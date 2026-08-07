"""Emit the server -> client wire contract as JSON Schema for the web client.

    cd gateway && uv run python -m app.schema_export

`web/`'s `npm run generate:events` runs this and then compiles the result to
zod, so `web/src/protocol/events.ts` no longer restates the event shapes by
hand. Nothing here talks to a running gateway -- the models are the contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from .protocol import ServerEventUnion

OUT = Path(__file__).resolve().parents[2] / "web/src/protocol/events.schema.json"


def _inline(node: Any, defs: dict[str, Any]) -> Any:
    """Replace every $ref with the definition it points at.

    The emitted document is then ref-free, so the zod compiler never has to
    resolve one. Safe because none of these models is recursive.
    """
    if isinstance(node, list):
        return [_inline(item, defs) for item in node]
    if not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if ref is not None:
        return _inline(defs[ref.rsplit("/", 1)[-1]], defs)
    return {key: _inline(value, defs) for key, value in node.items()}


def _normalise(model: dict[str, Any]) -> None:
    """Strip pydantic's Python-facing noise and require every field.

    A Python-side default does not make a field optional on the wire:
    `model_dump_json` emits every field it has not excluded, so a frame
    missing one is drift, not a shorthand. Saying so here is what keeps
    `type` a plain literal in the generated zod -- which `parseServerEvent`
    reads to tell an unknown event from an invalid one -- and what keeps
    `hits` and `arguments` non-optional for the store that consumes them.
    """
    model.pop("title", None)
    model.pop("description", None)
    properties = model.get("properties", {})
    for prop in properties.values():
        prop.pop("title", None)
        prop.pop("default", None)
    model["required"] = list(properties)


def schema() -> dict[str, Any]:
    # mode="serialization" is load-bearing: it drops TurnEnd's exclude=True
    # persistence fields, which are valid inputs but never reach the wire.
    doc = TypeAdapter(ServerEventUnion).json_schema(mode="serialization")
    doc = _inline(doc, doc.pop("$defs"))
    for event in doc["anyOf"]:
        _normalise(event)
        for prop in event["properties"].values():
            if prop.get("type") == "array" and isinstance(prop.get("items"), dict):
                _normalise(prop["items"])
    return doc


if __name__ == "__main__":
    OUT.write_text(json.dumps(schema(), indent=2) + "\n")
    print(f"wrote {OUT}")
