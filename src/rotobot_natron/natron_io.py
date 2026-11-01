"""The Natron side: build a Roto node from a plan, and read it back for export.

The only module that imports ``NatronEngine``. Tested against Natron 2.5.0
(Python 3.10, PySide 1.2.4). Notes on the API, all checked on 2.5.0:

* ``BezierCurve.setPointAtIndex`` keys the whole shape at that time (auto-key
  is on by default and Python cannot turn it off); the feather points must be
  set too or they stay where the shape was created.
* ``setCurveFinished(True)`` re-centres the transform, so ``center`` is set
  after it.
* The per-shape extra matrix is a 9-dimension knob Python cannot reach
  (``getParam("extraMatrix")`` is ``None``), hence no camera matrix.
* The animated "activated" value is ignored by the renderer (and by
  ``getIsActivated``), so visibility is keyed on opacity.
* A Roto node renders at most ~64 shapes: when its internal Merge fills, more
  are chained, but the node outputs the first (``getMergeNode`` returns
  ``globalMergeNodes.front()``). Hence one node per person.
* ``Layer.getChildren()`` returns plain items; ``Roto.getItemByName`` returns
  the typed object.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Mapping, Optional, Tuple

import NatronEngine  # noqa: F401  (only available inside Natron)

from . import model
from .model import DocPlan, ShapeDump
from .xform import ShapeXform

PLUGIN_ID = "fr.inria.built-in.Roto"
#: User parameters stored on the Roto node so export can find its source.
SOURCE_PARAM = "rotobotSource"
OFFSET_PARAM = "rotobotFrameOffset"


def _layer(roto, parent, label: str, cache: Dict[Tuple[str, ...], Any], path: Tuple[str, ...]):
    if path in cache:
        return cache[path]
    lay = roto.createLayer()
    lay.setScriptName(model.script_name(label))
    lay.setLabel(label)
    parent.addItem(lay)
    cache[path] = lay
    return lay


#: Natron 2.5 renders at most 64 shapes of one Roto node (they are merged by a
#: single internal Merge node); shapes past that are silently dropped. So each
#: person gets their own node, split further when one person has more.
MAX_SHAPES_PER_NODE = 60
#: Width (frames) of a visibility step.
VIS_STEP = 1e-3


def node_groups(plan: DocPlan) -> List[Tuple[str, List[Any]]]:
    """(suffix, shapes) per Roto node: one per person, chunked to MAX_SHAPES_PER_NODE."""
    by: Dict[str, List[Any]] = {}
    for s in plan.shapes:
        by.setdefault(s.layers[0], []).append(s)
    out = []
    for person, shapes in by.items():
        for i in range(0, len(shapes), MAX_SHAPES_PER_NODE):
            part = shapes[i:i + MAX_SHAPES_PER_NODE]
            out.append((person if len(shapes) <= MAX_SHAPES_PER_NODE else f"{person}_{i // MAX_SHAPES_PER_NODE}", part))
    return out


def build_nodes(app, plan: DocPlan, source_path: str = "", node_name: str = "Rotobot",
                feather: float = 0.0, log=print, point_keys: str = "all") -> List[Any]:
    """Create the Roto nodes for ``plan`` -- ``<node_name>_<person>``, each
    composited over the previous one through its Bg input -- and return them;
    the last is the output. Connect the plate to the first one's Bg input.

    ``point_keys="first"`` keys the control points on each shape's first frame
    only (transforms and visibility are still keyed on every frame); the rest
    are spliced into the saved project by :func:`import_json_fast`."""
    fitted = _set_project(app, plan, log)
    nodes: List[Any] = []
    for suffix, shapes in node_groups(plan):
        node = _build_one(app, plan, shapes, source_path, f"{node_name}_{suffix}", feather, log, point_keys)
        if nodes:
            node.connectInput(0, nodes[-1])
        node.setPosition(0.0, 120.0 * len(nodes))
        nodes.append(node)
    if not fitted and nodes:
        _canvas(app, plan, nodes[0], f"{node_name}_canvas", log)
    return nodes


def _canvas(app, plan: DocPlan, first, name: str, log) -> None:
    """A transparent Constant of the plate's size on the first node's Bg input,
    so the shapes are not cropped to a project format of another size. Replace
    it with the plate when you have one."""
    try:
        c = app.createNode("net.sf.openfx.ConstantPlugin")
        c.setScriptName(name)
        ex = c.getParam("extent")
        ex.setValue([ex.getOption(i) for i in range(ex.getNumOptions())].index("size"))
        c.getParam("size").setValue(float(plan.width), 0)
        c.getParam("size").setValue(float(plan.height), 1)
        c.getParam("bottomLeft").setValue(0.0, 0)
        c.getParam("bottomLeft").setValue(0.0, 1)
        col = c.getParam("color")
        for i in range(4):
            col.setValue(0.0, i)
        fr = c.getParam("frameRange")
        fr.setValue(int(plan.first), 0)
        fr.setValue(int(plan.last), 1)
        first.connectInput(0, c)
        c.setPosition(0.0, -120.0)
    except Exception as e:
        log(f"rotobot-natron: could not add a {int(plan.width)}x{int(plan.height)} canvas ({e})")


def _build_one(app, plan: DocPlan, shapes, source_path: str, node_name: str, feather: float, log, point_keys: str):
    t0 = time.time()
    node = app.createNode(PLUGIN_ID)
    node.setScriptName(node_name)
    node.setLabel(node_name)
    roto = node.getRotoContext()
    try:
        p = node.createStringParam(SOURCE_PARAM, "Rotobot JSON")
        p.setValue(source_path)
        q = node.createIntParam(OFFSET_PARAM, "Rotobot frame offset")
        q.setValue(plan.offset)
    except Exception as e:  # user params are a convenience; export can be told the source
        log(f"rotobot-natron: could not store the source path on the node ({e})")

    base = roto.getBaseLayer()
    layers: Dict[Tuple[str, ...], Any] = {}
    for i, s in enumerate(shapes):
        parent = base
        for depth in range(len(s.layers)):
            parent = _layer(roto, parent, s.layers[depth], layers, tuple(s.layers[: depth + 1]))
        times = sorted(s.frames)
        n = len(s.frames[times[0]].points)
        b = roto.createBezier(0.0, 0.0, float(times[0]))
        for _ in range(n - 1):
            b.addControlPoint(0.0, 0.0)
        b.setCurveFinished(True)
        if not b.setScriptName(s.script_name):
            log(f"rotobot-natron: script name {s.script_name} taken; Natron keeps {b.getScriptName()}")
        b.setLabel(s.key)
        parent.addItem(b)
        b.getFeatherDistanceParam().setValue(float(feather))
        center = b.getParam("center")
        center.setValue(0.0, 0)
        center.setValue(0.0, 1)
        tr, ro = b.getParam("translate"), b.getParam("rotate")
        for t in times:
            fr = s.frames[t]
            if point_keys == "all" or t == times[0]:
                for k, pt in enumerate(fr.points):
                    b.setPointAtIndex(k, float(t), *pt)
                    b.setFeatherPointAtIndex(k, float(t), *pt)
            tr.setValueAtTime(fr.translate[0], t, 0)
            tr.setValueAtTime(fr.translate[1], t, 1)
            ro.setValueAtTime(fr.rotate, t, 0)
        # Visibility as opacity: Natron 2.5's renderer ignores the animated
        # "activated" value. Each change is a step just before the frame (a
        # hold key, as Silhouette's), so motion-blur samples do not fade.
        op = b.getOpacityParam()
        prev: Optional[bool] = None
        for t in sorted(s.visible):
            v = s.visible[t]
            if v != prev:
                if prev is not None:
                    op.setValueAtTime(1.0 if prev else 0.0, t - VIS_STEP)
                op.setValueAtTime(1.0 if v else 0.0, t)
                prev = v
        log(f"rotobot-natron: {node_name} {i + 1}/{len(shapes)} {s.key} ({n} points x {len(times)} frames)")
    log(f"rotobot-natron: built {node_name}, {len(shapes)} shapes, in {time.time() - t0:.1f} s")
    return node


def _set_project(app, plan: DocPlan, log) -> bool:
    """Frame range, rate and format. False when no project format of the
    plate's size could be chosen."""
    try:
        app.getProjectParam("frameRange").set(int(plan.first), int(plan.last))
        app.getProjectParam("lockRange").setValue(True)
    except Exception as e:
        log(f"rotobot-natron: could not set the project frame range ({e})")
    try:
        if plan.fps:
            app.getProjectParam("frameRate").setValue(float(plan.fps))
    except Exception as e:
        log(f"rotobot-natron: could not set the frame rate ({e})")
    # A built-in format of the same size when there is one, else a new one
    # (App.addFormat wants "Name WxH PAR" with no space in the name).
    w, h = int(plan.width), int(plan.height)
    try:
        fmt = app.getProjectParam("outputFormat")
        names = [fmt.getOption(i) for i in range(fmt.getNumOptions())]
        want = BUILTIN_FORMATS.get((w, h))
        if want in names:
            fmt.setValue(names.index(want))
            return True
        app.addFormat(f"Rotobot_{w}x{h} {w}x{h} 1")
        for i in range(fmt.getNumOptions()):
            if fmt.getOption(i).startswith(f"Rotobot_{w}x{h}"):
                fmt.setValue(i)
                return True
        log(f"rotobot-natron: no {w}x{h} project format; adding a {w}x{h} canvas instead")
    except Exception as e:
        log(f"rotobot-natron: could not set the project format ({e})")
    return False


