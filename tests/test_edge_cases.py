# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright Contributors to the otio-fdl project

"""Regression tests for the review findings and edge-case gaps."""

import copy
import json

import opentimelineio as otio
import pytest

import otio_fdl
from conftest import A65

KEY = otio.schema.Clip.DEFAULT_MEDIA_KEY


# --- cross-timeline document copying (AnyDictionary validation) --------------

def test_copy_document_between_timelines(simple_timeline, a65_document):
    otio_fdl.attach_document(simple_timeline, a65_document)
    other = otio.schema.Timeline(name="other")
    # get_document returns a live AnyDictionary: it must still validate
    otio_fdl.attach_document(other, otio_fdl.get_document(simple_timeline))
    assert otio_fdl.extract_document(other) == a65_document


def test_validate_after_file_roundtrip(simple_timeline, a65_document, tmp_path):
    otio_fdl.attach_document(simple_timeline, a65_document)
    path = tmp_path / "cut.otio"
    otio.adapters.write_to_file(simple_timeline, str(path))
    reloaded = otio.adapters.read_from_file(str(path))
    otio_fdl.validate_fdl(otio_fdl.get_document(reloaded))  # must not raise


# --- malformed version field --------------------------------------------------

def test_version_string_raises_fdl_error():
    with pytest.raises(otio_fdl.FDLError, match="unsupported or missing"):
        otio_fdl.validate_fdl({"version": "2.0"})


# --- round rule enum strictness ----------------------------------------------

def test_round_unknown_enum_raises():
    with pytest.raises(otio_fdl.FDLError, match="unknown round 'even'"):
        otio_fdl.round_dimension(1608.75, {"even": "ture", "mode": "up"})
    with pytest.raises(otio_fdl.FDLError, match="unknown round 'mode'"):
        otio_fdl.round_dimension(1608.75, {"even": "even", "mode": "ceil"})


# --- id minting ---------------------------------------------------------------

LONG_CANVAS = {
    "label": "Long",
    "id": "sourcecanvasid_extralong",
    "source_canvas_id": "sourcecanvasid_extralong",
    "dimensions": {"width": 4000, "height": 3000},
    "anamorphic_squeeze": 1.0,
    "framing_decisions": [
        {
            "label": "one",
            "id": "sourcecanvasid_extralong-int1",
            "framing_intent_id": "int1",
            "dimensions": {"width": 3800, "height": 2000},
            "anchor_point": {"x": 100, "y": 500},
        },
        {
            "label": "two",
            "id": "sourcecanvasid_extralong-int2",
            "framing_intent_id": "int2",
            "dimensions": {"width": 3000, "height": 2600},
            "anchor_point": {"x": 500, "y": 200},
        },
    ],
}

LONG_TEMPLATE = {
    "label": "Pull",
    "id": "verylongtemplateid",
    "target_dimensions": {"width": 1920, "height": 1080},
    "target_anamorphic_squeeze": 1.0,
    "fit_source": "framing_decision.dimensions",
    "fit_method": "width",
}


def test_minted_ids_are_schema_valid_and_distinct():
    out1 = otio_fdl.apply_canvas_template(LONG_CANVAS, LONG_TEMPLATE, "int1")
    out2 = otio_fdl.apply_canvas_template(LONG_CANVAS, LONG_TEMPLATE, "int2")
    import re
    for out in (out1, out2):
        assert re.match(r"^[A-Za-z0-9_]+$", out["id"]) and len(out["id"]) <= 32
        fd_id = out["framing_decisions"][0]["id"]
        assert re.match(r"^[A-Za-z0-9_]+-[A-Za-z0-9_]+$", fd_id)
        assert len(fd_id) <= 65
    assert out1["framing_decisions"][0]["id"] != out2["framing_decisions"][0]["id"]


def test_caller_canvas_id_is_validated():
    with pytest.raises(otio_fdl.FDLError, match="not a valid FDL id"):
        otio_fdl.apply_canvas_template(
            LONG_CANVAS, LONG_TEMPLATE, "int1", canvas_id="X" * 40
        )
    with pytest.raises(otio_fdl.FDLError, match="not a valid FDL id"):
        otio_fdl.apply_canvas_template(
            LONG_CANVAS, LONG_TEMPLATE, "int1", canvas_id="bad-hyphen"
        )


