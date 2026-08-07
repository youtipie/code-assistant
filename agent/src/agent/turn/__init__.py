"""Machinery for driving one turn, kept apart from the turn's own lifecycle.

`run_turn` in `agent.agent` owns the lifecycle -- prompt in, events out, one
terminal `TurnEnd` however it ends. `stream` owns the one genuinely fiddly
mechanism underneath it: racing the graph's message stream against the
interceptor's buffer so tool events reach the client promptly.
"""

from .stream import Buffered, Message, Step, drain, steps

__all__ = ["Buffered", "Message", "Step", "drain", "steps"]
