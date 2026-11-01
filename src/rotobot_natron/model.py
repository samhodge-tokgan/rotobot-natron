"""Rotobot JSON <-> Natron Roto shapes, without Natron.

Import (:func:`build_plan`)
    Each JSON object becomes one closed Natron Bezier. Its per-shape transform
    carries the part's motion -- ``translate`` = the bone's first point,
    ``rotate`` = the bone's angle, ``center`` = (0, 0) -- and its control points
    are stored in that bone-local space, so the transform reads (and edits)
    like a parented hierarchy. Natron's extra matrix is not reachable from
    Python, so the camera is folded into the local points; the composition is
    still exact: ``plate = T + R(rotate) . local``.

    JSON coordinates are Y-down plate pixels with pixel i's centre at i;
    Natron's canonical space is y-up with pixel centres at i + 0.5, so
    ``x_natron = x + 0.5`` and ``y_natron = height - (y + 0.5)``. Natron time is the JSON frame number
    plus ``frame_start - 1`` (0 when the file has no ``frame_start``).

Export (:func:`export_json`)
    Natron's control points at each source frame are put back through the
    shape's transform (:mod:`rotobot_natron.xform`, Natron's own maths),
    flipped to Y-down, and written into a copy of the ORIGINAL document: only
    ``objects[*].frames[*].points`` and ``cps`` change, every other key is kept.
    A frame whose points did not move (within 1e-6 px) is kept verbatim. For an
    object that carried B-spline control points (``cps``), an edited frame that
    is still an exact B-spline keeps that form; otherwise it is refit with the
    same number of control points and the deviation is reported.
"""

from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import bspline
from .bspline import Knot
from .xform import ShapeXform, apply

SCHEMA = "lozenge_bezier_anim"
SUPPORTED_VERSIONS = (2, 3)

#: An unedited frame is kept verbatim when every knot and handle is within this.
UNCHANGED_TOL_PX = 1e-6
#: An edited Bezier still counts as a B-spline when it is this close to one.
BSPLINE_EXACT_TOL_PX = 1e-3
#: Refits that move the curve more than this are reported as warnings.
REFIT_WARN_PX = 0.5
#: Samples per segment for the refit (the product's own rule).
REFIT_MULT = 8


class ExportError(ValueError):
    """The Natron shapes cannot be written back; ``errors`` says why."""

    def __init__(self, errors: Sequence[str]):
        super().__init__("; ".join(errors[:5]) + (f" (+{len(errors) - 5} more)" if len(errors) > 5 else ""))
        self.errors = list(errors)


# ------------------------------------------------------------------ document


def check_document(raw: Any) -> List[str]:
    """Problems that stop a document being imported or exported (empty = fine)."""
    errs: List[str] = []
    if not isinstance(raw, Mapping):
        return ["not a JSON object"]
    if raw.get("schema") != SCHEMA:
        errs.append(f"schema is {raw.get('schema')!r}, expected {SCHEMA!r}")
    if raw.get("schema_version") not in SUPPORTED_VERSIONS:
        errs.append(f"schema_version {raw.get('schema_version')!r} is not one of {SUPPORTED_VERSIONS}")
    if height(raw) is None:
        errs.append("no resolution / height")
    objs = raw.get("objects")
    if not isinstance(objs, Mapping) or not objs:
        errs.append("no objects")
        return errs
    for key, o in objs.items():
        frames = o.get("frames") if isinstance(o, Mapping) else None
        if not isinstance(frames, Mapping):
            errs.append(f"{key}: no frames")
            continue
        n = None
        for fk, fr in frames.items():
            try:
                int(fk)
            except (TypeError, ValueError):
                errs.append(f"{key}: frame key {fk!r} is not an integer")
                continue
            pts = fr.get("points") if isinstance(fr, Mapping) else None
            if not isinstance(pts, list) or len(pts) < 2:
                errs.append(f"{key} frame {fk}: fewer than 2 points")
                continue
            if n is None:
                n = len(pts)
            elif len(pts) != n:
                errs.append(f"{key} frame {fk}: {len(pts)} points, other frames have {n}")
            for p in pts:
                vals = [p.get(k) for k in ("x", "y", "left_x", "left_y", "right_x", "right_y")]
                if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals):
                    errs.append(f"{key} frame {fk}: a point is missing a coordinate or is not finite")
                    break
    return errs


