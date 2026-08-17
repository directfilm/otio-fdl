# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright Contributors to the otio-fdl project

"""Carry ASC Framing Decision List (FDL) documents in OpenTimelineIO files.

Model ("carrier, not translator"):

* The complete FDL document lives verbatim, exactly once, under
  ``timeline.metadata["ascfdl"]["document"]``.
* Each media reference carries only a lightweight pointer:
  ``media_reference.metadata["ascfdl"] = {"canvas_id": ...}``.
* All geometry stays in FDL's own coordinate system (pixel units, top-left
  origin, y-down). Nothing is re-expressed in OTIO-native spatial terms.
"""

from __future__ import annotations

import copy
import json
import os
from importlib import resources

NAMESPACE = "ascfdl"

_SCHEMA_FILES = {
    (2, 0): "ascfdl-2.0.1.schema.json",
}


class FDLError(ValueError):
    """Raised for invalid FDL documents or unresolvable references."""


def load_fdl(path):
    """Read a ``.fdl`` file (JSON, UTF-8) and return it as a dict."""
    with open(path, encoding="utf-8") as f:
        try:
            document = json.load(f)
        except json.JSONDecodeError as exc:
            raise FDLError(f"{path!r} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise FDLError(f"{path!r} does not contain a JSON object")
    return document


def validate_fdl(document):
    """Validate ``document`` against the bundled official ASC FDL schema.

    The schema version is chosen from the document's own ``version`` field
    (patch releases share their minor version's schema). Requires the
    ``jsonschema`` package; raises :class:`FDLError` on failure.
    """
    version = document.get("version") or {}
    key = (version.get("major"), version.get("minor"))
    schema_file = _SCHEMA_FILES.get(key)
    if schema_file is None:
        supported = ", ".join(f"{m}.{n}" for m, n in sorted(_SCHEMA_FILES))
        raise FDLError(
            f"unsupported or missing FDL version {version!r}"
            f" (supported: {supported})"
        )

    import jsonschema

    schema_text = (
        resources.files(__package__).joinpath("schemas", schema_file).read_text()
    )
    try:
        jsonschema.validate(document, json.loads(schema_text))
    except jsonschema.ValidationError as exc:
        raise FDLError(
            f"FDL document failed schema validation: {exc.message}"
            f" (at {'/'.join(str(p) for p in exc.absolute_path) or '<root>'})"
        ) from exc


def attach_document(timeline, document, *, validate=True, replace=False):
    """Attach an FDL document to ``timeline.metadata["ascfdl"]["document"]``.

    The document is deep-copied in, so later mutation of the source dict
    cannot corrupt the timeline. Set ``replace=True`` to overwrite an
    existing document.
    """
    if validate:
        validate_fdl(document)
    ns = timeline.metadata.setdefault(NAMESPACE, {})
    if "document" in ns and not replace:
        raise FDLError(
            "timeline already carries an FDL document"
            " (pass replace=True to overwrite)"
        )
    ns["document"] = copy.deepcopy(document)


def get_document(timeline):
    """Return the attached FDL document (live reference), or ``None``."""
    ns = timeline.metadata.get(NAMESPACE)
    return ns.get("document") if ns else None


def extract_document(timeline):
    """Return a deep copy of the attached FDL document, or ``None``.

    Suitable for writing back out as a ``.fdl`` sidecar.
    """
    document = get_document(timeline)
    return _as_plain(document) if document is not None else None


def _as_plain(value):
    """Recursively convert OTIO AnyDictionary/AnyVector to dict/list."""
    if hasattr(value, "items"):
        return {k: _as_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)) or (
        hasattr(value, "__iter__") and not isinstance(value, (str, bytes))
    ):
        return [_as_plain(v) for v in value]
    return value


def iter_canvases(document):
    """Yield ``(context, canvas)`` pairs across the document."""
    for context in document.get("contexts", []):
        for canvas in context.get("canvases", []):
            yield context, canvas


