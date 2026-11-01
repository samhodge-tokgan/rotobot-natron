"""Natron's per-shape Roto transform, reproduced exactly.

Natron 2.x draws a Roto shape's control points through
``RotoDrawableItem::getTransformAtTime``, which is
``Transform::matTransformCanonical(translate, scale, skew, skewOrder, rotate,
center) x extraMatrix``. The extra matrix is not reachable from Python, so it
is identity for every shape this package writes and is ignored here.

``matTransformCanonical`` (Engine/Transform.cpp) composes, applied right to
left::

    T(center) T(translate) R(-rads) Skew(skewX, skewY, order) S(sx, sy) T(-center)

with ``matRotation(r) = [[cos r, sin r], [-sin r, cos r]]``, so a positive
``rotate`` turns counter-clockwise in Natron's y-up canonical space.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence, Tuple

Mat3 = Tuple[float, float, float, float, float, float, float, float, float]


@dataclass
class ShapeXform:
    translate: Tuple[float, float] = (0.0, 0.0)
    rotate: float = 0.0  # degrees
    scale: Tuple[float, float] = (1.0, 1.0)
    uniform: bool = False
    skewx: float = 0.0
    skewy: float = 0.0
    skew_order_yx: bool = False
    center: Tuple[float, float] = (0.0, 0.0)

    def matrix(self) -> Mat3:
        sx = self.scale[0]
        sy = sx if self.uniform else self.scale[1]
        return mat_transform_canonical(self.translate[0], self.translate[1], sx, sy,
                                       self.skewx, self.skewy, self.skew_order_yx,
                                       math.radians(self.rotate), self.center[0], self.center[1])


def mul(a: Sequence[float], b: Sequence[float]) -> Mat3:
    return tuple(  # type: ignore[return-value]
        sum(a[r * 3 + k] * b[k * 3 + c] for k in range(3)) for r in range(3) for c in range(3))


def translation(x: float, y: float) -> Mat3:
    return (1.0, 0.0, x, 0.0, 1.0, y, 0.0, 0.0, 1.0)


def rotation(rads: float) -> Mat3:
    c, s = math.cos(rads), math.sin(rads)
    return (c, s, 0.0, -s, c, 0.0, 0.0, 0.0, 1.0)


def scaling(x: float, y: float) -> Mat3:
    return (x, 0.0, 0.0, 0.0, y, 0.0, 0.0, 0.0, 1.0)


def skew_xy(skew_x: float, skew_y: float, order_yx: bool) -> Mat3:
    return (1.0 if order_yx else 1.0 + skew_x * skew_y, skew_x, 0.0,
            skew_y, (1.0 + skew_x * skew_y) if order_yx else 1.0, 0.0,
            0.0, 0.0, 1.0)


def mat_transform_canonical(tx: float, ty: float, sx: float, sy: float, skew_x: float, skew_y: float,
                            skew_order_yx: bool, rads: float, cx: float, cy: float) -> Mat3:
    m = mul(translation(cx, cy), translation(tx, ty))
    m = mul(m, rotation(-rads))
    m = mul(m, skew_xy(skew_x, skew_y, skew_order_yx))
    m = mul(m, scaling(sx, sy))
    return mul(m, translation(-cx, -cy))


def apply(m: Sequence[float], x: float, y: float) -> Tuple[float, float]:
    w = m[6] * x + m[7] * y + m[8]
    return ((m[0] * x + m[1] * y + m[2]) / w, (m[3] * x + m[4] * y + m[5]) / w)
