"""Closed uniform cubic B-splines and their exact cubic Bezier form, in plain Python.

A closed uniform cubic B-spline with control points C[0..K-1] is exactly the
closed cubic Bezier whose knot i and handles are::

    J[i] = (C[i-1] + 4 C[i] + C[i+1]) / 6
    L[i] = (C[i-1] + 2 C[i]) / 3            (incoming handle)
    R[i] = (2 C[i] + C[i+1]) / 3            (outgoing handle)

so segment i -> i+1 has controls J[i], R[i], L[i+1], J[i+1]. Going back,
``2 R[i] - L[i+1] == C[i]`` exactly; :func:`from_bezier` uses that and reports
how far the Bezier is from being a B-spline at all.

When an edit leaves the B-spline form, :func:`fit` finds the K control points
whose curve is closest (least squares) to the edited Bezier sampled ``mult``
times per segment, the same rule the product's own refit uses.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import List, Sequence, Tuple

Vec2 = Tuple[float, float]
#: x, y, left_x, left_y, right_x, right_y -- absolute positions.
Knot = Tuple[float, float, float, float, float, float]


def to_bezier(C: Sequence[Vec2]) -> List[Knot]:
    K = len(C)
    out: List[Knot] = []
    for i in range(K):
        (ax, ay), (bx, by), (cx, cy) = C[i - 1], C[i], C[(i + 1) % K]
        out.append((
            (ax + 4 * bx + cx) / 6.0, (ay + 4 * by + cy) / 6.0,
            (ax + 2 * bx) / 3.0, (ay + 2 * by) / 3.0,
            (2 * bx + cx) / 3.0, (2 * by + cy) / 3.0,
        ))
    return out


def from_bezier(knots: Sequence[Knot]) -> Tuple[List[Vec2], float]:
    """Control points read off the handles, and the largest distance (px)
    between ``knots`` and the exact Bezier form of those control points.
    Zero (to rounding) means the Bezier IS that B-spline."""
    K = len(knots)
    C = [(2 * knots[i][4] - knots[(i + 1) % K][2], 2 * knots[i][5] - knots[(i + 1) % K][3])
         for i in range(K)]
    return C, max_knot_distance(knots, to_bezier(C))


def max_knot_distance(a: Sequence[Knot], b: Sequence[Knot]) -> float:
    worst = 0.0
    for p, q in zip(a, b):
        for j in (0, 2, 4):
            worst = max(worst, math.hypot(p[j] - q[j], p[j + 1] - q[j + 1]))
    return worst


def _basis(t: float) -> Tuple[float, float, float, float]:
    t2, t3 = t * t, t * t * t
    return ((1 - t) ** 3 / 6.0, (3 * t3 - 6 * t2 + 4) / 6.0,
            (-3 * t3 + 3 * t2 + 3 * t + 1) / 6.0, t3 / 6.0)


def evaluate(C: Sequence[Vec2], mult: int) -> List[Vec2]:
    """The curve at u = j / mult, j = 0 .. K*mult-1."""
    K = len(C)
    out: List[Vec2] = []
    for j in range(K * mult):
        i, t = divmod(j, mult)
        w = _basis(t / mult)
        x = y = 0.0
        for k in range(4):
            cx, cy = C[(i - 1 + k) % K]
            x += w[k] * cx
            y += w[k] * cy
        out.append((x, y))
    return out


def sample_bezier(knots: Sequence[Knot], mult: int) -> List[Vec2]:
    """The closed Bezier at t = s / mult on each segment i -> i+1, in order."""
    K = len(knots)
    out: List[Vec2] = []
    for i in range(K):
        p0 = knots[i][0:2]
        p1 = knots[i][4:6]
        p2 = knots[(i + 1) % K][2:4]
        p3 = knots[(i + 1) % K][0:2]
        for s in range(mult):
            t = s / mult
            u = 1 - t
            a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
            out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                        a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def _solve(A: List[List[float]], B: List[List[float]]) -> List[List[float]]:
    """A X = B by Gaussian elimination with partial pivoting (A is K x K)."""
    n = len(A)
    M = [A[r][:] + B[r][:] for r in range(n)]
    m = len(B[0])
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        piv = M[c][c]
        for r in range(n):
            if r != c and M[r][c] != 0.0:
                f = M[r][c] / piv
                Mr, Mc = M[r], M[c]
                for k in range(c, n + m):
                    Mr[k] -= f * Mc[k]
    return [[M[r][n + k] / M[r][r] for k in range(m)] for r in range(n)]


@lru_cache(maxsize=64)
def _fit_matrix(K: int, mult: int) -> Tuple[Tuple[float, ...], ...]:
    """F [K x K*mult] with control points = F @ samples (least squares)."""
    rows = []  # B: (K*mult) x K
    for j in range(K * mult):
        i, t = divmod(j, mult)
        w = _basis(t / mult)
        row = [0.0] * K
        for k in range(4):
            row[(i - 1 + k) % K] += w[k]
        rows.append(row)
    BtB = [[sum(r[a] * r[b] for r in rows) for b in range(K)] for a in range(K)]
    Bt = [[r[a] for r in rows] for a in range(K)]
    return tuple(tuple(r) for r in _solve(BtB, Bt))


def fit(knots: Sequence[Knot], mult: int = 8) -> Tuple[List[Vec2], float]:
    """Least-squares K control points for the edited closed Bezier ``knots``
    (K = len(knots)), and the largest distance (px) between the edited curve
    and the fitted one at the ``mult``-per-segment samples."""
    K = len(knots)
    E = sample_bezier(knots, mult)
    F = _fit_matrix(K, mult)
    C = [(sum(f * e[0] for f, e in zip(row, E)), sum(f * e[1] for f, e in zip(row, E))) for row in F]
    got = evaluate(C, mult)
    dev = max(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(E, got))
    return C, dev
