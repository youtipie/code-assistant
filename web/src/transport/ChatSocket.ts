import { WebSocket as ReconnectingWebSocket } from "partysocket";
import { parseServerEvent, type ClientEvent, type ServerEvent } from "@/protocol/events";

export type ConnectionState = "connecting" | "open" | "reconnecting" | "closed";

interface Handlers {
  onEvent: (event: ServerEvent) => void;
  onStateChange: (state: ConnectionState) => void;
  onProtocolError?: (reason: string, raw: unknown) => void;
}

const PING_INTERVAL_MS = 20_000;

export class ChatSocket {
  private socket: ReconnectingWebSocket | null = null;
  private pingTimer: number | null = null;
  private opened = false;

  constructor(
    private readonly url: string,
    private readonly handlers: Handlers,
  ) {}

  connect(): void {
    this.handlers.onStateChange("connecting");

    const socket = new ReconnectingWebSocket(this.url, undefined, {
      minReconnectionDelay: 500,
      maxReconnectionDelay: 15_000,
      connectionTimeout: 10_000,
    });
    this.socket = socket;

    socket.addEventListener("open", () => {
      this.opened = true;
      this.handlers.onStateChange("open");
      this.startPing();
    });

    socket.addEventListener("message", (event) => {
      let raw: unknown;
      try {
        raw = JSON.parse(String(event.data));
      } catch {
        this.handlers.onProtocolError?.("not JSON", event.data);
        return;
      }
      const parsed = parseServerEvent(raw);
      if (parsed.ok) this.handlers.onEvent(parsed.event);
      else if (parsed.reason === "invalid") {
        this.handlers.onProtocolError?.("failed validation", parsed.raw);
      }
    });

    socket.addEventListener("close", () => {
      this.stopPing();
      this.handlers.onStateChange(this.opened ? "reconnecting" : "connecting");
    });

    socket.addEventListener("error", () => {
      this.stopPing();
    });
  }

  send(event: ClientEvent): boolean {
    if (this.socket?.readyState !== WebSocket.OPEN) return false;
    this.socket.send(JSON.stringify(event));
    return true;
  }

  close(): void {
    this.stopPing();
    this.socket?.close();
    this.socket = null;
    this.handlers.onStateChange("closed");
  }

  private startPing(): void {
    this.stopPing();
    this.pingTimer = window.setInterval(() => this.send({ type: "ping" }), PING_INTERVAL_MS);
  }

  private stopPing(): void {
    if (this.pingTimer !== null) window.clearInterval(this.pingTimer);
    this.pingTimer = null;
  }
}

export function socketUrl(client: string, path = "/chat"): string {
  const configured = import.meta.env["VITE_GATEWAY_WS"];
  const base =
    typeof configured === "string" && configured.length > 0
      ? configured
      : `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}${path}`;
  const separator = base.includes("?") ? "&" : "?";
  return `${base}${separator}client=${encodeURIComponent(client)}`;
}