def link(media_reference, canvas_id, *, timeline=None):
    """Point ``media_reference`` at a canvas by id.

    If ``timeline`` is given, the canvas id is checked against the attached
    document and unknown ids are rejected.
    """
    if timeline is not None:
        document = get_document(timeline)
        if document is None:
            raise FDLError("timeline carries no FDL document")
        if not any(c["id"] == canvas_id for _, c in iter_canvases(document)):
            raise FDLError(f"canvas id {canvas_id!r} not present in document")
    media_reference.metadata.setdefault(NAMESPACE, {})["canvas_id"] = canvas_id


def auto_link(timeline):
    """Link media references using the document's per-context ``clip_id``.

    FDL 2.0 contexts may carry ``clip_id`` records (``clip_name``, ``file``).
    For every clip in the timeline, a context matches when its
    ``clip_id.clip_name`` equals the clip's name, or its ``clip_id.file``
    equals the basename of a media reference's ``target_url``. When the
    matching context holds exactly one canvas, every media reference of that
    clip is linked to it (file matches link just the matching reference).

    Returns a report dict: ``{"linked": [...], "ambiguous": [...],
    "unmatched": [...]}`` naming clips by name.
    """
    document = get_document(timeline)
    if document is None:
        raise FDLError("timeline carries no FDL document")

    by_clip_name = {}
    by_file = {}
    for context in document.get("contexts", []):
        clip_id = context.get("clip_id") or {}
        if clip_id.get("clip_name"):
            by_clip_name.setdefault(clip_id["clip_name"], []).append(context)
        if clip_id.get("file"):
            by_file.setdefault(clip_id["file"], []).append(context)

    report = {"linked": [], "ambiguous": [], "unmatched": []}
    for clip in timeline.find_clips():
        contexts = list(by_clip_name.get(clip.name, []))
        file_hits = []  # (media_reference, context)
        for mr in _media_references(clip):
            url = getattr(mr, "target_url", None) or getattr(
                mr, "target_url_base", None
            )
            if url:
                for context in by_file.get(os.path.basename(url.rstrip("/")), []):
                    file_hits.append((mr, context))

        if not contexts and not file_hits:
            report["unmatched"].append(clip.name)
            continue

        linked = False
        for mr, context in file_hits:
            canvases = context.get("canvases", [])
            if len(canvases) == 1:
                link(mr, canvases[0]["id"])
                linked = True
        if contexts and not linked:
            canvases = [c for ctx in contexts for c in ctx.get("canvases", [])]
            if len(canvases) == 1:
                for mr in _media_references(clip):
                    link(mr, canvases[0]["id"])
                linked = True
        report["linked" if linked else "ambiguous"].append(clip.name)
    return report


def _media_references(clip):
    """All media references of a clip (multi-reference aware)."""
    try:
        return list(clip.media_references().values())
    except AttributeError:  # pragma: no cover - OTIO < 0.15
        return [clip.media_reference] if clip.media_reference else []


def canvas_for(media_reference, timeline):
    """Resolve a media reference's canvas from the timeline's document."""
    ns = media_reference.metadata.get(NAMESPACE)
    canvas_id = ns.get("canvas_id") if ns else None
    if canvas_id is None:
        return None
    document = get_document(timeline)
    if document is None:
        raise FDLError("timeline carries no FDL document")
    for _, canvas in iter_canvases(document):
        if canvas["id"] == canvas_id:
            return canvas
    raise FDLError(f"canvas id {canvas_id!r} not present in document")


def framing_decision_for(media_reference, timeline, framing_intent_id=None):
    """Resolve the framing decision for a media reference.

    Uses ``framing_intent_id`` when given, otherwise the document's
    ``default_framing_intent``. Returns ``None`` when the media reference is
    unlinked or the canvas holds no decision for that intent.
    """
    canvas = canvas_for(media_reference, timeline)
    if canvas is None:
        return None
    if framing_intent_id is None:
        document = get_document(timeline)
        framing_intent_id = document.get("default_framing_intent")
    for decision in canvas.get("framing_decisions", []):
        if decision.get("framing_intent_id") == framing_intent_id:
            return decision
    return None