def test_minted_canvas_revalidates_in_document():
    """A minted pull canvas inserted back into the document must pass the
    official schema — end-to-end guarantee that outputs are valid FDL."""
    document = json.loads(A65.read_text())
    canvas = document["contexts"][0]["canvases"][0]
    template = {
        "label": "VFX Pull",
        "id": "VXPULL01",
        "target_dimensions": {"width": 3840, "height": 2160},
        "target_anamorphic_squeeze": 1.0,
        "fit_source": "framing_decision.dimensions",
        "fit_method": "width",
        "preserve_from_source_canvas": "canvas.dimensions",
        "round": {"even": "even", "mode": "up"},
    }
    minted = otio_fdl.apply_canvas_template(canvas, template)
    document["contexts"][0]["canvases"].append(minted)
    document.setdefault("canvas_templates", []).append(template)
    otio_fdl.validate_fdl(document)  # must not raise


# --- pull_specs resilience ----------------------------------------------------

def test_dangling_link_does_not_abort_pull_list(simple_timeline):
    document = json.loads(
        (A65.parent / "A_5184x4320_2_20percentSafe.fdl").read_text()
    )
    otio_fdl.attach_document(simple_timeline, document)
    clips = {c.name: c for c in simple_timeline.find_clips()}
    otio_fdl.link(clips["shot010"].media_reference, "20220310")
    # stale link: canvas id that is not in the attached document
    clips["shot020"].media_reference.metadata["ascfdl"] = {"canvas_id": "gone"}

    specs = {s["clip"]: s for s in otio_fdl.pull_specs(simple_timeline)}

    assert specs["shot010"]["pull"]["dimensions"] == {"width": 6000, "height": 2700}
    assert specs["shot020"]["status"] == "error"
    assert "gone" in specs["shot020"]["error"]


# --- file matching: image sequences and encoded URLs -------------------------

def test_auto_link_image_sequence(simple_timeline, a65_document):
    document = copy.deepcopy(a65_document)
    document["contexts"][0]["clip_id"] = {
        "clip_name": "A004C012_230114_R1CB",
        "file": "A_plate.0001001.exr",
    }
    otio_fdl.attach_document(simple_timeline, document)
    clip = [c for c in simple_timeline.find_clips() if c.name == "shot010"][0]
    clip.media_reference = otio.schema.ImageSequenceReference(
        target_url_base="file:///plates/A_plate/",
        name_prefix="A_plate.",
        name_suffix=".exr",
        start_frame=1001,
        frame_zero_padding=7,
        rate=24,
    )

    report = otio_fdl.auto_link(simple_timeline)

    assert report["linked"] == [
        {"clip": "shot010", "ref": KEY, "canvas_id": "pXLM4OnA"}
    ]


def test_auto_link_percent_encoded_url(simple_timeline, a65_document):
    document = copy.deepcopy(a65_document)
    document["contexts"][0]["clip_id"] = {
        "clip_name": "A004C012_230114_R1CB",
        "file": "shot 010.exr",
    }
    otio_fdl.attach_document(simple_timeline, document)
    clip = [c for c in simple_timeline.find_clips() if c.name == "shot010"][0]
    clip.media_reference = otio.schema.ExternalReference(
        target_url="file:///plates/shot%20010.exr"
    )

    report = otio_fdl.auto_link(simple_timeline)

    assert report["linked"] == [
        {"clip": "shot010", "ref": KEY, "canvas_id": "pXLM4OnA"}
    ]


# --- multi-reference clips: report is per-reference ---------------------------

