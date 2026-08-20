# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright Contributors to the otio-fdl project

"""Apply FDL canvas templates: the VFX pull-spec machinery.

Implements ASC FDL v2.0.1 spec section 7.4 ("Canvas Template"): given a
source canvas (with framing decisions) and a canvas template, produce the
new output canvas — the actual pull raster and where the framing lands in
it. Order of operations follows section 7.4.1 and the normative
desqueeze-then-scale rule of sections 7.4.5/7.4.7.

Where the spec delegates detail to the (unpublished) Implementation Guide,
choices are documented inline: explicit target_dimensions are authoritative
(7.4.4 says the free axis "may be calculated", i.e. when not supplied);
rounding pad/crop is distributed per the template's alignment gravity; and
a maximum_dimensions crop is centered on the target box, mirroring
pad_to_maximum's "target_dimensions should center-align to the resulting
canvas".
"""

from __future__ import annotations

import hashlib
import math
import re

from .core import FDLError, canvas_for, get_document, root_canvas, select_decision

_ID_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
_ID_MAX = 32  # fdl_id; framing-decision ids allow 65 (two ids + hyphen)


def round_dimension(value, rule=None):
    """Round one canvas dimension per the template ``round`` rule (7.4.12)."""
    rule = rule or {}
    even = rule.get("even", "even")
    mode = rule.get("mode", "up")
    if even not in ("even", "whole"):
        raise FDLError(f"unknown round 'even' value {even!r}")
    if mode not in ("up", "down", "round"):
        raise FDLError(f"unknown round 'mode' value {mode!r}")
    value = round(value, 9)  # shed float noise so exact ints survive "up"
    if even == "even":
        half = value / 2.0
        if mode == "up":
            return int(math.ceil(half)) * 2
        if mode == "down":
            return int(math.floor(half)) * 2
        return int(math.floor(half + 0.5)) * 2
    if mode == "up":
        return int(math.ceil(value))
    if mode == "down":
        return int(math.floor(value))
    return int(math.floor(value + 0.5))


def _valid_id(candidate, what):
    if not _ID_PATTERN.match(candidate or "") or len(candidate) > _ID_MAX:
        raise FDLError(
            f"{what} {candidate!r} is not a valid FDL id"
            f" (alphanumeric/underscore, 1-{_ID_MAX} chars)"
        )
    return candidate


def _mint_canvas_id(template, canvas):
    """A deterministic, schema-valid id for the minted canvas."""
    composite = f"{template.get('id', 'tpl')}_{canvas.get('id', 'src')}"
    composite = re.sub(r"[^A-Za-z0-9_]", "_", composite)
    if len(composite) <= _ID_MAX:
        return composite
    digest = hashlib.md5(composite.encode()).hexdigest()[:7]
    return f"{composite[:_ID_MAX - 8].rstrip('_')}_{digest}"


def _region(canvas, decision, selector):
    """(dimensions, anchor) of a fit/preserve selector, in source pixels."""
    if selector == "framing_decision.dimensions":
        return decision["dimensions"], decision["anchor_point"]
    if selector == "framing_decision.protection_dimensions":
        if "protection_dimensions" not in decision:
            raise FDLError(
                f"framing decision {decision.get('id')!r} has no protection"
            )
        return decision["protection_dimensions"], decision["protection_anchor_point"]
    if selector == "canvas.dimensions":
        return canvas["dimensions"], {"x": 0, "y": 0}
    if selector == "canvas.effective_dimensions":
        if "effective_dimensions" not in canvas:
            raise FDLError(
                f"canvas {canvas.get('id')!r} has no effective_dimensions"
            )
        return canvas["effective_dimensions"], canvas["effective_anchor_point"]
    raise FDLError(f"unknown fit/preserve selector {selector!r}")


