"""Turning raw tool output into the text the model sees.

Two cases, deliberately kept apart: the knowledge server's results have a
schema this repo owns and are parsed and rendered into citation-carrying
blocks (`knowledge`); everything else is third-party data with no schema we
control, wrapped and labelled as such (`external`, with `diffs` for the one
payload shape big enough to need truncating).
"""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from ..knowledge import OUTLINE, OWN_SERVER, READ_FILE, SEARCH_CODE, SEARCH_DOCS
from .external import _remember_diff_paths, _remember_paths, _render_external
from .knowledge import (
    Hits,
    _render_outline,
    _render_read,
    _render_search,
)

log = logging.getLogger(__name__)

RENDERERS = {
    (OWN_SERVER, SEARCH_DOCS): _render_search,
    (OWN_SERVER, SEARCH_CODE): _render_search,
    (OWN_SERVER, OUTLINE): _render_outline,
    (OWN_SERVER, READ_FILE): _render_read,
}

__all__ = ["Hits", "render"]


def render(server: str, tool: str, raw: str) -> tuple[str, Hits | None]:
    renderer = RENDERERS.get((server, tool))

    if renderer is None:
        _remember_diff_paths(raw)
        try:
            _remember_paths(json.loads(raw))
        except json.JSONDecodeError:
            pass
        return _render_external(server, tool, raw), None

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return f"Tool returned an unreadable response: {raw[:200]}", None

    try:
        return renderer(payload)
    except ValidationError:
        # the knowledge server returned something this build does not
        # understand -- say so rather than raising into the tool call, where
        # it would surface to the model as an opaque adapter error
        log.exception("%s.%s returned an unexpected shape", server, tool)
        return f"{tool} returned a response this client cannot read.", None
