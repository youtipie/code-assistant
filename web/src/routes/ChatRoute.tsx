import { useCallback, useEffect, useMemo, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Message } from "@/api/client";
import { AssistantTurn } from "@/components/AssistantTurn";
import { Composer } from "@/components/Composer";
import { ServerStatusBar } from "@/components/ServerStatusBar";
import { useChatSocket } from "@/transport/useChatSocket";
import {
  isStreaming,
  serverOf,
  useChatStore,
  type ToolInvocation,
  type Turn,
} from "@/state/chatStore";
import "./ChatRoute.css";

const EXAMPLES = [
  "What is the deployment architecture?",
  "How does a checkout become an order?",
  "When was complete_checkout.py last changed, and by which PR?",
];

/** The stored rows for one turn, as the cards want them.
 *
 * `status` widens to `string` crossing the API boundary; anything outside the
 * three the UI knows was written by a newer server, and "running" is the
 * honest reading -- an outcome we cannot vouch for either way.
 */
function toolsFromHistory(tools: Message["tools"]): ToolInvocation[] {
  return tools.map((tool) => ({
    callId: tool.call_id,
    name: tool.name,
    server: serverOf(tool.name),
    arguments: tool.arguments,
    status:
      tool.status === "ok" || tool.status === "error" ? tool.status : "running",
    ...(tool.preview ? { preview: tool.preview } : {}),
    hits: tool.hits,
    ...(tool.duration_ms === null ? {} : { durationMs: tool.duration_ms }),
  }));
}

function turnsFromHistory(messages: Message[]): Turn[] {
  const turns: Turn[] = [];
  let question = "";
  for (const message of messages) {
    if (message.role === "user") {
      question = message.text;
      continue;
    }
    if (message.role !== "assistant") continue;
    turns.push({
      id: message.turn_id ?? `history-${turns.length}`,
      question,
      text: message.text,
      tools: toolsFromHistory(message.tools),
      status: "completed",
      startedAt: 0,
      ...(message.stats ? { stats: message.stats } : {}),
    });
    question = "";
  }

  if (question) {
    // a question whose turn wrote no assistant message: cancelled, or the
    // reply was lost. Its tool rows hang off a turn_id no message carries.
    turns.push({
      id: `history-pending-${turns.length}`,
      question,
      text: "",
      tools: [],
      status: "cancelled",
      startedAt: 0,
    });
  }
  return turns;
}

export function ChatRoute() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const turns = useChatStore((state) => state.turns);
  const connection = useChatStore((state) => state.connection);
  const storeSessionId = useChatStore((state) => state.sessionId);
  const lastError = useChatStore((state) => state.lastError);
  const loadHistory = useChatStore((state) => state.loadHistory);
  const reset = useChatStore((state) => state.reset);

  const { send, cancel } = useChatSocket();
  const busy = isStreaming(turns);
  const bottom = useRef<HTMLDivElement>(null);

  const { data: status } = useQuery({
    queryKey: ["status"],
    queryFn: api.status,
    refetchInterval: 15_000,
  });

  const { data: history, isError: historyMissing } = useQuery({
    queryKey: ["messages", sessionId],
    queryFn: () => api.messages(sessionId as string),
    enabled: Boolean(sessionId),
    retry: false,
    staleTime: 0,
    refetchOnMount: "always",
  });

  const previousSession = useRef<string | undefined>(undefined);
  useEffect(() => {
    const previous = previousSession.current;
    previousSession.current = sessionId;
    if (previous && sessionId && previous !== sessionId) {
      if (isStreaming(useChatStore.getState().turns)) cancel();
    }
  }, [sessionId, cancel]);

  const hydrated = useRef<string | null>(null);

  useEffect(() => {
    if (!sessionId) {
      hydrated.current = null;
      return;
    }

    if (historyMissing) {
      reset();
      hydrated.current = null;
      navigate("/", { replace: true });
      return;
    }

    if (sessionId === storeSessionId) {
      hydrated.current = sessionId;
      return;
    }

    if (history && hydrated.current !== sessionId) {
      loadHistory(turnsFromHistory(history), sessionId);
      hydrated.current = sessionId;
    }
  }, [
    sessionId,
    storeSessionId,
    history,
    historyMissing,
    loadHistory,
    reset,
    navigate,
  ]);

  useEffect(() => {
    if (!sessionId && storeSessionId && turns.length > 0) {
      navigate(`/s/${storeSessionId}`, { replace: true });
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
    }
  }, [sessionId, storeSessionId, turns.length, navigate, queryClient]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length, busy]);

  const finishedTurns = turns.filter((turn) => turn.status !== "streaming").length;
  useEffect(() => {
    if (finishedTurns > 0) {
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
    }
  }, [finishedTurns, queryClient]);

  const snapshots = useMemo(
    () => Object.fromEntries((status?.snapshots ?? []).map((s) => [s.repo, s.commit])),
    [status],
  );

  const onSend = useCallback(
    (text: string) => {
      send(text);
    },
    [send],
  );

  const empty = useMemo(() => turns.length === 0, [turns.length]);

  return (
    <div className="chat">
      <header className="chat__bar">
        <ServerStatusBar status={status} connection={connection} />
      </header>

      <div className="chat__scroll">
        <div className="chat__inner">
          {empty && (
            <section className="chat__intro">
              <h1 className="chat__title">Ask about the codebase</h1>
              <p className="chat__lede">
                Answers come from an indexed snapshot of the code and docs, and from GitHub for
                anything about history. Every claim links back to the line it came from.
              </p>
              <ul className="chat__examples">
                {EXAMPLES.map((example) => (
                  <li key={example}>
                    <button type="button" onClick={() => onSend(example)}>
                      {example}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {turns.map((turn) => (
            <AssistantTurn key={turn.id} turn={turn} snapshots={snapshots} />
          ))}

          {lastError && <p className="chat__error">{lastError}</p>}
          <div ref={bottom} />
        </div>
      </div>

      <footer className="chat__composer">
        <div className="chat__inner">
          <Composer
            onSend={onSend}
            onCancel={cancel}
            busy={busy}
            disabled={connection !== "open"}
          />
        </div>
      </footer>
    </div>
  );
}