#: Natron 2.5's built-in square-pixel formats.
BUILTIN_FORMATS = {
    (640, 480): "PC_Video", (720, 576): "PAL", (1280, 720): "HD_720", (1920, 1080): "HD",
    (3840, 2160): "UHD_4K", (1024, 778): "1K_Super_35(full-ap)", (2048, 1556): "2K_Super_35(full-ap)",
    (2048, 1080): "2K_DCP", (4096, 3112): "4K_Super_35(full-ap)", (4096, 2160): "4K_DCP",
    (256, 256): "square_256", (512, 512): "square_512", (1024, 1024): "square_1K", (2048, 2048): "square_2K",
}


def import_json(app, path: str, **kw) -> List[Any]:
    """Build through the Python API alone: exact, but slow on big shapes
    (see :mod:`rotobot_natron.ntp_splice`). Returns the nodes."""
    with open(path) as f:
        raw = json.load(f)
    return build_nodes(app, model.build_plan(raw), source_path=path, **kw)


def import_json_fast(app, path: str, project_path: str, node_name: str = "Rotobot", log=print, **kw):
    """Build with one point key per shape, save, splice in every frame's keys,
    and reload from ``project_path``. Returns ``(app, nodes)`` of the reloaded
    project; the caller should use those from now on."""
    from . import ntp_splice

    with open(path) as f:
        raw = json.load(f)
    plan = model.build_plan(raw)
    names = [n.getScriptName() for n in build_nodes(app, plan, source_path=path, node_name=node_name,
                                                     log=log, point_keys="first", **kw)]
    t0 = time.time()
    # Saved under another name: reloading the path the app already has open
    # comes back without its nodes.
    one_key = project_path + ".onekey.ntp"
    app.saveProjectAs(one_key)
    with open(one_key) as f:
        text = f.read()
    os.remove(one_key)
    shapes = {}
    for s in plan.shapes:
        times = sorted(s.frames)
        shapes[s.script_name] = ([float(t) for t in times], [s.frames[t].points for t in times])
    text, n = ntp_splice.splice(text, shapes)
    if n != len(plan.shapes):
        raise RuntimeError(f"spliced {n} of {len(plan.shapes)} shapes; the project layout was not as expected")
    with open(project_path, "w") as f:
        f.write(text)
    app2 = app.loadProject(project_path)
    if app2 is None:
        raise RuntimeError(f"Natron could not reload {project_path} after the splice")
    nodes = [app2.getNode(nm) for nm in names]
    if any(nd is None for nd in nodes):
        raise RuntimeError(f"{project_path} reloaded without its Rotobot nodes")
    log(f"rotobot-natron: spliced {n} shapes and reloaded in {time.time() - t0:.1f} s")
    return app2, nodes


