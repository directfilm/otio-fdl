# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright Contributors to the otio-fdl project

"""Canvas template application, validated two ways.

Primary ground truth: the numeric worked examples in ASC FDL spec v2.0.1
sections 7.4.9-7.4.12. Second axis: the ASC's published VFX-pull fixtures
(ascmitc/fdl resources/FDL), whose result canvases correspond to the
common-container recipe the spec's 7.4 prose describes (normalize all
sources into one delivery container: maximum_dimensions + pad_to_maximum).
"""

import copy
import json

import pytest

import otio_fdl
from conftest import FIXTURES


# The spec's own worked example source (sections 7.4.9-7.4.11): a 4448x3096
# canvas whose framing decision is 4004x2252. The spec does not give the
# decision's anchor; centered is used (222, 422) - canvas-dimension results
# below do not depend on it.
SPEC_CANVAS = {
    "label": "Example",
    "id": "spec01",
    "source_canvas_id": "spec01",
    "dimensions": {"width": 4448, "height": 3096},
    "anamorphic_squeeze": 1.0,
    "framing_decisions": [
        {
            "label": "spec",
            "id": "spec01-int1",
            "framing_intent_id": "int1",
            "dimensions": {"width": 4004, "height": 2252},
            "anchor_point": {"x": 222, "y": 422},
        }
    ],
}

SPEC_TEMPLATE = {
    "label": "VFX Pull",
    "id": "tpl01",
    "target_dimensions": {"width": 3840, "height": 2160},
    "target_anamorphic_squeeze": 1.0,
    "fit_source": "framing_decision.dimensions",
    "fit_method": "width",
    "preserve_from_source_canvas": "canvas.dimensions",
}


# --- Spec 7.4.12: the rounding table, verbatim -------------------------------

@pytest.mark.parametrize(
    "rule,expected",
    [
        ({"even": "even", "mode": "round"}, 1608),
        ({"even": "even", "mode": "up"}, 1610),
        ({"even": "even", "mode": "down"}, 1608),
        ({"even": "whole", "mode": "round"}, 1609),
        ({"even": "whole", "mode": "up"}, 1609),
        ({"even": "whole", "mode": "down"}, 1608),
    ],
)
def test_round_table_from_spec(rule, expected):
    assert otio_fdl.round_dimension(1608.75, rule) == expected


def test_round_exact_int_not_bumped_by_up():
    assert otio_fdl.round_dimension(2700.0000000001, {"even": "even", "mode": "up"}) == 2700


# --- Spec 7.4.9: preserve_from_source_canvas -> 4266 x 2970 ------------------

def test_spec_preserve_expands_canvas():
    out = otio_fdl.apply_canvas_template(SPEC_CANVAS, SPEC_TEMPLATE)
    assert out["dimensions"] == {"width": 4266, "height": 2970}
    fd = out["framing_decisions"][0]
    assert fd["dimensions"]["width"] == pytest.approx(3840)
    # fit width: height tracks the source aspect (4004x2252 is not exactly
    # 16:9), per 7.4.7 "dynamically adjusted" — 2252 * 3840/4004 = 2159.76
    assert fd["dimensions"]["height"] == pytest.approx(2159.76, abs=0.01)


def test_spec_preserve_framing_decision_only_stays_at_target():
    template = dict(SPEC_TEMPLATE, preserve_from_source_canvas="framing_decision.dimensions")
    out = otio_fdl.apply_canvas_template(SPEC_CANVAS, template)
    assert out["dimensions"] == {"width": 3840, "height": 2160}


# --- Spec 7.4.10: maximum_dimensions crops, never scales ---------------------

def test_spec_maximum_crops_to_4096x2160():
    template = dict(SPEC_TEMPLATE, maximum_dimensions={"width": 4096, "height": 2160})
    out = otio_fdl.apply_canvas_template(SPEC_CANVAS, template)
    assert out["dimensions"] == {"width": 4096, "height": 2160}
    # cropping must not rescale the framing decision
    fd = out["framing_decisions"][0]
    assert fd["dimensions"]["width"] == pytest.approx(3840)


def test_spec_maximum_no_crop_when_not_exceeded():
    template = dict(SPEC_TEMPLATE, maximum_dimensions={"width": 5000, "height": 3496})
    out = otio_fdl.apply_canvas_template(SPEC_CANVAS, template)
    assert out["dimensions"] == {"width": 4266, "height": 2970}


# --- Spec 7.4.11: pad_to_maximum -> 5000 x 3496 ------------------------------

def test_spec_pad_to_maximum():
    template = dict(
        SPEC_TEMPLATE,
        maximum_dimensions={"width": 5000, "height": 3496},
        pad_to_maximum=True,
    )
    out = otio_fdl.apply_canvas_template(SPEC_CANVAS, template)
    assert out["dimensions"] == {"width": 5000, "height": 3496}
    # padding means inactive pixels: effective area must be declared (7.4.11)
    assert "effective_dimensions" in out
    assert out["effective_dimensions"]["width"] < 5000


# --- ASC published fixtures: embedded template, spec-literal application -----

