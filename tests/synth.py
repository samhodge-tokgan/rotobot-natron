"""A small synthetic lozenge_bezier_anim v3 document for tests."""

import math

from rotobot_natron import bspline


def cps_at(f, K=8, cx=600.0, cy=400.0):
    r = 80 + 5 * math.sin(f / 3.0)
    return [(cx + 2 * f + r * math.cos(2 * math.pi * i / K), cy + f + 0.6 * r * math.sin(2 * math.pi * i / K))
            for i in range(K)]


def point(k):
    return {"x": k[0], "y": k[1], "left_x": k[2], "left_y": k[3], "right_x": k[4], "right_y": k[5]}


def document(frames=range(1, 13), frame_start=1001):
    objs = {}
    # A B-spline object (cps + exact Bezier points), its bone turning through 400 degrees.
    fr = {}
    for f in frames:
        C = cps_at(f)
        a = math.radians(40.0 * f)
        fr[str(f)] = {
            "points": [point(k) for k in bspline.to_bezier(C)],
            "cps": [{"x": x, "y": y} for x, y in C],
            "bone": {"pt0": {"x": 600.0 + 2 * f, "y": 400.0 + f},
                     "pt1": {"x": 600.0 + 2 * f + 100 * math.cos(a), "y": 400.0 + f + 100 * math.sin(a)}},
        }
    objs["p0:arm:L:forearm"] = {"person_id": 0, "body": "arm", "side": "L", "segment": "forearm",
                                "closed": True, "point_count": 8, "spline": "bspline3_uniform_closed",
                                "visibility": {str(f): (0 if f == 5 else 1) for f in frames}, "frames": fr}
    # A plain Bezier object without a bone, missing frame 3. Its handles are
    # knot -/+ 0.3 (next - prev), as the product writes them: in line with the
    # knot (Natron re-aligns handles that are not).
    fr2 = {}
    for f in frames:
        if f == 3:
            continue
        P = [(160.0 + f + 60 * math.cos(2 * math.pi * i / 5), 220.0 + 40 * math.sin(2 * math.pi * i / 5)) for i in range(5)]
        knots = []
        for i, (x, y) in enumerate(P):
            (px, py), (nx, ny) = P[i - 1], P[(i + 1) % 5]
            dx, dy = 0.3 * (nx - px), 0.3 * (ny - py)
            knots.append((x, y, x - dx, y - dy, x + dx, y + dy))
        fr2[str(f)] = {"points": [point(k) for k in knots]}
    objs["p1:head:C:head"] = {"person_id": 1, "body": "head", "side": "C", "segment": "head",
                              "closed": True, "point_count": 5, "frames": fr2}
    # A second shape for person 1, so the head is not the one Natron leaves
    # selected (the last created), whose transform reads from the node's.
    objs["p1:hand:R:palm"] = {"person_id": 1, "body": "hand", "side": "R", "segment": "palm",
                              "closed": True, "point_count": 5,
                              "frames": {k: {"points": [dict(p, x=p["x"] + 300, left_x=p["left_x"] + 300,
                                                             right_x=p["right_x"] + 300) for p in v["points"]]}
                                         for k, v in fr2.items()}}
    return {"schema": "lozenge_bezier_anim", "schema_version": 3, "fps": 24, "resolution": [1920, 1080],
            "width": 1920, "height": 1080, "units": "pixels", "frame_start": frame_start,
            "camera": {"1": {"H2d": [1, 0, 0, 0, 1, 0, 0, 0, 1], "source": "ecc-seed"}},
            "spline_output": {"snap": "on"}, "objects": objs}