def apply_canvas_template(canvas, template, framing_intent_id=None, canvas_id=None):
    """Mint the output canvas for ``canvas`` under ``template`` (spec 7.4).

    Returns a new canvas dict (canvas dimensions int, decision geometry
    float, matching the schema's types). ``framing_intent_id`` picks the
    source framing decision (first one when omitted); ``canvas_id`` names
    the new canvas (default: derived from template and source ids).
    """
    decision = select_decision(canvas, framing_intent_id)

    # -- 1. Normalize: desqueeze factor (widths only), then scale factor.
    source_sq = float(canvas.get("anamorphic_squeeze", 1.0))
    target_sq = float(template.get("target_anamorphic_squeeze", 1.0))
    out_sq = source_sq if target_sq == 0 else target_sq
    f = 1.0 if target_sq == 0 else source_sq / target_sq

    fit_dims, fit_anchor = _region(canvas, decision, template["fit_source"])
    target = template["target_dimensions"]
    tw, th = target["width"], target["height"]

    method = template["fit_method"]
    if method == "width":
        s = tw / (fit_dims["width"] * f)
    elif method == "height":
        s = th / fit_dims["height"]
    elif method == "fit_all":
        s = min(tw / (fit_dims["width"] * f), th / fit_dims["height"])
    elif method == "fill":
        s = max(tw / (fit_dims["width"] * f), th / fit_dims["height"])
    else:
        raise FDLError(f"unknown fit_method {method!r}")

    def sx(w):  # source width -> output pixels
        return w * f * s

    def sy(h):
        return h * s

    # -- 2. Scaled fit region F, positioned in the target box T (7.4.8).
    # Explicit target_dimensions are authoritative for T (7.4.4); the
    # canvas extent below still guarantees the whole fit source survives
    # for every method except fill, whose overflow is cut off (7.4.7).
    Fw, Fh = sx(fit_dims["width"]), sy(fit_dims["height"])
    Tw, Th = float(tw), float(th)
    ah = template.get("alignment_method_horizontal", "center")
    av = template.get("alignment_method_vertical", "center")
    if ah not in ("left", "center", "right"):
        raise FDLError(f"unknown alignment_method_horizontal {ah!r}")
    if av not in ("top", "center", "bottom"):
        raise FDLError(f"unknown alignment_method_vertical {av!r}")
    Tx, Ty = 0.0, 0.0
    Fx = {"left": 0.0, "center": (Tw - Fw) / 2, "right": Tw - Fw}[ah]
    Fy = {"top": 0.0, "center": (Th - Fh) / 2, "bottom": Th - Fh}[av]

    # -- 3. Canvas extent: T, plus the whole fit source (except fill),
    # plus the preserve region (7.4.9).
    cx0, cy0, cx1, cy1 = 0.0, 0.0, Tw, Th
    if method != "fill":
        cx0, cy0 = min(cx0, Fx), min(cy0, Fy)
        cx1, cy1 = max(cx1, Fx + Fw), max(cy1, Fy + Fh)
    preserve = template.get("preserve_from_source_canvas")
    if preserve:
        p_dims, p_anchor = _region(canvas, decision, preserve)
        px = Fx - sx(fit_anchor["x"] - p_anchor["x"])
        py = Fy - sy(fit_anchor["y"] - p_anchor["y"])
        cx0, cy0 = min(cx0, px), min(cy0, py)
        cx1 = max(cx1, px + sx(p_dims["width"]))
        cy1 = max(cy1, py + sy(p_dims["height"]))
    Cw, Ch = cx1 - cx0, cy1 - cy0
    Fx, Fy, Tx, Ty = Fx - cx0, Fy - cy0, Tx - cx0, Ty - cy0

    maximum = template.get("maximum_dimensions")
    pad_to_maximum = bool(template.get("pad_to_maximum")) and bool(maximum)

    # -- 4. Round canvas dimensions (7.4.12; skipped when padding to max).
    if not pad_to_maximum:
        rule = template.get("round")
        rw, rh = round_dimension(Cw, rule), round_dimension(Ch, rule)
        # distribute the pad/crop delta by alignment gravity (center: split)
        dx = {"left": 0.0, "center": (rw - Cw) / 2, "right": rw - Cw}[ah]
        dy = {"top": 0.0, "center": (rh - Ch) / 2, "bottom": rh - Ch}[av]
        Fx, Fy, Tx, Ty = Fx + dx, Fy + dy, Tx + dx, Ty + dy
        Cw, Ch = float(rw), float(rh)

    # -- 5. maximum_dimensions: crop, never scale (7.4.10), the crop window
    # centered on the target box; then pad_to_maximum expands the canvas to
    # the maximum with the target box center-aligned (7.4.11).
    if maximum:
        if Cw > maximum["width"]:
            lo = min(max(Tx + Tw / 2 - maximum["width"] / 2, 0.0), Cw - maximum["width"])
            Fx, Tx, Cw = Fx - lo, Tx - lo, float(maximum["width"])
        if Ch > maximum["height"]:
            lo = min(max(Ty + Th / 2 - maximum["height"] / 2, 0.0), Ch - maximum["height"])
            Fy, Ty, Ch = Fy - lo, Ty - lo, float(maximum["height"])
    if pad_to_maximum:
        dx = (maximum["width"] - Tw) / 2 - Tx
        dy = (maximum["height"] - Th) / 2 - Ty
        Fx, Fy, Tx, Ty = Fx + dx, Fy + dy, Tx + dx, Ty + dy
        Cw, Ch = float(maximum["width"]), float(maximum["height"])

    # -- Compose the output canvas.
    def place(dims, anchor):
        """Map a source-canvas region into output coordinates."""
        return (
            {"width": sx(dims["width"]), "height": sy(dims["height"])},
            {
                "x": Fx + sx(anchor["x"] - fit_anchor["x"]),
                "y": Fy + sy(anchor["y"] - fit_anchor["y"]),
            },
        )

    if canvas_id is not None:
        new_id = _valid_id(canvas_id, "canvas_id")
    else:
        new_id = _mint_canvas_id(template, canvas)
    intent_part = re.sub(
        r"[^A-Za-z0-9_]", "_", decision.get("framing_intent_id") or "fd"
    )[:_ID_MAX] or "fd"
    fd_dims, fd_anchor = place(decision["dimensions"], decision["anchor_point"])
    new_decision = {
        "label": decision.get("label", ""),
        "id": f"{new_id}-{intent_part}",  # <=65: two ids plus hyphen
        "framing_intent_id": decision.get("framing_intent_id"),
        "dimensions": fd_dims,
        "anchor_point": fd_anchor,
    }
    if "protection_dimensions" in decision:
        p_dims, p_anchor = place(
            decision["protection_dimensions"], decision["protection_anchor_point"]
        )
        new_decision["protection_dimensions"] = p_dims
        new_decision["protection_anchor_point"] = p_anchor

    out = {
        "label": template.get("label", ""),
        "id": new_id,
        "source_canvas_id": canvas.get("id"),
        "dimensions": {"width": int(round(Cw)), "height": int(round(Ch))},
        "anamorphic_squeeze": out_sq,
        "framing_decisions": [new_decision],
    }

    # Active image area: the scaled source canvas (or its effective area)
    # clipped to the output; emitted when padding leaves inactive pixels
    # (7.4.6 / 7.4.9 / 7.4.11).
    if canvas.get("effective_dimensions"):
        e_dims, e_anchor = place(
            canvas["effective_dimensions"], canvas["effective_anchor_point"]
        )
    else:
        e_dims, e_anchor = place(canvas["dimensions"], {"x": 0, "y": 0})
    ex0, ey0 = max(e_anchor["x"], 0.0), max(e_anchor["y"], 0.0)
    ex1 = min(e_anchor["x"] + e_dims["width"], Cw)
    ey1 = min(e_anchor["y"] + e_dims["height"], Ch)
    if round(ex1 - ex0) != round(Cw) or round(ey1 - ey0) != round(Ch):
        out["effective_dimensions"] = {
            "width": int(round(ex1 - ex0)),
            "height": int(round(ey1 - ey0)),
        }
        out["effective_anchor_point"] = {"x": ex0, "y": ey0}
    return out


