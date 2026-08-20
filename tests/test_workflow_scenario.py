# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright Contributors to the otio-fdl project

"""End-to-end: the offline-vs-original workflow.

The combination that motivates the whole project: the camera shot 4:3
open-gate anamorphic (squeeze 2.0), editorial cut with 1080p DNx proxies
that are already desqueezed and 2.39-letterboxed, and the OTIO file
references ONLY the proxies. VFX must recover original-negative framing
from what editorial saw, and pulls must come from the OCF.
"""

import opentimelineio as otio
import pytest

import otio_fdl

# --- the FDL document, built from first principles ---------------------------

OCF_W, OCF_H, OCF_SQ = 4448, 3096, 2.0          # 4:3 sensor, 2x anamorphic
FD_W, FD_X = 3700, 374                          # 2.39 extraction, full height
# lab recipe for dailies: desqueeze, fit the framing to 1920 wide, letterbox
K = 1920 / (FD_W * OCF_SQ)                      # 1920 / 7400
OFF_FD_H = OCF_H * K                            # 803.2864...
OFF_FD_Y = (1080 - OFF_FD_H) / 2                # 138.3567...
# a second deliverable intent: 16:9 TV extraction inside the same gate
TV_W_D = OCF_H * 16 / 9                         # desqueezed width 5504
TV_W = TV_W_D / OCF_SQ                          # 2752 px on sensor
TV_X = (OCF_W - TV_W) / 2                       # 848


def build_document():
    return {
        "uuid": "d13716b2-8b95-4b40-9d6b-a6b9c65c1c4e",
        "version": {"major": 2, "minor": 0},
        "fdl_creator": "otio-fdl test suite",
        "default_framing_intent": "sc239",
        "framing_intents": [
            {
                "label": "2.39 Scope",
                "id": "sc239",
                "aspect_ratio": {"width": 239, "height": 100},
                "protection": 0.0,
            },
            {
                "label": "16-9 TV",
                "id": "tv169",
                "aspect_ratio": {"width": 16, "height": 9},
                "protection": 0.0,
            },
        ],
        "contexts": [
            {
                "label": "A cam",
                "context_creator": "otio-fdl test suite",
                "clip_id": {"clip_name": "shot010"},
                "canvases": [
                    {
                        "label": "Open Gate OCF",
                        "id": "ocfA448",
                        "source_canvas_id": "ocfA448",
                        "dimensions": {"width": OCF_W, "height": OCF_H},
                        "anamorphic_squeeze": OCF_SQ,
                        "framing_decisions": [
                            {
                                "label": "2.39 Scope",
                                "id": "ocfA448-sc239",
                                "framing_intent_id": "sc239",
                                "dimensions": {"width": FD_W, "height": OCF_H},
                                "anchor_point": {"x": FD_X, "y": 0},
                            },
                            {
                                "label": "16-9 TV",
                                "id": "ocfA448-tv169",
                                "framing_intent_id": "tv169",
                                "dimensions": {"width": TV_W, "height": OCF_H},
                                "anchor_point": {"x": TV_X, "y": 0},
                            },
                        ],
                    },
                    {
                        "label": "Desqueezed Master",
                        "id": "dsq4k",
                        "source_canvas_id": "ocfA448",
                        "dimensions": {"width": 4448, "height": 1548},
                        "anamorphic_squeeze": 1.0,
                        "framing_decisions": [
                            {
                                "label": "2.39 Scope",
                                "id": "dsq4k-sc239",
                                "framing_intent_id": "sc239",
                                "dimensions": {"width": 3700, "height": 1548},
                                "anchor_point": {"x": 374, "y": 0},
                            },
                            {
                                "label": "16-9 TV",
                                "id": "dsq4k-tv169",
                                "framing_intent_id": "tv169",
                                "dimensions": {"width": 2752, "height": 1548},
                                "anchor_point": {"x": 848, "y": 0},
                            },
                        ],
                    },
                    {
                        "label": "Editorial DNx 1080",
                        "id": "offline1080",
                        "source_canvas_id": "dsq4k",
                        "dimensions": {"width": 1920, "height": 1080},
                        "effective_dimensions": {"width": 1920, "height": 804},
                        "effective_anchor_point": {"x": 0.0, "y": 138.0},
                        "anamorphic_squeeze": 1.0,
                        "framing_decisions": [
                            {
                                "label": "2.39 Scope",
                                "id": "offline1080-sc239",
                                "framing_intent_id": "sc239",
                                "dimensions": {"width": 1920, "height": OFF_FD_H},
                                "anchor_point": {"x": 0.0, "y": OFF_FD_Y},
                            },
                            {
                                "label": "16-9 TV",
                                "id": "offline1080-tv169",
                                "framing_intent_id": "tv169",
                                "dimensions": {
                                    "width": TV_W_D * K,
                                    "height": OFF_FD_H,
                                },
                                "anchor_point": {
                                    "x": (1920 - TV_W_D * K) / 2,
                                    "y": OFF_FD_Y,
                                },
                            },
                        ],
                    },
                ],
            }
        ],
        "canvas_templates": [
            {
                "label": "VFX Pull 2K",
                "id": "vxp2k",
                "target_dimensions": {"width": 2048, "height": 1080},
                "target_anamorphic_squeeze": 1.0,
                "fit_source": "framing_decision.dimensions",
                "fit_method": "width",
                "preserve_from_source_canvas": "canvas.dimensions",
                "round": {"even": "even", "mode": "up"},
            },
            {
                "label": "VFX Pull",
                "id": "vxp01",
                "target_dimensions": {"width": 4096, "height": 2160},
                "target_anamorphic_squeeze": 1.0,
                "fit_source": "framing_decision.dimensions",
                "fit_method": "width",
                "alignment_method_vertical": "center",
                "alignment_method_horizontal": "center",
                "preserve_from_source_canvas": "canvas.dimensions",
                "round": {"even": "even", "mode": "up"},
            }
        ],
    }


