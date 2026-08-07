import { z } from "zod";
import { serverEvent } from "./events.gen";

// The server -> client shapes are generated, not written here: `npm run
// generate:events` exports gateway's ServerEventUnion to events.schema.json
// and compiles that to events.gen.ts. Read shape diffs off the JSON -- the
// generated zod is one long line.

export type ServerEvent = z.infer<typeof serverEvent>;
export type RetrievalHit = Extract<ServerEvent, { type: "retrieval.hits" }>["hits"][number];

export type ParsedEvent =
  | { ok: true; event: ServerEvent }
  | { ok: false; reason: "unknown-type" | "invalid"; raw: unknown };

export function parseServerEvent(raw: unknown): ParsedEvent {
  const result = serverEvent.safeParse(raw);
  if (result.success) return { ok: true, event: result.data };

  const known = serverEvent.options.some(
    (option) =>
      option.shape.type.value ===
      (typeof raw === "object" && raw !== null && "type" in raw
        ? raw.type
        : undefined),
  );
  return { ok: false, reason: known ? "invalid" : "unknown-type", raw };
}

// Client -> server, deliberately still by hand: three shapes, and
// `parse_client_event` validates every one of them with pydantic on arrival,
// so drift here fails loudly at the gateway rather than silently in the UI.
export type ClientEvent =
  | { type: "user_message"; text: string; session_id?: string }
  | { type: "cancel" }
  | { type: "ping" };