def pull_specs(timeline, template_id=None, framing_intent_id=None, from_root=True):
    """Per-shot pull list for a timeline carrying an FDL document.

    For every clip, resolves the canvas linked to its *active* media
    reference and applies the document's canvas template (``template_id``,
    or the sole template when omitted). With ``from_root`` (the default),
    the template is applied to the ROOT of the canvas's derivation chain —
    pulls come from the camera original even when the timeline references
    offline/editorial media whose canvas is derived from it.

    Returns one entry per clip: ``{"clip", "canvas_id", "pulled_from",
    "pull"}``; clips without a canvas reference yield ``{"clip",
    "status": "unlinked"}`` and per-clip resolution failures (e.g. a
    canvas id dangling after a document swap) yield ``{"clip",
    "status": "error", "error": ...}`` without aborting the rest.
    """
    document = get_document(timeline)
    if document is None:
        raise FDLError("timeline carries no FDL document")
    templates = list(document.get("canvas_templates", []))
    if template_id is None:
        if len(templates) != 1:
            raise FDLError(
                f"document has {len(templates)} canvas templates;"
                " pass template_id to choose one"
            )
        template = templates[0]
    else:
        try:
            template = next(t for t in templates if t.get("id") == template_id)
        except StopIteration:
            raise FDLError(f"no canvas template with id {template_id!r}")

    specs = []
    for clip in timeline.find_clips():
        try:
            canvas = canvas_for(clip.media_reference, timeline)
            if canvas is None:
                specs.append({"clip": clip.name, "status": "unlinked"})
                continue
            source = (
                root_canvas(document, canvas["id"]) if from_root else canvas
            )
            pull = apply_canvas_template(
                source, template, framing_intent_id=framing_intent_id
            )
        except FDLError as exc:
            specs.append({"clip": clip.name, "status": "error", "error": str(exc)})
            continue
        specs.append(
            {
                "clip": clip.name,
                "canvas_id": canvas["id"],
                "pulled_from": source["id"],
                "pull": pull,
            }
        )
    return specs
