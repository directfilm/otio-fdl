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

import functools
import json
import os
import posixpath
import urllib.parse
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


@functools.lru_cache(maxsize=None)
def _schema(filename):
    text = resources.files(__package__).joinpath("schemas", filename).read_text()
    return json.loads(text)


def validate_fdl(document):
    """Validate ``document`` against the bundled official ASC FDL schema.

    The schema version is chosen from the document's own ``version`` field
    (patch releases share their minor version's schema). Requires the
    ``jsonschema`` package; raises :class:`FDLError` on failure.
    """
    # plain-convert first: documents read back from OTIO metadata are
    # AnyDictionary/AnyVector, which neither dict checks nor jsonschema
    # accept as JSON objects/arrays
    document = _as_plain(document)
    version = document.get("version")
    if not isinstance(version, dict):
        version = {}
    key = (version.get("major"), version.get("minor"))
    schema_file = _SCHEMA_FILES.get(key)
    if schema_file is None:
        supported = ", ".join(f"{m}.{n}" for m, n in sorted(_SCHEMA_FILES))
        raise FDLError(
            f"unsupported or missing FDL version {document.get('version')!r}"
            f" (supported: {supported})"
        )

    import jsonschema

    try:
        jsonschema.validate(document, _schema(schema_file))
    except jsonschema.ValidationError as exc:
        raise FDLError(
            f"FDL document failed schema validation: {exc.message}"
            f" (at {'/'.join(str(p) for p in exc.absolute_path) or '<root>'})"
        ) from exc


def attach_document(timeline, document, *, validate=True, replace=False):
    """Attach an FDL document to ``timeline.metadata["ascfdl"]["document"]``.

    The document is deep-copied in (via plain-JSON conversion), so later
    mutation of the source cannot corrupt the timeline. Set ``replace=True``
    to overwrite an existing document.
    """
    if validate:
        validate_fdl(document)
    ns = timeline.metadata.setdefault(NAMESPACE, {})
    if "document" in ns and not replace:
        raise FDLError(
            "timeline already carries an FDL document"
            " (pass replace=True to overwrite)"
        )
    ns["document"] = _as_plain(document)


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


def canvas_by_id(document, canvas_id):
    """Return the canvas with ``canvas_id``, or raise :class:`FDLError`."""
    for _, canvas in iter_canvases(document):
        if canvas.get("id") == canvas_id:
            return canvas
    raise FDLError(f"canvas id {canvas_id!r} not present in document")


def canvas_chain(document, canvas_id):
    """The derivation chain ``[canvas, parent, ..., root]``.

    Follows ``source_canvas_id`` until it reaches a root (a canvas whose
    source is itself or unset). Cycle-safe; a dangling source id raises.
    """
    chain = []
    seen = set()
    current = canvas_by_id(document, canvas_id)
    while True:
        cid = current.get("id")
        if cid in seen:
            raise FDLError(f"source_canvas_id cycle at canvas {cid!r}")
        seen.add(cid)
        chain.append(current)
        source_id = current.get("source_canvas_id")
        if source_id in (None, cid):
            return chain
        current = canvas_by_id(document, source_id)


def root_canvas(document, canvas_id):
    """The original (root) canvas that ``canvas_id`` derives from."""
    return canvas_chain(document, canvas_id)[-1]


def select_decision(canvas, framing_intent_id=None, default_intent=None):
    """The canvas's framing decision for an intent.

    With no ``framing_intent_id``, falls back to ``default_intent`` (a
    document's ``default_framing_intent``); with neither, the canvas's
    first decision. Raises :class:`FDLError` when nothing matches.
    """
    decisions = canvas.get("framing_decisions", [])
    intent = framing_intent_id or default_intent
    if intent is None:
        if not decisions:
            raise FDLError(f"canvas {canvas.get('id')!r} has no framing decisions")
        return decisions[0]
    for decision in decisions:
        if decision.get("framing_intent_id") == intent:
            return decision
    raise FDLError(
        f"canvas {canvas.get('id')!r} has no decision for intent {intent!r}"
    )


def link(media_reference, canvas_id, *, timeline=None):
    """Point ``media_reference`` at a canvas by id.

    If ``timeline`` is given, the canvas id is checked against the attached
    document and unknown ids are rejected.
    """
    if timeline is not None:
        document = get_document(timeline)
        if document is None:
            raise FDLError("timeline carries no FDL document")
        canvas_by_id(document, canvas_id)
    media_reference.metadata.setdefault(NAMESPACE, {})["canvas_id"] = canvas_id