# -------------------------------------------------------------------- export


def _walk(roto, layer, out: List[Any]) -> None:
    for child in layer.getChildren():
        item = roto.getItemByName(child.getScriptName())
        if isinstance(item, NatronEngine.Layer):
            _walk(roto, item, out)
        elif item is not None and hasattr(item, "getNumControlPoints"):
            out.append(item)


def _xform_at(b, t: float) -> ShapeXform:
    tr, ro, sc = b.getParam("translate"), b.getParam("rotate"), b.getParam("scale")
    un, kx, ky = b.getParam("uniform"), b.getParam("skewx"), b.getParam("skewy")
    so, ce = b.getParam("skewOrder"), b.getParam("center")
    return ShapeXform(
        translate=(tr.getValueAtTime(t, 0), tr.getValueAtTime(t, 1)),
        rotate=ro.getValueAtTime(t, 0),
        scale=(sc.getValueAtTime(t, 0), sc.getValueAtTime(t, 1)),
        uniform=bool(un.getValueAtTime(t)),
        skewx=kx.getValueAtTime(t, 0),
        skewy=ky.getValueAtTime(t, 0),
        skew_order_yx=so.getValueAtTime(t) == 1,
        center=(ce.getValueAtTime(t, 0), ce.getValueAtTime(t, 1)),
    )