def test_fixture_a_embedded_template():
    """A (5184x4320, squeeze 2.0): preserve canvas -> 6480x2700, max-crop 6000."""
    doc = json.loads((FIXTURES / "A_5184x4320_2_20percentSafe.fdl").read_text())
    canvas = doc["contexts"][0]["canvases"][0]
    out = otio_fdl.apply_canvas_template(canvas, doc["canvas_templates"][0])
    assert out["dimensions"] == {"width": 6000, "height": 2700}
    fd = out["framing_decisions"][0]
    assert fd["dimensions"]["width"] == pytest.approx(3840)
    assert fd["dimensions"]["height"] == pytest.approx(2160)
    assert fd["anchor_point"]["x"] == pytest.approx(1080)
    assert fd["anchor_point"]["y"] == pytest.approx(270)
    assert out["anamorphic_squeeze"] == 1.0
    assert out["source_canvas_id"] == "20220310"


# --- ASC published result canvases: the common-container recipe --------------

@pytest.mark.parametrize(
    "name",
    [
        "A_5184x4320_2_20percentSafe",
        "B_5184x4320_133_10percentSafe",
        "C_6560x3102_Spherical",
    ],
)
def test_fixture_result_canvases_via_common_container(name):
    """The published pull canvases (4800x2700, FD 3840x2160 centered) are the
    embedded template normalized to a common container: maximum 4800x2700,
    pad_to_maximum true. Three sources (squeeze 2.0 / 1.33 / spherical), one
    delivery raster."""
    doc = json.loads((FIXTURES / f"{name}.fdl").read_text())
    source = doc["contexts"][0]["canvases"][0]
    published = doc["contexts"][0]["canvases"][1]
    template = dict(
        doc["canvas_templates"][0],
        maximum_dimensions={"width": 4800, "height": 2700},
        pad_to_maximum=True,
    )

    out = otio_fdl.apply_canvas_template(source, template)

    assert out["dimensions"] == published["dimensions"]  # 4800 x 2700
    fd, pub = out["framing_decisions"][0], published["framing_decisions"][0]
    assert fd["dimensions"]["width"] == pytest.approx(pub["dimensions"]["width"], abs=0.25)
    assert fd["dimensions"]["height"] == pytest.approx(pub["dimensions"]["height"], abs=0.25)
    assert fd["anchor_point"]["x"] == pytest.approx(pub["anchor_point"]["x"], abs=0.25)
    assert fd["anchor_point"]["y"] == pytest.approx(pub["anchor_point"]["y"], abs=0.25)


def test_fixture_a_common_container_protection_exact():
    """A's numbers are exact: protection fills the pull canvas precisely.

    (B and C record protection as the full pull canvas too, but their source
    protections are canvas-clipped, so spec-literal scaling gives a smaller
    region; only A's stored values are reproducible bit-for-bit.)"""
    doc = json.loads((FIXTURES / "A_5184x4320_2_20percentSafe.fdl").read_text())
    template = dict(
        doc["canvas_templates"][0],
        maximum_dimensions={"width": 4800, "height": 2700},
        pad_to_maximum=True,
    )
    out = otio_fdl.apply_canvas_template(doc["contexts"][0]["canvases"][0], template)
    fd = out["framing_decisions"][0]
    assert fd["anchor_point"] == {"x": pytest.approx(480), "y": pytest.approx(270)}
    assert fd["protection_dimensions"]["width"] == pytest.approx(4800)
    assert fd["protection_dimensions"]["height"] == pytest.approx(2700)
    assert fd["protection_anchor_point"]["x"] == pytest.approx(0)
    assert fd["protection_anchor_point"]["y"] == pytest.approx(0)


# --- Selection and error paths ----------------------------------------------

def test_missing_intent_raises():
    with pytest.raises(otio_fdl.FDLError, match="no decision for intent"):
        otio_fdl.apply_canvas_template(SPEC_CANVAS, SPEC_TEMPLATE, framing_intent_id="zz")


def test_missing_protection_selector_raises():
    template = dict(SPEC_TEMPLATE, fit_source="framing_decision.protection_dimensions")
    with pytest.raises(otio_fdl.FDLError, match="no protection"):
        otio_fdl.apply_canvas_template(SPEC_CANVAS, template)


def test_target_squeeze_zero_preserves_source_squeeze():
    canvas = copy.deepcopy(SPEC_CANVAS)
    canvas["anamorphic_squeeze"] = 2.0
    template = dict(SPEC_TEMPLATE, target_anamorphic_squeeze=0)
    out = otio_fdl.apply_canvas_template(canvas, template)
    assert out["anamorphic_squeeze"] == 2.0
    # no desqueeze happened: same result as the squeeze-1.0 spec example
    assert out["dimensions"] == {"width": 4266, "height": 2970}


# --- pull_specs: the per-shot pull list --------------------------------------

def test_pull_specs_end_to_end(simple_timeline):
    doc = json.loads((FIXTURES / "A_5184x4320_2_20percentSafe.fdl").read_text())
    otio_fdl.attach_document(simple_timeline, doc)
    clip = [c for c in simple_timeline.find_clips() if c.name == "shot010"][0]
    otio_fdl.link(clip.media_reference, "20220310", timeline=simple_timeline)

    specs = otio_fdl.pull_specs(simple_timeline)

    by_clip = {s["clip"]: s for s in specs}
    assert by_clip["shot020"] == {"clip": "shot020", "status": "unlinked"}
    pull = by_clip["shot010"]["pull"]
    assert by_clip["shot010"]["canvas_id"] == "20220310"
    assert pull["dimensions"] == {"width": 6000, "height": 2700}
    assert pull["label"] == "VFX Pull"


def test_pull_specs_requires_unambiguous_template(simple_timeline, a65_document):
    otio_fdl.attach_document(simple_timeline, a65_document)  # no templates
    with pytest.raises(otio_fdl.FDLError, match="0 canvas templates"):
        otio_fdl.pull_specs(simple_timeline)
