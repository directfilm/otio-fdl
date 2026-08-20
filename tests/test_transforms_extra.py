# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright Contributors to the otio-fdl project

"""Transform degenerate-input guards."""

import copy

import pytest

import otio_fdl


def test_degenerate_target_decision_raises(a65_document):
    document = copy.deepcopy(a65_document)
    src = copy.deepcopy(document["contexts"][0]["canvases"][0])
    src["id"] = "srcB"
    src["framing_decisions"][0]["id"] = "srcB-fiWILIY0"
    document["contexts"][0]["canvases"].append(src)
    bad = document["contexts"][0]["canvases"][1]
    bad["framing_decisions"][0]["dimensions"] = {"width": 0, "height": 0}

    with pytest.raises(otio_fdl.FDLError, match="degenerate"):
        otio_fdl.transform_between(document, "pXLM4OnA", "srcB")
    # and symmetrically as the source side
    with pytest.raises(otio_fdl.FDLError, match="degenerate"):
        otio_fdl.transform_between(document, "srcB", "pXLM4OnA")
