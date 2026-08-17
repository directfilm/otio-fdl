# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright Contributors to the otio-fdl project

"""Canvas references: explicit link, clip_id auto-link, resolution."""

import copy

import pytest

import otio_fdl


A65_CANVAS = "pXLM4OnA"
A65_INTENT = "fiWILIY0"


def test_explicit_link_and_resolve(simple_timeline, a65_document):
    otio_fdl.attach_document(simple_timeline, a65_document)
    clip = list(simple_timeline.find_clips())[0]

    otio_fdl.link(clip.media_reference, A65_CANVAS, timeline=simple_timeline)

    canvas = otio_fdl.canvas_for(clip.media_reference, simple_timeline)
    assert canvas["label"] == "Open Gate 6.5K"
    assert canvas["dimensions"] == {"width": 6560, "height": 3100}


def test_link_rejects_unknown_canvas(simple_timeline, a65_document):
    otio_fdl.attach_document(simple_timeline, a65_document)
    clip = list(simple_timeline.find_clips())[0]
    with pytest.raises(otio_fdl.FDLError, match="not present"):
        otio_fdl.link(clip.media_reference, "nope", timeline=simple_timeline)


def test_unlinked_reference_resolves_to_none(simple_timeline, a65_document):
    otio_fdl.attach_document(simple_timeline, a65_document)
    clip = list(simple_timeline.find_clips())[0]
    assert otio_fdl.canvas_for(clip.media_reference, simple_timeline) is None
    assert (
        otio_fdl.framing_decision_for(clip.media_reference, simple_timeline)
        is None
    )


def test_framing_decision_uses_default_intent(simple_timeline, a65_document):
    otio_fdl.attach_document(simple_timeline, a65_document)
    clip = list(simple_timeline.find_clips())[0]
    otio_fdl.link(clip.media_reference, A65_CANVAS)

    decision = otio_fdl.framing_decision_for(
        clip.media_reference, simple_timeline
    )
    assert decision["framing_intent_id"] == A65_INTENT
    assert decision["dimensions"]["width"] == pytest.approx(3450.951)

    explicit = otio_fdl.framing_decision_for(
        clip.media_reference, simple_timeline, framing_intent_id=A65_INTENT
    )
    assert explicit == decision

    assert (
        otio_fdl.framing_decision_for(
            clip.media_reference, simple_timeline, framing_intent_id="absent"
        )
        is None
    )


def test_auto_link_by_clip_name(simple_timeline, a65_document):
    document = copy.deepcopy(a65_document)
    document["contexts"][0]["clip_id"] = {"clip_name": "shot010"}
    otio_fdl.attach_document(simple_timeline, document)

    report = otio_fdl.auto_link(simple_timeline)

    assert report["linked"] == ["shot010"]
    assert report["unmatched"] == ["shot020"]
    assert report["ambiguous"] == []

    shot010 = [c for c in simple_timeline.find_clips() if c.name == "shot010"][0]
    canvas = otio_fdl.canvas_for(shot010.media_reference, simple_timeline)
    assert canvas["id"] == A65_CANVAS


def test_auto_link_by_file(simple_timeline, a65_document):
    # The official schema requires clip_name inside clip_id; use a name that
    # matches no timeline clip so the file field does the matching.
    document = copy.deepcopy(a65_document)
    document["contexts"][0]["clip_id"] = {
        "clip_name": "A004C012_230114_R1CB",
        "file": "shot020_opengate.exr",
    }
    otio_fdl.attach_document(simple_timeline, document)

    report = otio_fdl.auto_link(simple_timeline)

    assert report["linked"] == ["shot020"]
    assert "shot010" in report["unmatched"]


def test_auto_link_ambiguous_multi_canvas(simple_timeline, a65_document):
    document = copy.deepcopy(a65_document)
    document["contexts"][0]["clip_id"] = {"clip_name": "shot010"}
    second = copy.deepcopy(document["contexts"][0]["canvases"][0])
    second["id"] = "second01"
    second["label"] = "Second Canvas"
    document["contexts"][0]["canvases"].append(second)
    otio_fdl.attach_document(simple_timeline, document, validate=False)

    report = otio_fdl.auto_link(simple_timeline)

    assert report["ambiguous"] == ["shot010"]
    shot010 = [c for c in simple_timeline.find_clips() if c.name == "shot010"][0]
    assert otio_fdl.canvas_for(shot010.media_reference, simple_timeline) is None


def test_auto_link_requires_document(simple_timeline):
    with pytest.raises(otio_fdl.FDLError, match="no FDL document"):
        otio_fdl.auto_link(simple_timeline)
