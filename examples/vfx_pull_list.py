#!/usr/bin/env python
# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright Contributors to the otio-fdl project

"""Demo: a conform timeline + an FDL sidecar -> a per-shot VFX pull list.

Usage:
    python examples/vfx_pull_list.py <cut.fdl> [template_id]

Builds a small editorial timeline, attaches the FDL document, links each
clip to its canvas, applies the document's canvas template, and prints the
pull spec every vendor normally reconstructs by hand: output raster, where
the framing lands in it, and the desqueeze applied.
"""

import sys

import opentimelineio as otio

import otio_fdl


def build_demo_timeline(document):
    """One clip per canvas in the FDL, named after its context."""
    timeline = otio.schema.Timeline(name="conform_demo")
    track = otio.schema.Track(name="V1")
    timeline.tracks.append(track)
    for context, canvas in otio_fdl.iter_canvases(document):
        if canvas.get("source_canvas_id") not in (None, canvas.get("id")):
            continue  # derived canvases are outputs, not sources to pull from
        clip = otio.schema.Clip(
            name=f"{context.get('label', 'ctx')}_{canvas['id']}",
            media_reference=otio.schema.ExternalReference(
                target_url=f"file:///plates/{canvas['id']}.exr"
            ),
            source_range=otio.opentime.TimeRange(
                otio.opentime.RationalTime(0, 24),
                otio.opentime.RationalTime(48, 24),
            ),
        )
        otio_fdl.link(clip.media_reference, canvas["id"])
        track.append(clip)
    return timeline


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    document = otio_fdl.load_fdl(sys.argv[1])
    template_id = sys.argv[2] if len(sys.argv) > 2 else None

    timeline = build_demo_timeline(document)
    otio_fdl.attach_document(timeline, document)

    print(f"Pull list for {timeline.name!r}  (FDL {document['uuid']})")
    for spec in otio_fdl.pull_specs(timeline, template_id=template_id):
        if spec.get("status") == "unlinked":
            print(f"  {spec['clip']:<28} !! no canvas linked")
            continue
        pull = spec["pull"]
        src = spec["canvas_id"]
        dims = pull["dimensions"]
        fd = pull["framing_decisions"][0]
        print(
            f"  {spec['clip']:<28} {src} -> "
            f"{dims['width']}x{dims['height']} "
            f"(squeeze {pull['anamorphic_squeeze']}), framing "
            f"{fd['dimensions']['width']:.0f}x{fd['dimensions']['height']:.0f}"
            f" @ ({fd['anchor_point']['x']:.1f}, {fd['anchor_point']['y']:.1f})"
        )


if __name__ == "__main__":
    main()
