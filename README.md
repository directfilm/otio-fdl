# otio-fdl

Carry [ASC Framing Decision List (FDL)](https://github.com/ascmitc/fdl) data in
[OpenTimelineIO](https://github.com/AcademySoftwareFoundation/OpenTimelineIO)
files, so each shot's framing — full-gate plates, active areas, protection,
pull recipes — travels with the cut instead of being re-derived at every VFX
pull and conform.

**Status: prototype.** This package implements the metadata-convention tier of
a proposed "OTIO Framing Model": no OTIO core changes are required, and files
written with it remain fully readable by stock OTIO.

## Model

*The FDL document lives in one place; everything else points into it.*

- `timeline.metadata["ascfdl"]["document"]` — the complete `.fdl` document,
  verbatim (validated against the official ASC JSON Schema, v2.0.x).
- `media_reference.metadata["ascfdl"]["canvas_id"]` — a per-representation
  pointer into the document. Different representations of the same clip (a
  full-gate OCF, a desqueezed proxy) reference different canvases.
- All geometry stays in FDL's own coordinate system (pixel units, top-left
  origin, y-down). Nothing is re-expressed in OTIO-native spatial terms:
  OTIO is the carrier, the ASC FDL specification owns the semantics.

## Usage

```python
import opentimelineio as otio
import otio_fdl

timeline = otio.adapters.read_from_file("cut.otio")

# Attach the FDL sidecar (validates against the official ASC schema)
document = otio_fdl.load_fdl("cut.fdl")
otio_fdl.attach_document(timeline, document)

# Link media references to canvases — automatically via FDL 2.0 clip_id
# records, or explicitly:
report = otio_fdl.auto_link(timeline)  # {"linked": [rows], "ambiguous": [rows], "unmatched": [...]}
clip = next(iter(timeline.find_clips()))
otio_fdl.link(clip.media_reference, "pXLM4OnA", timeline=timeline)

# Resolve framing for a pull
canvas = otio_fdl.canvas_for(clip.media_reference, timeline)
decision = otio_fdl.framing_decision_for(clip.media_reference, timeline)

# Per-shot VFX pull list. Which canvas each pull is computed FROM is
# pipeline policy, not a rule: "root" (default) walks the derivation
# chain to the camera original even when the cut references editorial
# proxies; "linked" uses the referenced canvas; a callable
# source(clip, chain) can pick e.g. a pre-desqueezed intermediate. The
# output raster (full-res, 4K, 2K, padded container) is whatever the
# chosen canvas template prescribes.
specs = otio_fdl.pull_specs(timeline, source="root")

# Map geometry between related canvases (offline <-> OCF <-> pull):
# two canvases sharing a framing intent define the same creative
# rectangle in two pixel spaces, which yields the affine map between them
t = otio_fdl.transform_between(document, "offline1080", "ocfA448")
dims, anchor = otio_fdl.map_rect(t, note_dims, note_anchor)

# The document round-trips back out as a sidecar
restored = otio_fdl.extract_document(timeline)

otio.adapters.write_to_file(timeline, "cut_with_framing.otio")
```

## Limitations (deliberate, documented)

Framing semantics are the ASC's domain, not this library's: spec gaps
are fixed upstream and inherited here — verbatim carriage already
preserves unknown fields (a future FDL 2.1 rotation, underscore vendor
properties) through OTIO round-trips, and adopting a new spec version
means adding its official schema, not changing the model. This library
never invents framing fields of its own.

- **No rotation or flip/flop.** FDL has no orientation field — every region
  is an axis-aligned rect ([ascmitc/fdl#28](https://github.com/ascmitc/fdl/issues/28),
  slated for FDL 2.1). Transforms here are translation + per-axis scale;
  a flopped dailies render or rotated crash-cam plate cannot be described
  until the spec can say it.
- **No per-frame framing.** Keyframed reframes and mid-shot moves are out
  of the FDL spec's scope (section 2) — that is effect territory, not
  framing metadata.
- **One FDL document per timeline.** Regime changes (new charts mid-show)
  are expressed inside one document; merging per-episode/per-block FDLs
  into a season conform has no upstream semantics yet and is future work.
- **Canvas ids must be unique document-wide** — the spec is ambiguous
  across contexts ([#32](https://github.com/ascmitc/fdl/issues/32)); this
  library is deliberately stricter because id-based linking depends on it.
- **Template alignment is the spec's 9-grid.** Arbitrary off-center pull
  alignment awaits [#30](https://github.com/ascmitc/fdl/issues/30);
  off-center *decisions* are fully supported.

## Fidelity

Carriage is lossless, with one documented caveat: OpenTimelineIO's JSON
parser currently drops sub-ULP precision on some doubles (its rapidjson
`Parse` call omits `kParseFullPrecisionFlag`), so e.g. `3710.7000000000003`
reads back as `3710.7` after a file round-trip. In-memory attach/extract is
bit-exact; a fix is being proposed upstream.

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

Tests run against the ASC's own sample FDLs (`tests/fixtures/`, from
[ascmitc/fdl](https://github.com/ascmitc/fdl), Apache-2.0).

## Licensing

Licensed under a choice of the
[Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0.txt)
or the [MIT License](https://opensource.org/licenses/MIT), matching the
OpenTimelineIO plugin template this repository was generated from.
