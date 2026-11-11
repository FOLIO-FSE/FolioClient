"""Small, deterministic ``$ref`` resolver for FOLIO JSON schemas fetched from GitHub.

This replaces ``jsonref.replace_refs(..., proxies=False)`` for schema dereferencing.
jsonref 1.1.0 memoizes nodes by ``id()`` in ``_walk_refs`` while *replacing* proxies, and the
replaced proxy objects are freed (and their ids reused) mid-walk, so a later node can be handed
the result computed for an unrelated, earlier one. See the changelog for details.

Behavior:

* Each document is fetched once and cached by absolute URL (without fragment).
* Every ``$ref`` is resolved against the URL of the document that contains it.
* The result is a plain nested ``dict``/``list`` structure containing no ``$ref`` keys, except
  for circular references (see below). Documents returned by the loader are never mutated.
* Sibling keys next to a ``$ref`` (e.g. ``description``) are merged over the referenced object
  when it is a mapping; the siblings win.
* A circular reference is left in place as ``{"$ref": "<absolute URL>#<pointer>"}`` (plus any
  sibling keys), so the output is always finite and JSON serializable.
"""

from __future__ import annotations

import copy
from typing import Any, Callable
from urllib.parse import unquote, urldefrag, urljoin

Loader = Callable[[str], Any]


def _resolve_pointer(document: Any, pointer: str, uri: str) -> Any:
    """Resolve a JSON pointer (RFC 6901) such as ``/definitions/foo`` within ``document``."""
    if not pointer:
        return document
    node = document
    for raw in unquote(pointer).lstrip("/").split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        try:
            node = node[int(part)] if isinstance(node, list) else node[part]
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise ValueError(f"Unresolvable JSON pointer '#{pointer}' in {uri}") from exc
    return node


def dereference(schema: Any, base_uri: str, loader: Loader) -> Any:
    """Return a copy of ``schema`` with all ``$ref`` objects replaced by what they point to.

    Args:
        schema: The already-loaded root document found at ``base_uri``.
        base_uri: Absolute URL of ``schema``; relative refs are resolved against it.
        loader: Callable taking an absolute URL and returning the parsed document.
    """
    root_uri = urldefrag(base_uri)[0]
    documents: dict[str, Any] = {root_uri: schema}
    memo: dict[tuple[str, str], Any] = {}
    in_progress: list[tuple[str, str]] = [(root_uri, "")]
    cycles_cut = 0  # circular refs emitted so far; results containing one aren't memoized

    def load(uri: str) -> Any:
        if uri not in documents:
            documents[uri] = loader(uri)
        return documents[uri]

    def walk(node: Any, doc_uri: str) -> Any:
        if isinstance(node, list):
            return [walk(item, doc_uri) for item in node]
        if not isinstance(node, dict):
            return node
        ref = node.get("$ref")
        if not isinstance(ref, str):
            return {key: walk(value, doc_uri) for key, value in node.items()}

        target_uri, pointer = urldefrag(urljoin(doc_uri, ref))
        key = (target_uri, pointer)
        siblings = {k: walk(v, doc_uri) for k, v in node.items() if k != "$ref"}
        if key in in_progress:
            nonlocal cycles_cut
            cycles_cut += 1
            return {"$ref": f"{target_uri}#{pointer}" if pointer else target_uri, **siblings}
        if key in memo:
            resolved = copy.deepcopy(memo[key])
        else:
            before = cycles_cut
            in_progress.append(key)
            try:
                target = _resolve_pointer(load(target_uri), pointer, target_uri)
                resolved = walk(target, target_uri)
            finally:
                in_progress.pop()
            if cycles_cut == before:  # nothing circular was cut off inside, so it's reusable
                memo[key] = copy.deepcopy(resolved)
        if siblings and isinstance(resolved, dict):
            resolved = {**resolved, **siblings}
        return resolved

    return walk(schema, root_uri)
