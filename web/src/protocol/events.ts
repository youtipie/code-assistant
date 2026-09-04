import { z } from "zod";
import { serverEvent } from "./events.gen";

// The server -> client shapes are generated: `npm run generate:events`
// exports gateway's ServerEventUnion to events.schema.json and compiles it to
// events.gen.ts. Read shape diffs off the JSON, not the one-line zod.

export type ServerEvent = z.infer<typeof serverEvent>;
export type RetrievalHit = Extract<ServerEvent, { type: "retrieval.hits" }>["hits"][number];
// nullable on the wire, for a turn that died before it could be accounted for
export type TurnStats = NonNullable<
  Extract<ServerEvent, { type: "turn.end" }>["stats"]
>;

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

// Client -> server, still by hand: `parse_client_event` validates all three
// with pydantic on arrival, so drift fails loudly at the gateway.
export type ClientEvent =
  | { type: "user_message"; text: string; session_id?: string }
  | { type: "cancel" }
  | { type: "ping" };
