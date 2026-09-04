import { create } from "zustand";
import type { ConnectionState } from "@/transport/ChatSocket";
import type { RetrievalHit, ServerEvent, TurnStats } from "@/protocol/events";


export interface ToolInvocation {
  callId: string;
  name: string;
  server: "knowledge" | "github" | "other";
  arguments: Record<string, unknown>;
  status: "running" | "ok" | "error";
  preview?: string;
  hits: RetrievalHit[];
  // measured server-side: arrival times would fold in socket and render
  // latency, and leave a reloaded turn with no timing at all
  durationMs?: number;
}

export interface Turn {
  id: string;
  question: string;
  text: string;
  tools: ToolInvocation[];
  status: "streaming" | "completed" | "cancelled" | "error";
  error?: string;
  startedAt: number;
  endedAt?: number;
  // measured server-side; arrives once on turn.end, so absent while streaming
  stats?: TurnStats;
}

interface ChatState {
  sessionId: string | null;
  turns: Turn[];
  connection: ConnectionState;
  pendingQuestion: string | null;
  lastError: string | null;

  apply: (event: ServerEvent) => void;
  setConnection: (state: ConnectionState) => void;
  setSession: (sessionId: string | null) => void;
  questionSent: (text: string) => void;
  loadHistory: (turns: Turn[], sessionId: string) => void;
  reset: () => void;
}


const KNOWLEDGE_TOOLS = new Set(["search_docs", "search_code", "outline", "read_file"]);

export function serverOf(toolName: string): ToolInvocation["server"] {
  const [prefix] = toolName.split("__");
  if (prefix === "github") return "github";
  if (prefix === "knowledge") return "knowledge";
  if (KNOWLEDGE_TOOLS.has(toolName)) return "knowledge";
  return "github";
}

function updateTurn(turns: Turn[], turnId: string, patch: (turn: Turn) => Turn): Turn[] {
  return turns.map((turn) => (turn.id === turnId ? patch(turn) : turn));
}

export const useChatStore = create<ChatState>((set) => ({
  sessionId: null,
  turns: [],
  connection: "connecting",
  pendingQuestion: null,
  lastError: null,

  setConnection: (connection) => set({ connection }),
  setSession: (sessionId) => set({ sessionId }),
  questionSent: (text) => set({ pendingQuestion: text, lastError: null }),
  loadHistory: (turns, sessionId) => set({ turns, sessionId, pendingQuestion: null }),
  reset: () => set({ turns: [], sessionId: null, pendingQuestion: null, lastError: null }),

  apply: (event) =>
    set((state) => {
      switch (event.type) {
        case "session.created":
          return { sessionId: event.session_id };

        case "turn.start": {
          const turn: Turn = {
            id: event.turn_id,
            question: state.pendingQuestion ?? "",
            text: "",
            tools: [],
            status: "streaming",
            startedAt: Date.now(),
          };
          return { turns: [...state.turns, turn], pendingQuestion: null };
        }

        case "text.delta":
          return {
            turns: updateTurn(state.turns, event.turn_id, (turn) => ({
              ...turn,
              text: turn.text + event.text,
            })),
          };

        case "tool.call":
          return {
            turns: updateTurn(state.turns, event.turn_id, (turn) => ({
              ...turn,
              tools: [
                ...turn.tools,
                {
                  callId: event.call_id,
                  name: event.name,
                  server: serverOf(event.name),
                  arguments: event.arguments,
                  status: "running",
                  hits: [],
                },
              ],
            })),
          };

        case "tool.result":
          return {
            turns: updateTurn(state.turns, event.turn_id, (turn) => ({
              ...turn,
              tools: turn.tools.map((tool) =>
                tool.callId === event.call_id
                  ? {
                      ...tool,
                      status: event.status,
                      ...(event.preview ? { preview: event.preview } : {}),
                      durationMs: event.duration_ms,
                    }
                  : tool,
              ),
            })),
          };

        case "retrieval.hits":
          return {
            turns: updateTurn(state.turns, event.turn_id, (turn) => ({
              ...turn,
              tools: turn.tools.map((tool) =>
                tool.callId === event.call_id ? { ...tool, hits: event.hits } : tool,
              ),
            })),
          };

        case "turn.end":
          return {
            turns: updateTurn(state.turns, event.turn_id, (turn) => ({
              ...turn,
              status: event.reason,
              ...(event.message ? { error: event.message } : {}),
              ...(event.stats ? { stats: event.stats } : {}),
              endedAt: Date.now(),
            })),
          };

        case "error":
          return { lastError: `${event.code}: ${event.message}` };

        case "heartbeat":
        case "pong":
          return {};

        default:
          return {};
      }
    }),
}));

export const isStreaming = (turns: Turn[]): boolean =>
  turns.some((turn) => turn.status === "streaming");
