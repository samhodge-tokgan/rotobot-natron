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
    # A plain Bezier object without a bone, missing frame 3.
    fr2 = {}
    for f in frames:
        if f == 3:
            continue
        fr2[str(f)] = {"points": [point((100.0 + i * 30 + f, 200.0 + (i % 2) * 40, 90.0 + i * 30 + f, 195.0,
                                         110.0 + i * 30 + f, 205.0)) for i in range(5)]}
    objs["p1:head:C:head"] = {"person_id": 1, "body": "head", "side": "C", "segment": "head",
                              "closed": True, "point_count": 5, "frames": fr2}
    return {"schema": "lozenge_bezier_anim", "schema_version": 3, "fps": 24, "resolution": [1920, 1080],
            "width": 1920, "height": 1080, "units": "pixels", "frame_start": frame_start,
            "camera": {"1": {"H2d": [1, 0, 0, 0, 1, 0, 0, 0, 1], "source": "ecc-seed"}},
            "spline_output": {"snap": "on"}, "objects": objs}
