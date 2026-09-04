from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Literal

from core.events import RetrievalHits, ToolCall, ToolResult
from langchain_mcp_adapters.interceptors import MCPToolCallRequest, MCPToolCallResult
from mcp.types import CallToolResult, TextContent

from . import rendering
from .config import settings
from .tool_rules import decide
from .turn_state import TurnState, current_turn_state


class TurnInterceptor:

    async def __call__(
        self,
        request: MCPToolCallRequest,
        handler: Callable[[MCPToolCallRequest], Awaitable[MCPToolCallResult]],
    ) -> MCPToolCallResult:
        server = request.server_name
        name = request.name
        state = current_turn_state()
        # outside a real turn there is nothing to de-dupe against, and a
        # throwaway set means the rules never refuse on repetition alone
        seen = state.seen if state is not None else set()

        decision = decide(server, name, dict(request.args), seen, settings)
        if decision.record is not None and state is not None:
            state.seen.add(decision.record)

        started = time.perf_counter()

        if decision.refusal is not None:
            call_id = _announce(state, name, decision.args)
            # "ok", not "error": a scope refusal is a policy outcome the model
            # is expected to read and work around, not a failed call
            _finish(
                state,
                call_id,
                "ok",
                decision.refusal_preview or "refused",
                _since(started),
            )
            return _as_result(decision.refusal)

        call_id = _announce(state, name, decision.args)
        try:
            result = await handler(request.override(args=decision.args))
        except Exception as exc:
            # report the failure to the client, then let it propagate:
            # handle_tool_errors on the client turns it into text for the
            # model, so the turn continues exactly as it did before
            _finish(
                state,
                call_id,
                "error",
                f"{type(exc).__name__}: {exc}",
                _since(started),
            )
            raise

        # stopped before rendering: the card reports what the tool took
        elapsed = _since(started)
        raw = _text_of(result)
        rendered, hits = rendering.render(server, name, raw)
        if hits is not None and state is not None:
            state.buffer.append(
                RetrievalHits(turn_id=state.turn_id, call_id=call_id, hits=hits)
            )
            state.updated.set()
        failed = _failed(result)
        _finish(state, call_id, "error" if failed else "ok", rendered, elapsed)
        # carry the flag through: telling the client a call failed while
        # telling the model it succeeded would be worse than either alone
        return _as_result(rendered, is_error=failed)


def _failed(result: MCPToolCallResult) -> bool:
    """Whether the server reported the call as failed.

    MCPToolCallResult is a union: an MCP CallToolResult carries `isError`, a
    LangChain ToolMessage carries `status`. An unrecognised shape counts as
    success -- the model reads the text either way.
    """
    if getattr(result, "isError", False):
        return True
    return getattr(result, "status", None) == "error"


def _announce(state: TurnState | None, name: str, arguments: dict) -> str:
    call_id = str(uuid.uuid4())[:8]
    if state is not None:
        state.calls += 1
        state.buffer.append(
            ToolCall(
                turn_id=state.turn_id, call_id=call_id, name=name, arguments=arguments
            )
        )
        state.updated.set()
    return call_id


def _finish(
    state: TurnState | None,
    call_id: str,
    status: Literal["ok", "error"],
    preview: str,
    duration_ms: int,
) -> None:
    if state is not None:
        state.buffer.append(
            ToolResult(
                turn_id=state.turn_id,
                call_id=call_id,
                status=status,
                preview=preview[:200],
                duration_ms=duration_ms,
            )
        )
        state.updated.set()


def _since(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _as_result(text: str, is_error: bool = False) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=text)], isError=is_error
    )


def _text_of(result: MCPToolCallResult) -> str:
    content = getattr(result, "content", None)
    if isinstance(content, str):
        return content

    parts: list[str] = []
    for block in content or []:
        kind = getattr(block, "type", None) or (
            block.get("type") if isinstance(block, dict) else None
        )
        if kind == "text":
            parts.append(getattr(block, "text", "") or block.get("text", ""))
        elif kind == "resource":
            resource = getattr(block, "resource", None)
            text = getattr(resource, "text", None)
            if text:
                uri = getattr(resource, "uri", "")
                parts.append(f"--- {uri} ---\n{text}" if uri else text)
    return "\n".join(parts) if parts else "{}"
