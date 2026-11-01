"""Fast import: write every frame's control-point keys straight into a saved .ntp.

Why: in Natron 2.5 every ``BezierCurve.setPointAtIndex`` call ends in
``Bezier::copyInternalPointsToGuiPoints()``, which copies every control point's
whole animation, so one call costs (points in the shape) x (keys so far) and a
shape costs points^2 x frames^2. A 236-point shape over 120 frames is minutes;
a 1,000-frame shot is hours.

How: the shapes are built through the Python API with ONE key each (cheap),
the project is saved, and this module replaces each control point's and
feather point's ``*_animation`` key sets with the full per-frame keys. The
project is then reloaded and read back, so Natron itself confirms the result.

Natron 2.x saves projects with boost::serialization XML. A Bezier's points
follow its ``<NumPoints>``: ``<CP>`` then ``<FP>`` for each point, each holding
``X Y Left_X Left_Y Right_X Right_Y`` curves as ``<..._animation><KeyFrameSet>``.

Natron uses the derivatives stored in the file as they are (it does not
recompute them on load), so they are written exactly as the API path leaves
them (``Interpolation::autoComputeDerivatives``, keys of type Smooth = 2):

* the first key: left 0, right the slope to the next key;
* a middle key: Catmull-Rom, flattened at extrema and clamped so the curve
  cannot overshoot either neighbour;
* the last key: left 1.5 x the slope from the previous key, right 0;
* two keys: the slope on the inner side of each, 0 outside.
"""

from __future__ import annotations

import re
from typing import Dict, List, Sequence, Tuple

#: Natron's eKeyframeTypeSmooth.
SMOOTH = 2
_CURVES = ("X", "Y", "Left_X", "Left_Y", "Right_X", "Right_Y")


def smooth_derivatives(ts: Sequence[float], vs: Sequence[float]) -> List[Tuple[float, float]]:
    """(left, right) derivative per key, as Natron 2.5 stores them after an
    in-order build through the Python API."""
    n = len(vs)
    if n == 1:
        return [(0.0, 0.0)]
    if n == 2:
        s = (vs[1] - vs[0]) / (ts[1] - ts[0])
        return [(0.0, s), (s, 0.0)]
    out = [(0.0, (vs[1] - vs[0]) / (ts[1] - ts[0]))]
    for i in range(1, n - 1):
        out.append(_smooth_middle(ts[i - 1], vs[i - 1], ts[i], vs[i], ts[i + 1], vs[i + 1]))
    out.append((1.5 * (vs[-1] - vs[-2]) / (ts[-1] - ts[-2]), 0.0))
    return out


def _smooth_middle(tprev, vprev, tcur, vcur, tnext, vnext) -> Tuple[float, float]:
    P0 = Q3 = vcur
    if (vprev > vcur and vcur < vnext) or (vprev < vcur and vcur > vnext):
        P0pr = Q3pl = 0.0
    else:
        deriv = (vnext - vprev) / (tnext - tprev)
        P0pr = deriv * (tnext - tcur)
        Q3pl = deriv * (tcur - tprev)
        P1 = P0 + P0pr / 3.0
        Q2 = Q3 - Q3pl / 3.0
        prev_max, prev_min = max(vprev, vcur), min(vprev, vcur)
        if Q2 < prev_min or Q2 > prev_max:
            Q2new = max(prev_min, min(Q2, prev_max))
            P1 = P0 + (P1 - P0) * (Q3 - Q2new) / (Q3 - Q2)
            Q2 = Q2new
        next_max, next_min = max(vcur, vnext), min(vcur, vnext)
        if P1 < next_min or P1 > next_max:
            P1new = max(next_min, min(P1, next_max))
            Q2 = Q3 - (Q3 - Q2) * (P1new - P0) / (P1 - P0)
            P1 = P1new
        P0pr = 3.0 * (P1 - P0)
        Q3pl = 3.0 * (Q3 - Q2)
    return (Q3pl / (tcur - tprev), P0pr / (tnext - tcur))


def _e(v: float) -> str:
    return "%.17e" % v


def keyframe_set(open_set: str, open_item: str, indent: str, ts: Sequence[float], vs: Sequence[float]) -> str:
    """A ``<KeyFrameSet>`` element. ``open_set`` / ``open_item`` are the opening
    tags found in the file: boost writes class ids on the first one only."""
    der = smooth_derivatives(ts, vs)
    i1, i2 = indent + "\t", indent + "\t\t"
    parts = [f"{open_set}\n{i1}<count>{len(vs)}</count>\n{i1}<item_version>0</item_version>\n"]
    for k, (t, v, (dl, dr)) in enumerate(zip(ts, vs, der)):
        parts.append(f"{i1}{open_item if k == 0 else '<item>'}\n"
                     f"{i2}<Time>{_e(t)}</Time>\n{i2}<Value>{_e(v)}</Value>\n"
                     f"{i2}<InterpolationMethod>{SMOOTH}</InterpolationMethod>\n"
                     f"{i2}<LeftDerivative>{_e(dl)}</LeftDerivative>\n"
                     f"{i2}<RightDerivative>{_e(dr)}</RightDerivative>\n{i1}</item>\n")
    parts.append(f"{indent}</KeyFrameSet>")
    return "".join(parts)


_KFS = re.compile(r"(?P<indent>[ \t]*)(?P<open><KeyFrameSet[^>]*>)(?P<body>.*?)</KeyFrameSet>", re.S)
_ITEM = re.compile(r"<item(?: [^>]*)?>")


def splice(text: str, shapes: Dict[str, Tuple[List[float], List[List[Tuple[float, ...]]]]]) -> Tuple[str, int]:
    """Replace the point keys of every Bezier named in ``shapes``.

    ``shapes[script_name] = (times, frames)`` where ``frames[k][i]`` is point
    i's (x, y, lx, ly, rx, ry) at ``times[k]``; the feather points get the same
    keys. Returns the new text and the number of shapes spliced."""
    out: List[str] = []
    pos = 0
    done = 0
    names = re.compile(r"<Name>(" + "|".join(re.escape(n) for n in shapes) + r")</Name>") if shapes else None
    for m in re.finditer(r"<NumPoints>(\d+)</NumPoints>", text):
        if names is None:
            break
        owner = None
        for nm in names.finditer(text, pos, m.start()):
            owner = nm.group(1)
        if owner is None:
            continue
        times, frames = shapes[owner]
        n = int(m.group(1))
        if frames and len(frames[0]) != n:
            raise ValueError(f"{owner}: the project has {n} points, the plan {len(frames[0])}")
        out.append(text[pos:m.end()])
        cur = m.end()
        for i in range(n):
            for _which in ("CP", "FP"):
                for c, curve in enumerate(_CURVES):
                    a = text.index(f"<{curve}_animation>", cur)
                    k = _KFS.search(text, a)
                    out.append(text[cur:k.start()])
                    item = _ITEM.search(k.group("body"))
                    vs = [fr[i][c] for fr in frames]
                    out.append(k.group("indent") + keyframe_set(k.group("open"), item.group(0) if item else "<item>",
                                                                k.group("indent"), times, vs))
                    cur = k.end()
        pos = cur
        done += 1
    out.append(text[pos:])
    return "".join(out), done
