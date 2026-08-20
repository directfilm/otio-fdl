# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright Contributors to the otio-fdl project

"""Round-trip: .fdl -> timeline metadata -> .otio file -> back, losslessly."""

import json

import opentimelineio as otio
import pytest

import otio_fdl
from conftest import ALL_VALID_FIXTURES, CORRUPT, assert_fdl_equal


@pytest.mark.parametrize(
    "fixture", ALL_VALID_FIXTURES, ids=lambda p: p.stem
)
def test_fdl_roundtrips_through_otio_file(fixture, simple_timeline, tmp_path):
    document = otio_fdl.load_fdl(fixture)
    otio_fdl.attach_document(simple_timeline, document)

    otio_path = tmp_path / "cut.otio"
    otio.adapters.write_to_file(simple_timeline, str(otio_path))
    reloaded = otio.adapters.read_from_file(str(otio_path))

    extracted = otio_fdl.extract_document(reloaded)
    assert_fdl_equal(extracted, document)


def test_in_memory_roundtrip_is_bit_exact(simple_timeline):
    """Without a file round-trip there is no parser in the loop: exact."""
    document = otio_fdl.load_fdl(ALL_VALID_FIXTURES[0])
    otio_fdl.attach_document(simple_timeline, document)
    assert otio_fdl.extract_document(simple_timeline) == document


def test_extracted_document_is_plain_json(simple_timeline, tmp_path):
    """The extracted document must serialize with the stock json module."""
    document = otio_fdl.load_fdl(ALL_VALID_FIXTURES[0])
    otio_fdl.attach_document(simple_timeline, document)

    otio_path = tmp_path / "cut.otio"
    otio.adapters.write_to_file(simple_timeline, str(otio_path))
    reloaded = otio.adapters.read_from_file(str(otio_path))

    extracted = otio_fdl.extract_document(reloaded)
    sidecar = tmp_path / "restored.fdl"
    sidecar.write_text(json.dumps(extracted, indent=2))
    assert_fdl_equal(json.loads(sidecar.read_text()), document)


def test_attach_deep_copies(simple_timeline, a65_document):
    otio_fdl.attach_document(simple_timeline, a65_document)
    a65_document["framing_intents"][0]["protection"] = 0.99
    stored = otio_fdl.get_document(simple_timeline)
    assert stored["framing_intents"][0]["protection"] == 0.07


def test_attach_twice_requires_replace(simple_timeline, a65_document):
    otio_fdl.attach_document(simple_timeline, a65_document)
    with pytest.raises(otio_fdl.FDLError, match="already carries"):
        otio_fdl.attach_document(simple_timeline, a65_document)
    otio_fdl.attach_document(simple_timeline, a65_document, replace=True)


def test_timeline_without_document(simple_timeline):
    assert otio_fdl.get_document(simple_timeline) is None
    assert otio_fdl.extract_document(simple_timeline) is None


def test_corrupt_fdl_raises():
    with pytest.raises(otio_fdl.FDLError, match="not valid JSON"):
        otio_fdl.load_fdl(CORRUPT)


def test_validation_rejects_bad_document(simple_timeline):
    bad = {"version": {"major": 2, "minor": 0}, "framing_intents": "nope"}
    with pytest.raises(otio_fdl.FDLError, match="schema validation"):
        otio_fdl.attach_document(simple_timeline, bad)


def test_validation_rejects_unsupported_version():
    with pytest.raises(otio_fdl.FDLError, match="unsupported"):
        otio_fdl.validate_fdl({"version": {"major": 1, "minor": 0}})
    with pytest.raises(otio_fdl.FDLError, match="unsupported"):
        otio_fdl.validate_fdl({})


def test_plain_metadata_survives_stock_otio(simple_timeline, a65_document, tmp_path):
    """A consumer with no otio-fdl installed sees intact, inert metadata.

    This environment IS stock OTIO (the package is not installed as a
    plugin), so reading the file with plain adapters and finding the
    namespace intact demonstrates graceful degradation.
    """
    otio_fdl.attach_document(simple_timeline, a65_document)
    otio_path = tmp_path / "cut.otio"
    otio.adapters.write_to_file(simple_timeline, str(otio_path))

    reloaded = otio.adapters.read_from_file(str(otio_path))
    raw = reloaded.metadata["ascfdl"]["document"]
    assert raw["uuid"] == a65_document["uuid"]


def test_unknown_future_fields_survive_carriage(simple_timeline, tmp_path):
    """The inheritance guarantee: fields this library has never heard of —
    a future FDL 2.1 rotation, underscore vendor properties — must survive
    attach -> .otio file -> extract verbatim. The carrier interprets
    nothing, so FDL evolution is inherited, not re-implemented."""
    document = otio_fdl.load_fdl(ALL_VALID_FIXTURES[0])
    canvas = document["contexts"][0]["canvases"][0]
    canvas["rotation"] = {"angle": 90}            # hypothetical 2.1 field
    canvas["_studio_note"] = "flopped for continuity"  # vendor property
    document["_pipeline"] = {"show": "EP101", "lut": "sh010_v2"}

    otio_fdl.attach_document(simple_timeline, document, validate=False)
    otio_path = tmp_path / "cut.otio"
    otio.adapters.write_to_file(simple_timeline, str(otio_path))
    reloaded = otio.adapters.read_from_file(str(otio_path))

    extracted = otio_fdl.extract_document(reloaded)
    out_canvas = extracted["contexts"][0]["canvases"][0]
    assert out_canvas["rotation"] == {"angle": 90}
    assert out_canvas["_studio_note"] == "flopped for continuity"
    assert extracted["_pipeline"] == {"show": "EP101", "lut": "sh010_v2"}
