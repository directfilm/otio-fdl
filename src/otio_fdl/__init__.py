# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright Contributors to the otio-fdl project

"""otio-fdl — carry ASC Framing Decision List (FDL) data in OTIO files.

Prototype implementing the "RFC: OTIO Framing Model" metadata convention:
the complete FDL document travels once at timeline scope under the
``ascfdl`` namespace; media references point into it by canvas id.
"""

from .templates import (  # noqa: F401
    apply_canvas_template,
    pull_specs,
    round_dimension,
)
from .core import (  # noqa: F401
    NAMESPACE,
    FDLError,
    attach_document,
    auto_link,
    canvas_for,
    extract_document,
    framing_decision_for,
    get_document,
    iter_canvases,
    link,
    load_fdl,
    validate_fdl,
)

__all__ = [
    "NAMESPACE",
    "apply_canvas_template",
    "pull_specs",
    "round_dimension",
    "FDLError",
    "attach_document",
    "auto_link",
    "canvas_for",
    "extract_document",
    "framing_decision_for",
    "get_document",
    "iter_canvases",
    "link",
    "load_fdl",
    "validate_fdl",
]
