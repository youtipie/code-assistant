"""Machinery for driving one turn, kept apart from the turn's own lifecycle.

`run_turn` in `agent.agent` owns the lifecycle; `stream` owns the fiddly
mechanism underneath it -- racing the graph's message stream against the
interceptor's buffer so tool events reach the client promptly.
"""

from .stream import Buffered, Message, Step, drain, steps

__all__ = ["Buffered", "Message", "Step", "drain", "steps"]
