import { memo, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Turn } from "@/state/chatStore";
import { findCitations, sourceUrl, type Snapshots } from "@/lib/citations";
import { turnTranscript } from "@/lib/transcript";
import { ToolCallCard } from "./ToolCallCard";
import { UserMessage } from "./UserMessage";
import { CopyButton } from "./CopyButton";
import { TurnStats } from "./TurnStats";
import "./AssistantTurn.css";

interface Props {
  turn: Turn;
  snapshots: Snapshots;
}

function linkify(text: string, snapshots: Snapshots): string {
  const citations = findCitations(text);
  if (citations.length === 0) return text;

  let result = "";
  let cursor = 0;
  for (const citation of citations) {
    const before = text.slice(cursor, citation.index);
    const inCode = (before.match(/`/g)?.length ?? 0) % 2 === 1;
    result += before;
    if (inCode) {
      result += citation.text;
    } else {
      result += `[${citation.text}](${sourceUrl(citation.path, citation.line, snapshots)})`;
    }
    cursor = citation.index + citation.text.length;
  }
  return result + text.slice(cursor);
}

/** `value`, but updated at most once per `ms` while `active`.
 *
 * A streamed answer arrives as thousands of deltas -- 2,438 in a measured
 * turn -- and re-parsing the markdown that often froze the main thread. Once
 * `active` goes false the exact final value lands immediately.
 */
function useThrottled(value: string, ms: number, active: boolean): string {
  const [shown, setShown] = useState(value);
  const lastUpdate = useRef(0);

  useEffect(() => {
    if (!active) {
      setShown(value);
      return;
    }
    const elapsed = Date.now() - lastUpdate.current;
    if (elapsed >= ms) {
      lastUpdate.current = Date.now();
      setShown(value);
      return;
    }
    const timer = window.setTimeout(() => {
      lastUpdate.current = Date.now();
      setShown(value);
    }, ms - elapsed);
    return () => {
      window.clearTimeout(timer);
    };
  }, [value, ms, active]);

  return shown;
}

// memo, because ChatRoute re-renders the whole turn list on every token
// delta: without this, each delta re-parsed the markdown of every *finished*
// turn too. chatStore's updateTurn only rebuilds the turn its event names.
export const AssistantTurn = memo(function AssistantTurn({ turn, snapshots }: Props) {
  const streaming = turn.status === "streaming";
  const source = useThrottled(turn.text, 80, streaming);

  // hold the element identity steady so React skips the subtree when only
  // the surrounding turn changed
  const answer = useMemo(
    () => <ReactMarkdown remarkPlugins={[remarkGfm]}>{linkify(source, snapshots)}</ReactMarkdown>,
    [source, snapshots],
  );

  return (
    <article className="turn" aria-busy={streaming}>
      {turn.question && <UserMessage text={turn.question} />}

      <span className="turn__who">Assistant</span>

      {turn.tools.length > 0 && (
        <ol className="turn__trace" aria-label="tool calls">
          {turn.tools.map((tool, index) => (
            <ToolCallCard
              key={tool.callId}
              tool={tool}
              step={index + 1}
              snapshots={snapshots}
            />
          ))}
        </ol>
      )}

      {turn.text && <div className="turn__answer">{answer}</div>}

      {!streaming && (turn.text || turn.stats) && (
        <div className="turn__actions">
          {turn.text && <CopyButton text={turnTranscript(turn)} label="Copy transcript" />}
          {turn.stats && <TurnStats stats={turn.stats} />}
        </div>
      )}

      {streaming && !turn.text && <p className="turn__waiting">Working…</p>}

      {turn.status === "cancelled" && (
        <p className="turn__note">
          {turn.text ? "Stopped." : "No answer was recorded for this question."}
        </p>
      )}
      {turn.status === "error" && (
        <p className="turn__note turn__note--error">{turn.error ?? "That turn failed."}</p>
      )}
    </article>
  );
});
