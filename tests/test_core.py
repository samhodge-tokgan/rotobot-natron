import json
import math
import random

import pytest

from rotobot_natron import bspline, model, xform
from rotobot_natron.model import ExportError, ShapeDump, build_plan, export_json
from rotobot_natron.xform import ShapeXform

from synth import cps_at, document


def dumps_from_plan(plan, edit=None):
    """What Natron would hand back if nothing was edited (``edit`` may change a frame)."""
    out = []
    for s in plan.shapes:
        frames = {}
        for t, fr in s.frames.items():
            pts = list(fr.points)
            xf = ShapeXform(translate=fr.translate, rotate=fr.rotate)
            if edit:
                pts, xf = edit(s.key, t, pts, xf)
            frames[t] = (pts, xf)
        out.append(ShapeDump(s.key, frames))
    return out


# ------------------------------------------------------------------ bspline


def test_bezier_form_inverts_exactly():
    C = cps_at(3, K=11)
    back, resid = bspline.from_bezier(bspline.to_bezier(C))
    assert resid < 1e-9
    assert max(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(C, back)) < 1e-9


def test_fit_of_a_bspline_is_itself():
    C = cps_at(7, K=9)
    got, dev = bspline.fit(bspline.to_bezier(C))
    assert dev < 1e-8
    assert max(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(C, got)) < 1e-8


def test_fit_of_a_broken_handle_reports_the_deviation():
    knots = bspline.to_bezier(cps_at(2))
    k = list(knots[3])
    k[4] += 25.0  # pull one handle out
    knots[3] = tuple(k)
    assert bspline.from_bezier(knots)[1] > 1.0
    C, dev = bspline.fit(knots)
    assert 0.1 < dev < 25.0


# -------------------------------------------------------------------- xform


def test_natron_matrix_matches_hand_composition():
    random.seed(1)
    for _ in range(50):
        xf = ShapeXform(translate=(random.uniform(-500, 500), random.uniform(-500, 500)),
                        rotate=random.uniform(-720, 720), scale=(random.uniform(0.2, 3), random.uniform(0.2, 3)),
                        skewx=random.uniform(-1, 1), skewy=random.uniform(-1, 1),
                        skew_order_yx=random.random() < 0.5, center=(random.uniform(0, 900), random.uniform(0, 900)))
        x, y = random.uniform(0, 1920), random.uniform(0, 1080)
        # center-relative, then scale, skew, rotate CCW, translate, back from center
        cx, cy = xf.center
        u, v = (x - cx) * xf.scale[0], (y - cy) * xf.scale[1]
        sx, sy = xf.skewx, xf.skewy
        if xf.skew_order_yx:
            u, v = u + sx * v, sy * u + (1 + sx * sy) * v
        else:
            u, v = (1 + sx * sy) * u + sx * v, sy * u + v
        r = math.radians(xf.rotate)
        u, v = math.cos(r) * u - math.sin(r) * v, math.sin(r) * u + math.cos(r) * v
        want = (u + cx + xf.translate[0], v + cy + xf.translate[1])
        got = xform.apply(xf.matrix(), x, y)
        assert math.hypot(want[0] - got[0], want[1] - got[1]) < 1e-9


def test_uniform_scale_uses_x():
    xf = ShapeXform(scale=(2.0, 5.0), uniform=True)
    assert xform.apply(xf.matrix(), 1.0, 1.0) == pytest.approx((2.0, 2.0))


# -------------------------------------------------------------------- model


def test_plan_frames_visibility_and_layers():
    doc = document()
    plan = build_plan(doc)
    assert (plan.first, plan.last, plan.offset) == (1001, 1012, 1000)
    arm, head = plan.shapes
    assert arm.script_name == "p0_arm_L_forearm" and arm.layers == ["p0", "p0_arm", "p0_arm_L"]
    assert arm.visible[1005] is False and arm.visible[1006] is True
    assert 1003 not in head.frames and head.visible[1003] is False
    # rotation unwrapped: 40 deg/frame keeps climbing past 360 (Natron's y-up flips the sign)
    rots = [arm.frames[t].rotate for t in sorted(arm.frames)]
    assert all(abs(b - a) < 180 for a, b in zip(rots, rots[1:]))
    assert abs(rots[-1] - rots[0]) > 360


def test_unedited_round_trip_is_verbatim():
    doc = document()
    out, rep = export_json(doc, dumps_from_plan(build_plan(doc)))
    assert out == doc
    assert rep.unchanged_frames == 12 + 11 and not rep.edited