@pytest.fixture
def cut():
    """An editorial cut referencing ONLY the DNx proxies, doc attached."""
    timeline = otio.schema.Timeline(name="ep101_r3_v012")
    track = otio.schema.Track(name="V1")
    timeline.tracks.append(track)
    track.append(
        otio.schema.Clip(
            name="shot010",
            media_reference=otio.schema.ExternalReference(
                target_url="file:///editorial/shot010_dnx36.mov"
            ),
            source_range=otio.opentime.TimeRange(
                otio.opentime.RationalTime(0, 24),
                otio.opentime.RationalTime(48, 24),
            ),
        )
    )
    document = build_document()
    otio_fdl.validate_fdl(document)  # the constructed doc is real FDL
    otio_fdl.attach_document(timeline, document)
    return timeline


def _link_offline(timeline):
    clip = next(iter(timeline.find_clips()))
    otio_fdl.link(clip.media_reference, "offline1080", timeline=timeline)
    return clip


def test_auto_link_multi_canvas_context_with_chooser(cut):
    """OCF + intermediate + proxy canvases in one context: ambiguous by
    default (never guess), resolved by a chooser encoding pipeline
    knowledge — an editorial cut references the 1080p proxies."""
    report = otio_fdl.auto_link(cut)
    key = otio.schema.Clip.DEFAULT_MEDIA_KEY
    assert report["ambiguous"] == {
        "shot010": {key: ["ocfA448", "dsq4k", "offline1080"]}
    }

    def editorial_proxy(mr, canvases):
        hits = [
            c for c in canvases
            if c["dimensions"] == {"width": 1920, "height": 1080}
        ]
        return hits[0] if len(hits) == 1 else None

    report = otio_fdl.auto_link(cut, choose=editorial_proxy)
    assert report["linked"] == {"shot010": {key: "offline1080"}}


def test_reframe_note_maps_offline_to_ocf_and_back(cut):
    """A rect drawn on the proxy lands on the right OCF pixels (D2)."""
    _link_offline(cut)
    document = otio_fdl.get_document(cut)
    t = otio_fdl.transform_between(document, "offline1080", "ocfA448")
    assert t["uniform"]

    # the whole offline framing maps exactly onto the OCF framing
    dims, anchor = otio_fdl.map_rect(
        t, {"width": 1920, "height": OFF_FD_H}, {"x": 0.0, "y": OFF_FD_Y}
    )
    assert dims["width"] == pytest.approx(FD_W)
    assert dims["height"] == pytest.approx(OCF_H)
    assert anchor["x"] == pytest.approx(FD_X)
    assert anchor["y"] == pytest.approx(0, abs=1e-9)

    # an arbitrary note round-trips through the inverse
    note_dims, note_anchor = {"width": 400, "height": 225}, {"x": 480, "y": 300}
    ocf_dims, ocf_anchor = otio_fdl.map_rect(t, note_dims, note_anchor)
    back_dims, back_anchor = otio_fdl.map_rect(
        otio_fdl.invert(t), ocf_dims, ocf_anchor
    )
    assert back_dims["width"] == pytest.approx(400)
    assert back_anchor["x"] == pytest.approx(480)
    assert back_anchor["y"] == pytest.approx(300)