def height(raw: Mapping[str, Any]) -> Optional[float]:
    res = raw.get("resolution")
    if isinstance(res, (list, tuple)) and len(res) == 2:
        return float(res[1])
    if raw.get("height") is not None:
        return float(raw["height"])
    return None


def width(raw: Mapping[str, Any]) -> Optional[float]:
    res = raw.get("resolution")
    if isinstance(res, (list, tuple)) and len(res) == 2:
        return float(res[0])
    if raw.get("width") is not None:
        return float(raw["width"])
    return None


def frame_offset(raw: Mapping[str, Any]) -> int:
    """Natron time - JSON frame."""
    fs = raw.get("frame_start")
    try:
        return int(fs) - 1 if fs is not None else 0
    except (TypeError, ValueError):
        return 0


def script_name(key: str) -> str:
    """A Natron script name for an object key (``p0:arm:L:forearm`` -> ``p0_arm_L_forearm``)."""
    s = re.sub(r"[^A-Za-z0-9_]", "_", key)
    return s if s[:1].isalpha() else "s_" + s


def _knot(p: Mapping[str, Any]) -> Knot:
    return (float(p["x"]), float(p["y"]), float(p["left_x"]), float(p["left_y"]),
            float(p["right_x"]), float(p["right_y"]))


#: JSON coordinate i is the CENTRE of pixel i; Natron (like every DCC) puts
#: pixel i's centre at i + 0.5, and counts rows from the bottom.
PIXEL_CENTRE = 0.5


def _flip(k: Knot, h: float) -> Knot:
    """JSON (Y-down, centres at i) -> Natron canonical (y-up, centres at i + 0.5)."""
    c = PIXEL_CENTRE
    return (k[0] + c, h - (k[1] + c), k[2] + c, h - (k[3] + c), k[4] + c, h - (k[5] + c))


def _unflip(x: float, y: float, h: float) -> Tuple[float, float]:
    """Natron canonical -> JSON."""
    return (x - PIXEL_CENTRE, h - y - PIXEL_CENTRE)


# -------------------------------------------------------------------- import


@dataclass
class ShapeFrame:
    points: List[Knot]  # bone-local, Natron y-up
    translate: Tuple[float, float]
    rotate: float


@dataclass
class ShapePlan:
    key: str
    script_name: str
    layers: List[str]
    frames: Dict[int, ShapeFrame]  # Natron time -> frame
    visible: Dict[int, bool]  # Natron time -> visible, every time in the doc's range


@dataclass
class DocPlan:
    width: float
    height: float
    offset: int
    first: int  # Natron time
    last: int
    fps: float
    shapes: List[ShapePlan] = field(default_factory=list)


def _bone_series(frames: Mapping[str, Any], h: float, order: Sequence[int]) -> Dict[int, Tuple[float, float, float]]:
    """frame -> (tx, ty, angle_deg) in Natron space, holding the last good bone
    (the first good one for leading frames); (0, 0, 0) when there is none."""
    good: Dict[int, Tuple[float, float, float]] = {}
    for f in order:
        b = frames[str(f)].get("bone") if isinstance(frames[str(f)], Mapping) else None
        try:
            x0, y0 = float(b["pt0"]["x"]) + PIXEL_CENTRE, h - float(b["pt0"]["y"]) - PIXEL_CENTRE
            x1, y1 = float(b["pt1"]["x"]) + PIXEL_CENTRE, h - float(b["pt1"]["y"]) - PIXEL_CENTRE
        except (TypeError, KeyError, ValueError):
            continue
        if not all(math.isfinite(v) for v in (x0, y0, x1, y1)):
            continue
        good[f] = (x0, y0, math.degrees(math.atan2(y1 - y0, x1 - x0)))
    if not good:
        return {f: (0.0, 0.0, 0.0) for f in order}
    out: Dict[int, Tuple[float, float, float]] = {}
    last = good[min(good)]
    prev_ang: Optional[float] = None
    for f in order:
        last = good.get(f, last)
        x, y, a = last
        if prev_ang is not None:  # unwrap so Natron never interpolates the long way round
            a = a + 360.0 * round((prev_ang - a) / 360.0)
        prev_ang = a
        out[f] = (x, y, a)
    return out


