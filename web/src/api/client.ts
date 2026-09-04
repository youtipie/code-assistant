import { z } from "zod";
import { clientId } from "@/lib/identity";
import type { components } from "./schema";


export type SessionSummary = components["schemas"]["SessionSummary"];
export type Message = components["schemas"]["MessageOut"];
export type ServerStatus = components["schemas"]["ServerStatus"];
export type Status = components["schemas"]["Status"];

export const sessionSummary: z.ZodType<SessionSummary> = z.object({
  id: z.string(),
  title: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  turn_count: z.number().int(),
});

export type MessageStats = components["schemas"]["TurnStats"];

export const turnStats: z.ZodType<MessageStats> = z.object({
  model: z.string(),
  prompt_tokens: z.number().int(),
  completion_tokens: z.number().int(),
  cached_tokens: z.number().int(),
  cache_write_tokens: z.number().int(),
  cost_usd: z.number().nullable(),
  ttft_ms: z.number().int().nullable(),
  duration_ms: z.number().int(),
  steps: z.number().int(),
  tool_calls: z.number().int(),
});

export type MessageToolCall = components["schemas"]["ToolCallOut"];

export const toolCall: z.ZodType<MessageToolCall> = z.object({
  call_id: z.string(),
  name: z.string(),
  arguments: z.record(z.unknown()),
  status: z.string(),
  preview: z.string().nullable(),
  hits: z.array(
    z.object({
      path: z.string(),
      citation: z.string(),
      start_line: z.number().int(),
      source_type: z.string(),
    }),
  ),
  duration_ms: z.number().int().nullable(),
});

export const message: z.ZodType<Message> = z.object({
  id: z.number().int(),
  role: z.string(),
  text: z.string(),
  turn_id: z.string().nullable(),
  created_at: z.string(),
  // z.object strips keys the schema does not name: omitting these drops the
  // footer and the cards from every reloaded turn
  stats: turnStats.nullable(),
  tools: z.array(toolCall),
});

export const serverStatus: z.ZodType<ServerStatus> = z.object({
  name: z.string(),
  description: z.string(),
  available: z.boolean(),
  tool_count: z.number().int(),
});

export const status: z.ZodType<Status> = z.object({
  model: z.string(),
  corpus_repos: z.array(z.string()),
  snapshots: z.array(z.object({ repo: z.string(), commit: z.string() })),
  servers: z.array(serverStatus),
  tools: z.array(z.string()),
});

export class ApiError extends Error {
  constructor(
    message: string,
    readonly statusCode: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function headers(): HeadersInit {
  return { Accept: "application/json", "X-Client-Id": clientId() };
}

async function request<T>(path: string, schema: z.ZodType<T>): Promise<T> {
  const response = await fetch(path, { headers: headers() });
  if (!response.ok) throw new ApiError(`GET ${path} failed`, response.status);
  return schema.parse(await response.json());
}

export const api = {
  sessions: () => request("/api/sessions", z.array(sessionSummary)),
  messages: (sessionId: string) =>
    request(`/api/sessions/${sessionId}/messages`, z.array(message)),
  status: () => request("/api/status", status),
  deleteSession: async (sessionId: string): Promise<void> => {
    const response = await fetch(`/api/sessions/${sessionId}`, {
      method: "DELETE",
      headers: headers(),
    });
    if (!response.ok) throw new ApiError("could not delete session", response.status);
  },
};
