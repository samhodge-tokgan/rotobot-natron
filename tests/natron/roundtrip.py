"""Headless round trip inside Natron:

    NatronRenderer -t tests/natron/roundtrip.py </dev/null

Environment:
    RN_JSON     source lozenge_bezier_anim JSON
    RN_OUT      output directory
    RN_FRAMES   optional: keep only the first N frames
    RN_OBJECTS  optional: comma-separated object-key prefixes to keep (e.g. "p0:")
    RN_SRC      the src/ directory holding rotobot_natron
    RN_MODE     fast (default: one key per shape + .ntp splice) or api (every key through the API)

Steps: import -> save .ntp -> reload -> export (must equal the source) ->
edit a handle and a transform -> export (refit reported) -> delete a shape
(export refused). Prints one line per check and exits 1 if any fails.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.environ["RN_SRC"])  # Natron runs -t scripts without __file__

from rotobot_natron import model, natron_io  # noqa: E402

app = app1  # noqa: F821  (Natron injects it in -t mode)
out = os.environ["RN_OUT"]
os.makedirs(out, exist_ok=True)
failed = []


def check(ok, what):
    print(("PASS " if ok else "FAIL ") + what, flush=True)
    if not ok:
        failed.append(what)


with open(os.environ["RN_JSON"]) as f:
    raw = json.load(f)
keep = [p for p in os.environ.get("RN_OBJECTS", "").split(",") if p]
if keep:
    raw["objects"] = {k: v for k, v in raw["objects"].items() if any(k.startswith(p) for p in keep)}
if os.environ.get("RN_FRAMES"):
    n = int(os.environ["RN_FRAMES"])
    for o in raw["objects"].values():
        fr = sorted(o["frames"], key=int)[:n]
        o["frames"] = {k: o["frames"][k] for k in fr}
src = os.path.join(out, "source.json")
with open(src, "w") as f:
    json.dump(raw, f)
npts = sum(len(next(iter(o["frames"].values()))["points"]) for o in raw["objects"].values())
nfr = max(len(o["frames"]) for o in raw["objects"].values())
print(f"source: {len(raw['objects'])} objects, {npts} points/frame, {nfr} frames", flush=True)

ntp = os.path.join(out, "roundtrip.ntp")
t = time.time()
if os.environ.get("RN_MODE", "fast") == "fast":
    app, nodes = natron_io.import_json_fast(app, src, ntp, log=lambda s: None)
    t_imp = time.time() - t
    t_save = 0.0
else:
    nodes = natron_io.import_json(app, src, log=lambda s: None)
    t_imp = time.time() - t
    t = time.time()
    app.saveProjectAs(ntp)
    t_save = time.time() - t
print(f"import ({os.environ.get('RN_MODE', 'fast')}) {t_imp:.1f} s, save {t_save:.1f} s, "
      f".ntp {os.path.getsize(ntp) / 1e6:.1f} MB", flush=True)

t = time.time()
names = [n.getScriptName() for n in nodes]
app2 = app.loadProject(ntp)
node = [app2.getNode(nm) for nm in names]
print(f"reload {time.time() - t:.1f} s, {len(node)} Roto node(s): {', '.join(names)}", flush=True)
check(all(n is not None and natron_io.source_of(n) == src for n in node), "the reloaded nodes remember their source JSON")

t = time.time()
rep = natron_io.export_json(node, os.path.join(out, "unedited.json"))
print(f"export {time.time() - t:.1f} s", flush=True)
with open(os.path.join(out, "unedited.json")) as f:
    back = json.load(f)
check(back == raw, f"unedited export equals the source ({rep.unchanged_frames} frames unchanged, "
                   f"{sum(rep.edited.values())} edited)")
if back != raw:
    worst = 0.0
    for k, o in raw["objects"].items():
        for fk, fr in o["frames"].items():
            a = [model._knot(p) for p in fr["points"]]
            b = [model._knot(p) for p in back["objects"][k]["frames"][fk]["points"]]
            from rotobot_natron import bspline
            worst = max(worst, bspline.max_knot_distance(a, b))
    print(f"  worst knot difference {worst:.2e} px", flush=True)

# ---- edits: pull one handle of a B-spline object; nudge another object's transform
def item(key):
    for n in node:
        it = n.getRotoContext().getItemByName(model.script_name(key))
        if it is not None:
            return it


cps_keys = [k for k, o in raw["objects"].items() if "cps" in next(iter(o["frames"].values()))]
plain_keys = [k for k in raw["objects"] if k not in cps_keys]
off = model.frame_offset(raw)
edit_frame = sorted(next(iter(raw["objects"].values()))["frames"], key=int)[min(5, nfr - 1)]
tt = float(int(edit_frame) + off)
if cps_keys:
    b = item(cps_keys[0])
    x, y, lx, ly, rx, ry = b.getControlPointPosition(2, tt)
    b.setPointAtIndex(2, tt, x, y, lx, ly, rx + 12.0, ry + 5.0)
    b.setFeatherPointAtIndex(2, tt, x, y, lx, ly, rx + 12.0, ry + 5.0)
# Not the last shape of a person: Natron leaves that one selected, and a
# selected shape's transform reads from the node's controls (where the GUI
# edits it), so a script writing the shape's own knob would not show.
moved = plain_keys[0] if plain_keys else (cps_keys[1] if len(cps_keys) > 1 else None)
if moved:
    moved_frame = sorted(raw["objects"][moved]["frames"], key=int)[-1]
    tm = float(int(moved_frame) + off)
    b2 = item(moved)
    tr = b2.getParam("translate")
    tr.setValueAtTime(tr.getValueAtTime(tm, 0) + 7.0, tm, 0)
rep = natron_io.export_json(node, os.path.join(out, "edited.json"))
print(rep.summary(), flush=True)
if cps_keys:
    check(cps_keys[0] in rep.cps_refit, f"the pulled handle on {cps_keys[0]} is refit as a B-spline")
if moved:
    with open(os.path.join(out, "edited.json")) as f:
        ed = json.load(f)
    a = raw["objects"][moved]["frames"][moved_frame]["points"][0]
    c = ed["objects"][moved]["frames"][moved_frame]["points"][0]
    check(abs((c["x"] - a["x"]) - 7.0) < 1e-4 and abs(c["y"] - a["y"]) < 1e-4,
          f"a +7 translate on {moved} moves its points +7 px in the JSON")
check(set(rep.edited) <= {cps_keys[0] if cps_keys else None, moved}, "nothing else changed")

# ---- a deleted shape is refused
victim = item(list(raw["objects"])[-1])
victim.getParentLayer().removeItem(victim)
try:
    natron_io.export_json(node, os.path.join(out, "refused.json"))
    check(False, "export refuses a deleted shape")
except model.ExportError as e:
    check(any("no Natron shape" in x for x in e.errors), "export refuses a deleted shape")

print("RESULT", "FAIL" if failed else "PASS", flush=True)
sys.stdout.flush()
os._exit(1 if failed else 0)