def _media_references(clip):
    """``{key: media_reference}`` for a clip (multi-reference aware)."""
    try:
        return dict(clip.media_references())
    except AttributeError:  # pragma: no cover - OTIO without multi-reference
        mr = clip.media_reference
        return {"DEFAULT_MEDIA": mr} if mr else {}


def _reference_matches_file(media_reference, filename):
    """Does an FDL ``clip_id.file`` entry name this media reference?

    ExternalReference: compare against the decoded basename of target_url.
    ImageSequenceReference: a sequence has no single file, so match when
    ``filename`` fits the sequence pattern (prefix/suffix) or equals the
    decoded basename of the sequence directory.
    """
    prefix = getattr(media_reference, "name_prefix", None)
    suffix = getattr(media_reference, "name_suffix", None)
    if prefix is not None or suffix is not None:  # image sequence
        if filename.startswith(prefix or "") and filename.endswith(suffix or ""):
            if len(filename) > len(prefix or "") + len(suffix or ""):
                return True
    for url in (
        getattr(media_reference, "target_url", None),
        getattr(media_reference, "target_url_base", None),
    ):
        if not url:
            continue
        path = urllib.parse.unquote(urllib.parse.urlparse(url).path or url)
        base = posixpath.basename(path.replace("\\", "/").rstrip("/"))
        if base and base == filename:
            return True
        # tolerate plain filesystem paths in target_url
        if os.path.basename(path.rstrip("/\\")) == filename:
            return True
    return False


def auto_link(timeline, choose=None):
    """Link media references using the document's per-context ``clip_id``.

    FDL 2.0 contexts may carry ``clip_id`` records (``clip_name``,
    ``file``). Every media reference of every clip is resolved
    independently: a context matches a reference when its ``clip_id.file``
    names that reference's media, or (clip-wide) when ``clip_id.clip_name``
    equals the clip's name. A single candidate canvas links the reference;
    several candidates are reported as ambiguous unless ``choose`` — called
    as ``choose(media_reference, candidate_canvases)`` and returning a
    canvas or ``None`` — settles it. Nothing is ever guessed.

    Returns ``{"linked": {clip: {ref_key: canvas_id}},
    "ambiguous": {clip: {ref_key: [candidate ids]}}, "unmatched": [clip]}``.
    """
    document = get_document(timeline)
    if document is None:
        raise FDLError("timeline carries no FDL document")

    by_clip_name = {}
    with_file = []
    for context in document.get("contexts", []):
        clip_id = context.get("clip_id") or {}
        if clip_id.get("clip_name"):
            by_clip_name.setdefault(clip_id["clip_name"], []).append(context)
        if clip_id.get("file"):
            with_file.append((clip_id["file"], context))

    report = {"linked": {}, "ambiguous": {}, "unmatched": []}
    for clip in timeline.find_clips():
        name_contexts = by_clip_name.get(clip.name, [])
        matched_any = False
        for key, mr in _media_references(clip).items():
            file_contexts = [
                ctx for fname, ctx in with_file
                if _reference_matches_file(mr, fname)
            ]
            contexts = file_contexts or name_contexts
            if not contexts:
                continue
            matched_any = True
            candidates = [c for ctx in contexts for c in ctx.get("canvases", [])]
            if len(candidates) > 1 and choose is not None:
                picked = choose(mr, candidates)
                if picked is not None:
                    candidates = [picked]
            if len(candidates) == 1:
                link(mr, candidates[0]["id"])
                report["linked"].setdefault(clip.name, {})[key] = candidates[0]["id"]
            elif candidates:
                report["ambiguous"].setdefault(clip.name, {})[key] = [
                    c["id"] for c in candidates
                ]
        if not matched_any:
            report["unmatched"].append(clip.name)
    return report


def canvas_for(media_reference, timeline):
    """Resolve a media reference's canvas from the timeline's document."""
    ns = media_reference.metadata.get(NAMESPACE)
    canvas_id = ns.get("canvas_id") if ns else None
    if canvas_id is None:
        return None
    document = get_document(timeline)
    if document is None:
        raise FDLError("timeline carries no FDL document")
    return canvas_by_id(document, canvas_id)


def framing_decision_for(media_reference, timeline, framing_intent_id=None):
    """Resolve the framing decision for a media reference.

    Uses ``framing_intent_id`` when given, otherwise the document's
    ``default_framing_intent``. Returns ``None`` when the media reference
    is unlinked or the canvas holds no decision for that intent.
    """
    canvas = canvas_for(media_reference, timeline)
    if canvas is None:
        return None
    document = get_document(timeline)
    try:
        return select_decision(
            canvas,
            framing_intent_id,
            default_intent=document.get("default_framing_intent"),
        )
    except FDLError:
        return None