def test_pull_comes_from_ocf_not_proxy(cut):
    """pull_specs walks the derivation chain to the camera original (D1)."""
    _link_offline(cut)
    specs = otio_fdl.pull_specs(cut, template_id="vxp01")
    (spec,) = specs
    assert spec["canvas_id"] == "offline1080"      # what the cut references
    assert spec["pulled_from"] == "ocfA448"        # what the pull uses
    pull = spec["pull"]
    # hand-derived: fit 7400 desq to 4096 -> s = 0.55351; preserve the
    # desqueezed gate (8896 * s = 4924.06) -> round even/up -> 4926 wide
    assert pull["dimensions"] == {"width": 4926, "height": 2160}
    assert pull["anamorphic_squeeze"] == 1.0
    fd = pull["framing_decisions"][0]
    assert fd["dimensions"]["width"] == pytest.approx(4096)
    assert fd["dimensions"]["height"] == pytest.approx(1713.678, abs=0.01)
    assert fd["anchor_point"]["x"] == pytest.approx(415.0, abs=0.01)

    # without the chain walk the pull would wrongly come from the proxy
    proxy_specs = otio_fdl.pull_specs(cut, template_id="vxp01", source="linked")
    assert proxy_specs[0]["pulled_from"] == "offline1080"


def test_multi_intent_transforms_agree(cut):
    """Both intents were baked with the same lab recipe, so registration
    through either yields the same map (G6) — a consistency check real
    documents can be audited with."""
    document = otio_fdl.get_document(cut)
    t_scope = otio_fdl.transform_between(
        document, "offline1080", "ocfA448", framing_intent_id="sc239"
    )
    t_tv = otio_fdl.transform_between(
        document, "offline1080", "ocfA448", framing_intent_id="tv169"
    )
    for k in ("scale_x", "scale_y", "offset_x", "offset_y"):
        assert t_scope[k] == pytest.approx(t_tv[k], rel=1e-9)


def test_intent_selection_on_offline(cut):
    clip = _link_offline(cut)
    tv = otio_fdl.framing_decision_for(
        clip.media_reference, cut, framing_intent_id="tv169"
    )
    assert tv["id"] == "offline1080-tv169"
    default = otio_fdl.framing_decision_for(clip.media_reference, cut)
    assert default["id"] == "offline1080-sc239"  # default_framing_intent


def test_conform_qc_roundtrip(cut):
    """Pull -> conform check (D3/D4): mint the pull canvas, add it to the
    document, and verify the pull's framing registers back onto the OCF
    exactly — the chain OCF -> offline -> pull -> OCF closes."""
    _link_offline(cut)
    document = otio_fdl.extract_document(cut)
    pull = otio_fdl.pull_specs(cut, template_id="vxp01")[0]["pull"]
    document["contexts"][0]["canvases"].append(pull)
    otio_fdl.validate_fdl(document)  # minted canvas is valid FDL in place

    t = otio_fdl.transform_between(document, pull["id"], "ocfA448")
    fd = pull["framing_decisions"][0]
    dims, anchor = otio_fdl.map_rect(t, fd["dimensions"], fd["anchor_point"])
    assert dims["width"] == pytest.approx(FD_W)
    assert dims["height"] == pytest.approx(OCF_H)
    assert anchor["x"] == pytest.approx(FD_X)
    assert anchor["y"] == pytest.approx(0, abs=1e-6)


def test_pull_from_desqueezed_intermediate_via_callable(cut):
    """Pulls are NOT always from the open gate: a callable source picks
    the pre-desqueezed master out of the derivation chain, and the 2K
    template scales down from there — both are pipeline policy."""
    _link_offline(cut)

    def first_desqueezed(clip, chain):
        return next(
            c for c in chain[1:] if c.get("anamorphic_squeeze") == 1.0
        )

    (spec,) = otio_fdl.pull_specs(
        cut, template_id="vxp2k", source=first_desqueezed
    )
    assert spec["canvas_id"] == "offline1080"
    assert spec["pulled_from"] == "dsq4k"
    pull = spec["pull"]
    # 2048/3700 fit on the 4448x1548 master, gate preserved: 2464x1080
    assert pull["dimensions"] == {"width": 2464, "height": 1080}
    assert pull["anamorphic_squeeze"] == 1.0
    fd = pull["framing_decisions"][0]
    assert fd["dimensions"]["width"] == pytest.approx(2048)
    assert fd["dimensions"]["height"] == pytest.approx(856.84, abs=0.01)


def test_chain_walks_through_intermediate(cut):
    document = otio_fdl.get_document(cut)
    chain = otio_fdl.canvas_chain(document, "offline1080")
    assert [c["id"] for c in chain] == ["offline1080", "dsq4k", "ocfA448"]
    assert otio_fdl.root_canvas(document, "offline1080")["id"] == "ocfA448"


def test_unknown_pull_source_raises(cut):
    _link_offline(cut)
    with pytest.raises(otio_fdl.FDLError, match="unknown pull source"):
        otio_fdl.pull_specs(cut, template_id="vxp01", source="og")


def test_declining_source_callable_is_per_clip_error(cut):
    _link_offline(cut)
    (spec,) = otio_fdl.pull_specs(
        cut, template_id="vxp01", source=lambda clip, chain: None
    )
    assert spec["status"] == "error"
    assert "declined" in spec["error"]