def test_moving_the_transform_moves_the_plate_points():
    doc = document()

    def edit(key, t, pts, xf):
        if key == "p1:head:C:head" and t == 1004:
            xf.translate = (xf.translate[0] + 10.0, xf.translate[1] - 4.0)  # Natron y-up: -4 is 4 px DOWN
        return pts, xf

    out, rep = export_json(doc, dumps_from_plan(build_plan(doc), edit))
    a = doc["objects"]["p1:head:C:head"]["frames"]["4"]["points"][2]
    b = out["objects"]["p1:head:C:head"]["frames"]["4"]["points"][2]
    assert (b["x"] - a["x"], b["y"] - a["y"]) == pytest.approx((10.0, 4.0))
    assert rep.edited == {"p1:head:C:head": 1}
    assert "cps" not in out["objects"]["p1:head:C:head"]["frames"]["4"]


def test_bspline_edit_stays_exact_when_it_is_one():
    doc = document()

    def edit(key, t, pts, xf):
        if key == "p0:arm:L:forearm" and t == 1002:
            # move a whole control point's influence: shift every knot/handle the same way
            pts = [tuple(v + (3.0 if j % 2 == 0 else 0.0) for j, v in enumerate(k)) for k in pts]
        return pts, xf

    out, rep = export_json(doc, dumps_from_plan(build_plan(doc), edit))
    assert rep.cps_exact == {"p0:arm:L:forearm": 1} and not rep.cps_refit
    fr = out["objects"]["p0:arm:L:forearm"]["frames"]["2"]
    C = [(c["x"], c["y"]) for c in fr["cps"]]
    pts = [model._knot(p) for p in fr["points"]]
    assert bspline.max_knot_distance(bspline.to_bezier(C), pts) < 1e-5


def test_broken_bspline_is_refit_and_reported():
    doc = document()

    def edit(key, t, pts, xf):
        if key == "p0:arm:L:forearm" and t == 1007:
            k = list(pts[2])
            k[4] += 15.0
            pts = pts[:2] + [tuple(k)] + pts[3:]
        return pts, xf

    out, rep = export_json(doc, dumps_from_plan(build_plan(doc), edit))
    assert "p0:arm:L:forearm" in rep.cps_refit and rep.cps_refit["p0:arm:L:forearm"] > 0.1
    fr = out["objects"]["p0:arm:L:forearm"]["frames"]["7"]
    C = [(c["x"], c["y"]) for c in fr["cps"]]
    assert bspline.max_knot_distance(bspline.to_bezier(C), [model._knot(p) for p in fr["points"]]) < 1e-5
    assert len(C) == 8


def test_structural_edits_are_refused():
    doc = document()
    plan = build_plan(doc)
    d = dumps_from_plan(plan)
    with pytest.raises(ExportError) as e:
        export_json(doc, d[:1])
    assert "p1:head:C:head" in str(e.value.errors)
    with pytest.raises(ExportError) as e:
        export_json(doc, d + [ShapeDump("p9:new", {})])
    assert any("p9:new" in x for x in e.value.errors)

    def drop(key, t, pts, xf):
        return (pts[:-1] if key == "p1:head:C:head" else pts), xf

    with pytest.raises(ExportError) as e:
        export_json(doc, dumps_from_plan(plan, drop))
    assert any("points can't be added or removed" in x for x in e.value.errors)


def test_bad_documents_are_named():
    doc = document()
    doc["schema_version"] = 1
    assert any("schema_version" in e for e in model.check_document(doc))
    doc = json.loads(json.dumps(document()))
    doc["objects"]["p0:arm:L:forearm"]["frames"]["4"]["points"][0]["x"] = float("nan")
    assert any("not finite" in e for e in model.check_document(doc))


# ---------------------------------------------------------------------- cli


def test_install_plugin_and_check(tmp_path, capsys):
    from rotobot_natron import cli

    dest = cli.install_plugin(tmp_path / "plug")
    assert (dest / "initGui.py").exists() and (dest / "init.py").exists()
    assert (dest / "rotobot_natron" / "natron_io.py").exists()
    assert not (dest / "rotobot_natron" / "plugin").exists()
    f = tmp_path / "doc.json"
    f.write_text(json.dumps(document()))
    assert cli.main(["check", str(f)]) == 0
    assert "OK, 2 shapes, Natron frames 1001-1012" in capsys.readouterr().out
    bad = document()
    bad["schema"] = "other"
    f.write_text(json.dumps(bad))
    assert cli.main(["check", str(f)]) == 1