def test_auto_link_multi_reference_reports_which_ref(simple_timeline, a65_document):
    document = copy.deepcopy(a65_document)
    document["contexts"][0]["clip_id"] = {
        "clip_name": "A004C012_230114_R1CB",
        "file": "A_plate.exr",
    }
    otio_fdl.attach_document(simple_timeline, document)
    clip = [c for c in simple_timeline.find_clips() if c.name == "shot010"][0]
    refs = clip.media_references()
    refs["highres"] = otio.schema.ExternalReference(
        target_url="file:///ocf/A_plate.exr"
    )
    clip.set_media_references(refs, KEY)
    # active reference stays the proxy, which matches nothing

    report = otio_fdl.auto_link(simple_timeline)

    assert report["linked"] == [
        {"clip": "shot010", "ref": "highres", "canvas_id": "pXLM4OnA"}
    ]
    # the report is per-reference, so it is visible that the ACTIVE
    # reference is not the one that linked
    assert otio_fdl.canvas_for(clip.media_reference, simple_timeline) is None
    assert otio_fdl.canvas_for(
        clip.media_references()["highres"], simple_timeline
    )["id"] == "pXLM4OnA"


# --- explicit target box + alignment (spec 7.4.4 / 7.4.8) --------------------

def test_alignment_bottom_in_taller_explicit_target():
    """Scen3-style: fit width into an explicitly taller target box, aligned
    bottom — the canvas keeps the full target height and the framing sits
    at the bottom (alignment is no longer a silent no-op)."""
    canvas = {
        "label": "src", "id": "src01", "source_canvas_id": "src01",
        "dimensions": {"width": 3840, "height": 2160},
        "anamorphic_squeeze": 1.0,
        "framing_decisions": [{
            "label": "f", "id": "src01-i1", "framing_intent_id": "i1",
            "dimensions": {"width": 3840, "height": 2160},
            "anchor_point": {"x": 0, "y": 0},
        }],
    }
    template = {
        "label": "T", "id": "T01",
        "target_dimensions": {"width": 3840, "height": 3160},
        "target_anamorphic_squeeze": 1.0,
        "fit_source": "framing_decision.dimensions",
        "fit_method": "width",
        "alignment_method_vertical": "bottom",
        "alignment_method_horizontal": "right",
    }
    out = otio_fdl.apply_canvas_template(canvas, template)
    assert out["dimensions"] == {"width": 3840, "height": 3160}
    fd = out["framing_decisions"][0]
    assert fd["anchor_point"]["y"] == pytest.approx(1000)  # 3160 - 2160
    # padding above the image: effective area declared
    assert out["effective_dimensions"]["height"] == 2160


def test_fill_overflow_is_cut_not_grown():
    canvas = {
        "label": "src", "id": "src02", "source_canvas_id": "src02",
        "dimensions": {"width": 4000, "height": 3000},
        "anamorphic_squeeze": 1.0,
        "framing_decisions": [{
            "label": "f", "id": "src02-i1", "framing_intent_id": "i1",
            "dimensions": {"width": 4000, "height": 3000},  # 4:3
            "anchor_point": {"x": 0, "y": 0},
        }],
    }
    template = {
        "label": "T", "id": "T02",
        "target_dimensions": {"width": 3840, "height": 2160},
        "target_anamorphic_squeeze": 1.0,
        "fit_source": "framing_decision.dimensions",
        "fit_method": "fill",
    }
    out = otio_fdl.apply_canvas_template(canvas, template)
    # fill: canvas stays at target; the 4:3 source's overflow is CUT OFF
    # (spec 7.4.7) — the emitted decision is clipped to the canvas, never
    # negative (the schema forbids negative anchors)
    assert out["dimensions"] == {"width": 3840, "height": 2160}
    fd = out["framing_decisions"][0]
    assert fd["dimensions"]["height"] == pytest.approx(2160)
    assert fd["anchor_point"]["y"] == pytest.approx(0)


# --- MissingReference carries links too --------------------------------------

def test_missing_reference_links(simple_timeline, a65_document):
    otio_fdl.attach_document(simple_timeline, a65_document)
    clip = [c for c in simple_timeline.find_clips() if c.name == "shot010"][0]
    clip.media_reference = otio.schema.MissingReference()
    otio_fdl.link(clip.media_reference, "pXLM4OnA", timeline=simple_timeline)
    canvas = otio_fdl.canvas_for(clip.media_reference, simple_timeline)
    assert canvas["id"] == "pXLM4OnA"


# --- industry-research protections -------------------------------------------

