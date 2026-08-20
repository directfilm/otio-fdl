#!/usr/bin/env python
# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright Contributors to the otio-fdl project

"""The conform workflow with framing as data: end to end.

A two-camera cut (A-cam 4:3 anamorphic open gate, B-cam spherical 16:9)
arrives from editorial referencing only 1080p DNx proxies. The dailies
lab's FDL sidecar travels with it. This script plays every department:

  1. EDITORIAL   builds the cut (as if converted from an EDL)
  2. DAILIES     attach the FDL document + auto-link clips to canvases
  3. VFX         generate the per-shot pull list FROM THE CAMERA ORIGINALS
  4. FINISHING   verify returning renders register onto the finishing
                 raster exactly where the framing intent says (conform QC)
  5. OUTPUT      write cut_with_framing.otio + the round-tripped .fdl

Run:  python examples/conform_with_framing.py [output_dir]
"""

import json
import pathlib
import sys
import tempfile

import opentimelineio as otio

import otio_fdl

INTENT = "sc239"


def lab_fdl():
    """The dailies lab's FDL: per-shot contexts, OCF + proxy + finishing
    canvases, and the VFX pull recipe. A-cam numbers match ARRI-style
    open-gate anamorphic practice; B-cam is a spherical 16:9 sensor."""

    def context(shot, ocf, proxy, fin):
        return {
            "label": f"{shot} setup",
            "context_creator": "demo dailies lab",
            "clip_id": {"clip_name": shot},
            "canvases": [ocf, proxy, fin],
        }

    def canvas(cid, label, w, h, sq, source, decisions, effective=None):
        out = {
            "label": label,
            "id": cid,
            "source_canvas_id": source or cid,
            "dimensions": {"width": w, "height": h},
            "anamorphic_squeeze": sq,
            "framing_decisions": decisions,
        }
        if effective:
            out["effective_dimensions"] = effective[0]
            out["effective_anchor_point"] = effective[1]
        return out

    def decision(cid, w, h, x, y):
        return {
            "label": "2.39 Scope",
            "id": f"{cid}-{INTENT}",
            "framing_intent_id": INTENT,
            "dimensions": {"width": w, "height": h},
            "anchor_point": {"x": x, "y": y},
        }

    # A-cam: 4448x3096 open gate, 2.0x anamorphic; scope framing is full
    # height, 3700 px wide (7400 desqueezed).
    a_fd_h, a_k = 3096, 1920 / 7400.0
    a_off_h = a_fd_h * a_k                      # 803.286...
    a_fin_h = 4096 * 3096 / 7400.0              # 1713.678
    # B-cam: 5760x3240 spherical; scope framing is full width.
    b_fd_h = 5760 / 2.39                        # 2410.042
    b_off_h = b_fd_h / 3.0                      # 803.347
    b_fin_h = 4096 * b_fd_h / 5760.0            # 1713.807

    return {
        "uuid": "83b2b6f2-42e2-4e4b-9a67-1c1de6f4a301",
        "version": {"major": 2, "minor": 0},
        "fdl_creator": "otio-fdl conform demo",
        "default_framing_intent": INTENT,
        "framing_intents": [
            {
                "label": "2.39 Scope",
                "id": INTENT,
                "aspect_ratio": {"width": 239, "height": 100},
                "protection": 0.05,
            }
        ],
        "contexts": [
            context(
                "sh010",
                canvas("ocfA", "A-cam Open Gate", 4448, 3096, 2.0, None,
                       [decision("ocfA", 3700, a_fd_h, 374, 0)]),
                canvas("dnxA", "A-cam DNx 1080", 1920, 1080, 1.0, "ocfA",
                       [decision("dnxA", 1920, a_off_h, 0, (1080 - a_off_h) / 2)],
                       effective=({"width": 1920, "height": 804},
                                  {"x": 0.0, "y": 138.0})),
                canvas("finA", "Finishing 4K Scope", 4096, 1716, 1.0, "ocfA",
                       [decision("finA", 4096, a_fin_h, 0, (1716 - a_fin_h) / 2)]),
            ),
            context(
                "sh020",
                canvas("ocfB", "B-cam Spherical", 5760, 3240, 1.0, None,
                       [decision("ocfB", 5760, b_fd_h, 0, (3240 - b_fd_h) / 2)]),
                canvas("dnxB", "B-cam DNx 1080", 1920, 1080, 1.0, "ocfB",
                       [decision("dnxB", 1920, b_off_h, 0, (1080 - b_off_h) / 2)],
                       effective=({"width": 1920, "height": 804},
                                  {"x": 0.0, "y": 138.0})),
                canvas("finB", "Finishing 4K Scope", 4096, 1716, 1.0, "ocfB",
                       [decision("finB", 4096, b_fin_h, 0, (1716 - b_fin_h) / 2)]),
            ),
        ],
        "canvas_templates": [
            {
                "label": "VFX Pull",
                "id": "vxpull",
                "target_dimensions": {"width": 4096, "height": 2160},
                "target_anamorphic_squeeze": 1.0,
                "fit_source": "framing_decision.dimensions",
                "fit_method": "width",
                "preserve_from_source_canvas": "canvas.dimensions",
                "round": {"even": "even", "mode": "up"},
            }
        ],
    }