def _to_local(k: Knot, tx: float, ty: float, deg: float) -> Knot:
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)

    def loc(x: float, y: float) -> Tuple[float, float]:
        dx, dy = x - tx, y - ty
        return (c * dx + s * dy, -s * dx + c * dy)

    a = loc(k[0], k[1])
    b = loc(k[2], k[3])
    d = loc(k[4], k[5])
    return (a[0], a[1], b[0], b[1], d[0], d[1])


def build_plan(raw: Mapping[str, Any]) -> DocPlan:
    errs = check_document(raw)
    if errs:
        raise ValueError("; ".join(errs))
    h = height(raw)
    w = width(raw) or 0.0
    off = frame_offset(raw)
    objs = raw["objects"]
    all_frames = sorted({int(f) for o in objs.values() for f in o["frames"]})
    first, last = all_frames[0] + off, all_frames[-1] + off
    plan = DocPlan(w, h, off, first, last, float(raw.get("fps") or 24))
    for key, o in objs.items():
        order = sorted(int(f) for f in o["frames"])
        bones = _bone_series(o["frames"], h, order)
        frames: Dict[int, ShapeFrame] = {}
        for f in order:
            tx, ty, ang = bones[f]
            pts = [_to_local(_flip(_knot(p), h), tx, ty, ang) for p in o["frames"][str(f)]["points"]]
            frames[f + off] = ShapeFrame(pts, (tx, ty), ang)
        vis_raw = o.get("visibility") if isinstance(o.get("visibility"), Mapping) else {}
        visible = {}
        for f in range(all_frames[0], all_frames[-1] + 1):
            v = str(f) in o["frames"]
            if v and str(f) in vis_raw:
                v = bool(vis_raw[str(f)])
            visible[f + off] = v
        pid = o.get("person_id", key.split(":")[0].lstrip("p"))
        body, side = o.get("body"), o.get("side")
        layers = [f"p{pid}"] + ([f"p{pid}_{body}"] if body else []) + ([f"p{pid}_{body}_{side}"] if body and side else [])
        plan.shapes.append(ShapePlan(key, script_name(key), layers, frames, visible))
    return plan


# -------------------------------------------------------------------- export


@dataclass
class ShapeDump:
    """What Natron holds for one shape, read at the source document's frames."""

    label: str
    #: Natron time -> (control points as Natron stores them, the shape's transform then).
    frames: Dict[int, Tuple[List[Knot], ShapeXform]]


@dataclass
class ExportReport:
    unchanged_frames: int = 0
    edited: Dict[str, int] = field(default_factory=dict)  # key -> edited frames
    cps_exact: Dict[str, int] = field(default_factory=dict)  # key -> edited frames still B-splines
    cps_refit: Dict[str, float] = field(default_factory=dict)  # key -> worst refit deviation, px
    warnings: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"{self.unchanged_frames} frame(s) unchanged; {sum(self.edited.values())} edited "
                 f"in {len(self.edited)} object(s)"]
        for k, n in sorted(self.edited.items()):
            extra = ""
            if k in self.cps_refit:
                extra = f", B-spline refit, max deviation {self.cps_refit[k]:.3f} px"
            elif k in self.cps_exact:
                extra = ", still an exact B-spline"
            lines.append(f"  {k}: {n} frame(s){extra}")
        lines += [f"warning: {w}" for w in self.warnings]
        return "\n".join(lines)