def test_duplicate_canvas_ids_rejected(simple_timeline, a65_document):
    """ascmitc/fdl#32: cross-context id uniqueness is ambiguous in the
    spec, but our id-based linking requires it."""
    document = copy.deepcopy(a65_document)
    document["contexts"].append(
        {
            "label": "B cam",
            "canvases": [copy.deepcopy(document["contexts"][0]["canvases"][0])],
        }
    )
    with pytest.raises(otio_fdl.FDLError, match="duplicate canvas id"):
        otio_fdl.attach_document(simple_timeline, document, validate=False)


def test_negative_anchor_gets_version_hint(a65_document):
    """ascmitc/fdl#42/#45: a 2.0-legal negative anchor fails the 2.0.1
    schema — the error must diagnose the version split, not just say
    'invalid'."""
    document = copy.deepcopy(a65_document)
    fd = document["contexts"][0]["canvases"][0]["framing_decisions"][0]
    fd["anchor_point"]["x"] = -120.0
    with pytest.raises(otio_fdl.FDLError, match="ascmitc/fdl#42"):
        otio_fdl.validate_fdl(document)


def test_fill_minted_canvas_is_schema_valid(simple_timeline, a65_document):
    """The clipped fill output must revalidate inside a document."""
    document = copy.deepcopy(a65_document)
    template = {
        "label": "Fill", "id": "FILL01",
        "target_dimensions": {"width": 3840, "height": 2160},
        "target_anamorphic_squeeze": 1.0,
        "fit_source": "framing_decision.dimensions",
        "fit_method": "fill",
    }
    canvas = document["contexts"][0]["canvases"][0]
    minted = otio_fdl.apply_canvas_template(canvas, template)
    document["contexts"][0]["canvases"].append(minted)
    document.setdefault("canvas_templates", []).append(template)
    otio_fdl.validate_fdl(document)  # must not raise


def test_duplicate_clip_names_stay_distinct(simple_timeline, a65_document):
    document = copy.deepcopy(a65_document)
    document["contexts"][0]["clip_id"] = {"clip_name": "shot010"}
    otio_fdl.attach_document(simple_timeline, document)
    # rename the second clip to collide with the first
    clips = list(simple_timeline.find_clips())
    clips[1].name = "shot010"

    report = otio_fdl.auto_link(simple_timeline)

    assert len(report["linked"]) == 2  # one row per clip, no collapse
    assert all(r["canvas_id"] == "pXLM4OnA" for r in report["linked"])


def test_matching_context_with_no_canvases_is_unmatched(
    simple_timeline, a65_document
):
    document = copy.deepcopy(a65_document)
    document["contexts"][0]["clip_id"] = {"clip_name": "shot010"}
    document["contexts"][0]["canvases"] = []
    otio_fdl.attach_document(simple_timeline, document, validate=False)

    report = otio_fdl.auto_link(simple_timeline)

    # the clip must not vanish: no canvases means it stays unmatched
    assert "shot010" in report["unmatched"]


def test_chooser_return_must_be_a_candidate(simple_timeline, a65_document):
    document = copy.deepcopy(a65_document)
    document["contexts"][0]["clip_id"] = {"clip_name": "shot010"}
    second = copy.deepcopy(document["contexts"][0]["canvases"][0])
    second["id"] = "second01"
    document["contexts"][0]["canvases"].append(second)
    otio_fdl.attach_document(simple_timeline, document, validate=False)

    with pytest.raises(otio_fdl.FDLError, match="not among"):
        otio_fdl.auto_link(
            simple_timeline, choose=lambda mr, c: {"id": "not_in_document"}
        )


def test_empty_sequence_pattern_matches_nothing(simple_timeline, a65_document):
    """Regression: default empty prefix/suffix must not match every file."""
    document = copy.deepcopy(a65_document)
    document["contexts"][0]["clip_id"] = {
        "clip_name": "A004C012_230114_R1CB",
        "file": "totally_unrelated.mov",
    }
    otio_fdl.attach_document(simple_timeline, document)
    clip = [c for c in simple_timeline.find_clips() if c.name == "shot010"][0]
    clip.media_reference = otio.schema.ImageSequenceReference(
        target_url_base="file:///plates/B_roll/",
        start_frame=1001,
        rate=24,
    )

    report = otio_fdl.auto_link(simple_timeline)

    assert report["linked"] == []
    assert "shot010" in report["unmatched"]
