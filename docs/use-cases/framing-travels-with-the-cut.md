# Framing Travels With The Cut

**Status: Prototyped**
A working implementation of this use case exists as the
[otio-fdl](https://github.com/directfilm/otio-fdl) plugin (metadata
convention, no core changes). This document is written in the format of
OpenTimelineIO's `docs/use-cases/` so it can be proposed upstream.

## Summary

A timeline says *when* every shot cuts, but nothing about *what part of
the image* each shot is. On most productions the camera captures more
than the framed picture — open-gate or 4:3 sensors, anamorphic squeezes,
protection areas — and every department re-derives the framing for
itself: dailies build 1080p extractions from framing charts, VFX pull
full-quality plates and reconstruct the crop by hand, and finishing
conforms everything into the delivery raster. Framing charts "are never
pixel accurate" (dailies supervisors rebuild them per show), facilities
check pixel-accurate turnovers per vendor by hand, and streamers maintain
formal "Framing Error" QC rejection categories for when this goes wrong.

The ASC Framing Decision List (FDL) exists to carry framing intent as
data — canvases, per-intent framing decisions, and canvas templates (the
recipes that generate pull rasters). OpenEXR already carries FDL in the
`ascFramingDecisionList` standard attribute. What is missing is keeping
that data attached to the *cut*: if the FDL travels inside the .otio
file, with each media reference pointing at its canvas, then pull
resolutions, extraction rectangles, and conform QC all become computable
from the timeline instead of being reconstructed from PDFs and folklore.

## Example

A show shoots A-cam on a 4:3 open-gate sensor with 2.0x anamorphic
lenses (4448x3096, scope framing 3700x3096 centered) and B-cam spherical
16:9 (5760x3240, scope framing full-width). Editorial cuts with 1080p
DNx proxies that are already desqueezed and letterboxed. The cut is
exported as OTIO, referencing only the proxies; the dailies lab's .fdl
sidecar is attached into the timeline's metadata, and each clip's media
reference is linked (automatically, via the FDL's per-context `clip_id`
records) to the canvas describing its proxy.

VFX receives the OTIO file alone and computes the pull list: for each
shot, the canvas derivation chain leads from the proxy back to the
camera original, and the document's "VFX Pull" canvas template produces
the plate spec — A-cam: 4926x2160 desqueezed with the full gate
preserved for stabilization, framing at (415, 223); B-cam: 4096x2304.
When renders return, finishing registers each pull against the 4K scope
delivery raster through the shared framing intent and verifies the image
lands exactly where the intent says — the same check a QC vendor
performs today by eye.

The `otio-fdl` prototype implements this end to end
(`examples/conform_with_framing.py`), validated against the ASC's own
sample FDLs and the spec's numeric examples. Files written this way
remain fully readable by stock OpenTimelineIO: consumers without the
plugin see inert, namespaced metadata.

## Features Needed in OTIO

None, at the prototype tier — that is the point of the metadata
convention:

* `metadata` dictionaries on `Timeline` (the complete FDL document,
  verbatim, exactly once) and on each `MediaReference` (a canvas-id
  pointer). Both exist today.
* Multi-media-reference clips (OTIO 0.15+) let one clip bind its OCF,
  proxy, and pull representations to different canvases.

For framing to become first-class, later stages would want:

* A SchemaDef plugin registering FramingIntent/Canvas/FramingDecision
  schemas (no core change; files degrade to `UnknownSchema`).
* Eventually, optional core fields following the `available_image_bounds`
  precedent (PR #1219): additive, optional, no schema-version bump.
* OTIOZ/OTIOD bundles could carry the .fdl sidecar alongside media, as
  proposed for OCIO configs.

## Features of Python Script

* Attach/extract: `.fdl` sidecar into `timeline.metadata["ascfdl"]`,
  validated against the official ASC JSON Schema; extract back out
  losslessly.
* Link: bind each media reference to its canvas — explicitly, or
  automatically from FDL `clip_id` records (per-reference, ambiguity
  reported, never guessed).
* Pull list: apply the document's canvas template per shot; the source
  canvas (camera original, pre-desqueezed intermediate, or the linked
  proxy) is pipeline policy, selectable per run.
* Registration: compute the affine map between any two canvases sharing
  a framing intent (proxy -> OCF for annotation mapping; pull ->
  finishing for conform QC), desqueeze-aware.
* Round-trip: write the enriched .otio and regenerate the .fdl sidecar.