def _r(v: float) -> float:
    return round(v, 6)


def export_json(raw: Mapping[str, Any], dumps: Sequence[ShapeDump]) -> Tuple[Dict[str, Any], ExportReport]:
    """A copy of ``raw`` with the Natron edits written back, and what changed.
    Raises :class:`ExportError` when the shapes no longer match the document."""
    errs = check_document(raw)
    if errs:
        raise ExportError(errs)
    h = height(raw)
    off = frame_offset(raw)
    objs = raw["objects"]
    by_label: Dict[str, ShapeDump] = {}
    for d in dumps:
        if d.label in by_label:
            errs.append(f"two Natron shapes are labelled {d.label!r}")
        by_label[d.label] = d
    for label in by_label:
        if label not in objs:
            errs.append(f"shape {label!r} is not in the source document (added shapes can't be exported)")
    for key in objs:
        if key not in by_label:
            errs.append(f"object {key!r} has no Natron shape (deleted or renamed?)")
    if errs:
        raise ExportError(errs)

    out = copy.deepcopy(dict(raw))
    rep = ExportReport()
    for key, o in objs.items():
        d = by_label[key]
        has_cps = isinstance(o.get("frames"), Mapping) and any(
            isinstance(fr, Mapping) and "cps" in fr for fr in o["frames"].values())
        worst_refit = 0.0
        for fk, fr in o["frames"].items():
            t = int(fk) + off
            if t not in d.frames:
                errs.append(f"{key}: no Natron data at time {t} (JSON frame {fk})")
                continue
            pts, xf = d.frames[t]
            src = [_knot(p) for p in fr["points"]]
            if len(pts) != len(src):
                errs.append(f"{key} frame {fk}: {len(pts)} points in Natron, {len(src)} in the JSON "
                            "(points can't be added or removed)")
                continue
            m = xf.matrix()
            plate: List[Knot] = []
            for k in pts:
                a = _unflip(*apply(m, k[0], k[1]), h)
                b = _unflip(*apply(m, k[2], k[3]), h)
                c = _unflip(*apply(m, k[4], k[5]), h)
                plate.append((a[0], a[1], b[0], b[1], c[0], c[1]))
            if not all(math.isfinite(v) for k in plate for v in k):
                errs.append(f"{key} frame {fk}: a point is not finite")
                continue
            if bspline.max_knot_distance(plate, src) <= UNCHANGED_TOL_PX:
                rep.unchanged_frames += 1
                continue
            rep.edited[key] = rep.edited.get(key, 0) + 1
            ofr = out["objects"][key]["frames"][fk]
            if has_cps:
                C, resid = bspline.from_bezier(plate)
                if resid <= BSPLINE_EXACT_TOL_PX:
                    rep.cps_exact[key] = rep.cps_exact.get(key, 0) + 1
                else:
                    C, dev = bspline.fit(plate, REFIT_MULT)
                    plate = bspline.to_bezier(C)
                    worst_refit = max(worst_refit, dev)
                ofr["cps"] = [{"x": _r(x), "y": _r(y)} for x, y in C]
            ofr["points"] = [{"x": _r(k[0]), "y": _r(k[1]), "left_x": _r(k[2]), "left_y": _r(k[3]),
                              "right_x": _r(k[4]), "right_y": _r(k[5])} for k in plate]
        if key in rep.edited and has_cps and worst_refit > 0.0:
            rep.cps_refit[key] = worst_refit
            if worst_refit > REFIT_WARN_PX:
                rep.warnings.append(f"{key}: the edit is not a B-spline; the refit moves the curve up to "
                                    f"{worst_refit:.2f} px from what was drawn in Natron")
    if errs:
        raise ExportError(errs)
    return out, rep
