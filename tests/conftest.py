# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright Contributors to the otio-fdl project

import json
import pathlib

import opentimelineio as otio
import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def assert_fdl_equal(a, b, path="$"):
    """Structural FDL equality with float tolerance.

    OpenTimelineIO's JSON *parser* is not full-precision for doubles (its
    rapidjson Parse call omits kParseFullPrecisionFlag —
    deserialization.cpp:888), so values like 3710.7000000000003 come back as
    3710.7 after a file round-trip. Carriage is otherwise lossless; floats
    are compared with math.isclose until that is fixed upstream.
    """
    import math

    if isinstance(a, dict) and isinstance(b, dict):
        assert a.keys() == b.keys(), f"{path}: keys {a.keys()} != {b.keys()}"
        for k in a:
            assert_fdl_equal(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list) and isinstance(b, list):
        assert len(a) == len(b), f"{path}: length {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            assert_fdl_equal(x, y, f"{path}[{i}]")
    elif isinstance(a, float) or isinstance(b, float):
        assert math.isclose(a, b, rel_tol=1e-12), f"{path}: {a!r} != {b!r}"
    else:
        assert a == b, f"{path}: {a!r} != {b!r}"

A65 = FIXTURES / "A65_effective-area_wdesqueeze.fdl"
SCEN3 = FIXTURES / "Scen3__RESULT.fdl"
CORRUPT = FIXTURES / "corrupt_fdl.fdl"

ALL_VALID_FIXTURES = sorted(
    p for p in FIXTURES.glob("*.fdl") if p.name != "corrupt_fdl.fdl"
)


@pytest.fixture
def a65_document():
    return json.loads(A65.read_text())


@pytest.fixture
def scen3_document():
    return json.loads(SCEN3.read_text())


@pytest.fixture
def simple_timeline():
    """A one-track timeline shaped like a small conform: two video clips."""
    timeline = otio.schema.Timeline(name="conform_reel_01")
    track = otio.schema.Track(name="V1")
    timeline.tracks.append(track)

    plate = otio.schema.Clip(
        name="shot010",
        media_reference=otio.schema.ExternalReference(
            target_url="file:///plates/shot010_opengate.exr"
        ),
        source_range=otio.opentime.TimeRange(
            otio.opentime.RationalTime(0, 24),
            otio.opentime.RationalTime(48, 24),
        ),
    )
    other = otio.schema.Clip(
        name="shot020",
        media_reference=otio.schema.ExternalReference(
            target_url="file:///plates/shot020_opengate.exr"
        ),
        source_range=otio.opentime.TimeRange(
            otio.opentime.RationalTime(0, 24),
            otio.opentime.RationalTime(36, 24),
        ),
    )
    track.append(plate)
    track.append(other)
    return timeline