def rotobot_nodes(app, source: Optional[str] = None) -> List[Any]:
    """The Roto nodes an import created (those carrying the source parameter),
    optionally only those from ``source``."""
    out = []
    for n in app.getChildren():
        p = n.getParam(SOURCE_PARAM)
        if p is not None and (source is None or p.getValue() == source):
            out.append(n)
    return out


def dump_nodes(nodes, raw: Mapping[str, Any]) -> List[ShapeDump]:
    """Every Bezier under ``nodes``, read at the source document's frames."""
    shapes: List[Any] = []
    for node in nodes:
        roto = node.getRotoContext()
        _walk(roto, roto.getBaseLayer(), shapes)
    off = model.frame_offset(raw)
    objs = raw["objects"]
    dumps = []
    for b in shapes:
        label = b.getLabel()
        frames = {}
        if label in objs:
            n = b.getNumControlPoints()
            for fk in objs[label]["frames"]:
                t = int(fk) + off
                pts = [tuple(b.getControlPointPosition(k, float(t))) for k in range(n)]
                frames[t] = (pts, _xform_at(b, float(t)))
        dumps.append(ShapeDump(label, frames))
    return dumps


def source_of(node) -> Optional[str]:
    p = node.getParam(SOURCE_PARAM)
    return p.getValue() if p is not None else None


def export_json(nodes, out_path: str, source_path: Optional[str] = None):
    """Write the shapes of ``nodes`` (all the nodes of one import) back over a
    copy of the source JSON. Returns the report."""
    nodes = list(nodes) if isinstance(nodes, (list, tuple)) else [nodes]
    src = source_path or source_of(nodes[0])
    if not src:
        raise model.ExportError(["the node has no Rotobot source JSON; pass source_path"])
    with open(src) as f:
        raw = json.load(f)
    out, rep = model.export_json(raw, dump_nodes(nodes, raw))
    with open(out_path, "w") as f:
        json.dump(out, f)
    return rep
