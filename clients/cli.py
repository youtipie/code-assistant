import asyncio
import json
import os
import signal
import sys

import websockets

URL = os.getenv("GATEWAY_URL", "ws://localhost:8000/chat")


class Client:
    def __init__(self, ws) -> None:
        self.ws = ws
        self.session_id: str | None = None
        self.streaming = asyncio.Event()
        self.turn_done = asyncio.Event()
        self.turn_done.set()

    async def receive_loop(self) -> None:
        async for raw in self.ws:
            event = json.loads(raw)
            kind = event.get("type")

            if kind == "session.created":
                self.session_id = event["session_id"]
                print(f"\n[session {self.session_id}]", flush=True)
            elif kind == "turn.start":
                self.streaming.set()
                self.turn_done.clear()
                print("\nassistant> ", end="", flush=True)
            elif kind == "text.delta":
                print(event["text"], end="", flush=True)
            elif kind == "tool.call":
                args = event.get("arguments", {})
                detail = args.get("query") or args.get("path") or ""
                if args.get("symbol"):
                    detail += f" :: {args['symbol']}"
                if args.get("repo"):
                    detail = f"{args.get('owner', '')}/{args['repo']} {detail}".strip()
                print(f"\n  \u2192 {event['name']}({detail})", flush=True)
            elif kind == "tool.result":
                mark = "\u2713" if event["status"] == "ok" else "\u2717"
                print(f"  {mark} {event.get('preview') or ''}", flush=True)
            elif kind == "retrieval.hits":
                for h in event.get("hits", []):
                    print(f"    \u00b7 {h['citation']}", flush=True)
                print(flush=True)
            elif kind == "turn.end":
                reason = event["reason"]
                suffix = "" if reason == "completed" else f"  [{reason}]"
                if event.get("message"):
                    suffix += f" {event['message']}"
                print(suffix, flush=True)
                if stats := event.get("stats"):
                    print(_stats_line(stats), flush=True)
                print(flush=True)
                self.streaming.clear()
                self.turn_done.set()
            elif kind == "error":
                print(f"\n[error:{event['code']}] {event['message']}\n", flush=True)
                self.turn_done.set()
            elif kind in ("heartbeat", "pong"):
                pass
            else:
                print(f"\n[{kind}] {event}\n", flush=True)

    async def send(self, payload: dict) -> None:
        await self.ws.send(json.dumps(payload))


def _stats_line(stats: dict) -> str:
    """The same numbers the web client shows under an answer."""
    parts = [stats["model"] or "unknown"]
    if stats["ttft_ms"] is not None:
        parts.append(f"{stats['ttft_ms'] / 1000:.1f}s to first token")
    parts.append(f"{stats['duration_ms'] / 1000:.1f}s total")
    parts.append(f"{stats['prompt_tokens']} in / {stats['completion_tokens']} out")
    cost = stats["cost_usd"]
    parts.append("cost unknown" if cost is None else f"${cost:.4f}")
    parts.append(f"{stats['steps']} step" + ("" if stats['steps'] == 1 else "s"))
    parts.append(f"{stats['tool_calls']} tools")
    return "  \u00b7 " + "  \u00b7 ".join(parts)


async def read_lines() -> asyncio.Queue[str | None]:
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_readable() -> None:
        line = sys.stdin.readline()
        queue.put_nowait(line if line else None)  # None == EOF

    loop.add_reader(sys.stdin.fileno(), on_readable)
    return queue


async def main() -> None:
    async with websockets.connect(URL, ping_interval=20) as ws:
        client = Client(ws)
        receiver = asyncio.create_task(client.receive_loop())
        print(f"connected to {URL}  (Ctrl-C cancels a response)\n")

        lines = await read_lines()
        loop = asyncio.get_running_loop()

        def on_sigint() -> None:
            if client.streaming.is_set():
                loop.create_task(client.send({"type": "cancel"}))
            else:
                lines.put_nowait(None)

        loop.add_signal_handler(signal.SIGINT, on_sigint)

        try:
            while True:
                print("you> ", end="", flush=True)
                raw_line = await lines.get()
                if raw_line is None:
                    print()
                    break

                line = raw_line.strip()
                if not line:
                    continue
                if line == "/new":
                    client.session_id = None
                    print("started a new session\n")
                    continue
                if line == "/session":
                    print(
                        f"session_id: {client.session_id}\n"
                        if client.session_id
                        else "no session yet - send a message first\n"
                    )
                    continue
                if line in ("/quit", "/exit"):
                    break

                msg: dict = {"type": "user_message", "text": line}
                if client.session_id:
                    msg["session_id"] = client.session_id
                client.turn_done.clear()
                await client.send(msg)
                await client.turn_done.wait()
        finally:
            loop.remove_signal_handler(signal.SIGINT)
            loop.remove_reader(sys.stdin.fileno())
            receiver.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
