# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright Contributors to the otio-fdl project

"""otio-fdl — carry ASC Framing Decision List (FDL) data in OTIO files.

Prototype implementing the "RFC: OTIO Framing Model" metadata convention:
the complete FDL document travels once at timeline scope under the
``ascfdl`` namespace; media references point into it by canvas id.
"""

from .core import (  # noqa: F401
    NAMESPACE,
    FDLError,
    attach_document,
    auto_link,
    canvas_by_id,
    canvas_chain,
    canvas_for,
    extract_document,
    framing_decision_for,
    get_document,
    iter_canvases,
    link,
    load_fdl,
    root_canvas,
    select_decision,
    validate_fdl,
)
from .templates import (  # noqa: F401
    apply_canvas_template,
    pull_specs,
    round_dimension,
)
from .transforms import (  # noqa: F401
    invert,
    map_point,
    map_rect,
    transform_between,
)

__all__ = [
    "NAMESPACE",
    "FDLError",
    "apply_canvas_template",
    "attach_document",
    "auto_link",
    "canvas_by_id",
    "canvas_chain",
    "canvas_for",
    "extract_document",
    "framing_decision_for",
    "get_document",
    "invert",
    "iter_canvases",
    "link",
    "load_fdl",
    "map_point",
    "map_rect",
    "pull_specs",
    "root_canvas",
    "round_dimension",
    "select_decision",
    "transform_between",
    "validate_fdl",
]
