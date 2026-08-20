# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright Contributors to the otio-fdl project

"""Coordinate transforms between related FDL canvases.

The bridge between what editorial saw and the camera original: two
canvases that carry a framing decision for the *same framing intent*
describe the same creative rectangle in two pixel spaces. Registering
those rectangles (in desqueezed display space, per the spec's
desqueeze-then-scale rule) yields the affine map between the canvases —
offline proxy to OCF, OCF to VFX pull, pull to conform raster.

A transform is a plain dict ``{"scale_x", "scale_y", "offset_x",
"offset_y", "uniform"}`` mapping source-canvas pixels to target-canvas
pixels: ``x' = x * scale_x + offset_x`` (and likewise y). ``uniform`` is
False when the two axes disagree beyond tolerance — a sign of
inconsistent framing data (e.g. a mis-declared squeeze), left to the
caller to treat as an error or not.
"""

from __future__ import annotations

import math

from .core import FDLError, canvas_by_id, select_decision

_UNIFORM_TOLERANCE = 1e-3


def transform_between(
    document, source_canvas_id, target_canvas_id, framing_intent_id=None
):
    """The affine map from one canvas's pixels to another's.

    Both canvases must hold a framing decision for the registration
    intent — ``framing_intent_id``, or the document's
    ``default_framing_intent``. Raises :class:`FDLError` when either
    decision is missing or degenerate.
    """
    source = canvas_by_id(document, source_canvas_id)
    target = canvas_by_id(document, target_canvas_id)
    default_intent = document.get("default_framing_intent")
    src_fd = select_decision(source, framing_intent_id, default_intent=default_intent)
    dst_fd = select_decision(target, framing_intent_id, default_intent=default_intent)

    src_sq = float(source.get("anamorphic_squeeze", 1.0)) or 1.0
    dst_sq = float(target.get("anamorphic_squeeze", 1.0)) or 1.0

    # Desqueezed display space: X_d = x_px * squeeze, y unchanged.
    src_w_d = src_fd["dimensions"]["width"] * src_sq
    dst_w_d = dst_fd["dimensions"]["width"] * dst_sq
    src_h = src_fd["dimensions"]["height"]
    dst_h = dst_fd["dimensions"]["height"]
    for fd, w, h in ((src_fd, src_w_d, src_h), (dst_fd, dst_w_d, dst_h)):
        if not (w and h):
            raise FDLError(
                f"framing decision {fd.get('id')!r} has degenerate dimensions"
            )

    ratio_w = dst_w_d / src_w_d
    scale_x = (src_sq / dst_sq) * ratio_w
    scale_y = dst_h / src_h
    offset_x = (
        dst_fd["anchor_point"]["x"] * dst_sq
        - src_fd["anchor_point"]["x"] * src_sq * ratio_w
    ) / dst_sq
    offset_y = dst_fd["anchor_point"]["y"] - src_fd["anchor_point"]["y"] * scale_y

    uniform = math.isclose(ratio_w, scale_y, rel_tol=_UNIFORM_TOLERANCE)
    return {
        "scale_x": scale_x,
        "scale_y": scale_y,
        "offset_x": offset_x,
        "offset_y": offset_y,
        "uniform": uniform,
    }


def map_point(transform, x, y):
    """Map a point through a transform; returns ``(x, y)``."""
    return (
        x * transform["scale_x"] + transform["offset_x"],
        y * transform["scale_y"] + transform["offset_y"],
    )


def map_rect(transform, dimensions, anchor_point):
    """Map an FDL rect (dimensions + anchor) through a transform.

    Returns ``(dimensions, anchor_point)`` in the target canvas's pixels.
    """
    x, y = map_point(transform, anchor_point["x"], anchor_point["y"])
    return (
        {
            "width": dimensions["width"] * transform["scale_x"],
            "height": dimensions["height"] * transform["scale_y"],
        },
        {"x": x, "y": y},
    )


def invert(transform):
    """The inverse transform (target pixels back to source pixels)."""
    sx, sy = transform["scale_x"], transform["scale_y"]
    if not (sx and sy):
        raise FDLError("transform is not invertible (zero scale)")
    return {
        "scale_x": 1.0 / sx,
        "scale_y": 1.0 / sy,
        "offset_x": -transform["offset_x"] / sx,
        "offset_y": -transform["offset_y"] / sy,
        "uniform": transform["uniform"],
    }