def editorial_cut():
    """The cut as it arrives: proxies only, no framing knowledge."""
    timeline = otio.schema.Timeline(name="ep101_r3_v012")
    track = otio.schema.Track(name="V1")
    timeline.tracks.append(track)
    for shot, frames in (("sh010", 48), ("sh020", 36)):
        track.append(
            otio.schema.Clip(
                name=shot,
                media_reference=otio.schema.ExternalReference(
                    target_url=f"file:///editorial/{shot}_dnx36.mov"
                ),
                source_range=otio.opentime.TimeRange(
                    otio.opentime.RationalTime(0, 24),
                    otio.opentime.RationalTime(frames, 24),
                ),
            )
        )
    return timeline


def main():
    out_dir = pathlib.Path(
        sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="otio_fdl_")
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    print("1. EDITORIAL: cut references 1080p proxies only")
    timeline = editorial_cut()

    print("2. DAILIES: attach FDL sidecar, auto-link (proxies are 1080p)")
    document = lab_fdl()
    otio_fdl.validate_fdl(document)
    otio_fdl.attach_document(timeline, document)

    def editorial_proxy(mr, canvases):
        hits = [c for c in canvases
                if c["dimensions"] == {"width": 1920, "height": 1080}]
        return hits[0] if len(hits) == 1 else None

    report = otio_fdl.auto_link(timeline, choose=editorial_proxy)
    for row in report["linked"]:
        print(f"   linked {row['clip']}/{row['ref']} -> {row['canvas_id']}")
    for name in report["unmatched"]:
        print(f"   UNMATCHED {name}")

    print("3. VFX: pull list from the camera originals (source='root')")
    pulls = {}
    for spec in otio_fdl.pull_specs(timeline, source="root"):
        if "pull" not in spec:
            print(f"   {spec['clip']}: {spec.get('status')}")
            continue
        pull = spec["pull"]
        fd = pull["framing_decisions"][0]
        pulls[spec["clip"]] = pull
        print(
            f"   {spec['clip']}: {spec['canvas_id']} -> pull from"
            f" {spec['pulled_from']}: {pull['dimensions']['width']}x"
            f"{pull['dimensions']['height']} (squeeze"
            f" {pull['anamorphic_squeeze']}), framing"
            f" {fd['dimensions']['width']:.0f}x{fd['dimensions']['height']:.1f}"
            f" @ ({fd['anchor_point']['x']:.1f}, {fd['anchor_point']['y']:.1f})"
        )

    print("4. FINISHING: renders return — conform QC against intent")
    qc_document = otio_fdl.extract_document(timeline)
    for clip_name, pull in pulls.items():
        qc_document["contexts"][0 if clip_name == "sh010" else 1][
            "canvases"].append(pull)
        fin_id = "finA" if clip_name == "sh010" else "finB"
        t = otio_fdl.transform_between(qc_document, pull["id"], fin_id)
        fd = pull["framing_decisions"][0]
        dims, anchor = otio_fdl.map_rect(t, fd["dimensions"], fd["anchor_point"])
        fin_fd = otio_fdl.canvas_by_id(qc_document, fin_id)["framing_decisions"][0]
        dw = abs(dims["width"] - fin_fd["dimensions"]["width"])
        dx = abs(anchor["x"] - fin_fd["anchor_point"]["x"])
        status = "OK" if (t["uniform"] and dw < 0.01 and dx < 0.01) else "FAIL"
        print(
            f"   {clip_name}: pull framing lands on {fin_id} at"
            f" ({anchor['x']:.2f}, {anchor['y']:.2f})"
            f" {dims['width']:.1f}x{dims['height']:.1f} — QC {status}"
        )

    print("5. OUTPUT")
    otio_path = out_dir / "cut_with_framing.otio"
    fdl_path = out_dir / "ep101_r3_v012.fdl"
    otio.adapters.write_to_file(timeline, str(otio_path))
    fdl_path.write_text(json.dumps(otio_fdl.extract_document(timeline), indent=2))
    print(f"   {otio_path}\n   {fdl_path}")
    print("   (the .otio remains fully readable by stock OpenTimelineIO)")


if __name__ == "__main__":
    main()
