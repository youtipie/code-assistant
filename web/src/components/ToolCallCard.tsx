import { memo, useState } from "react";
import type { ToolInvocation } from "@/state/chatStore";
import { CitationLink } from "./CitationLink";
import type { Snapshots } from "@/lib/citations";
import "./ToolCallCard.css";

interface Props {
  tool: ToolInvocation;
  step: number;
  snapshots: Snapshots;
}

function summarise(tool: ToolInvocation): string {
  const args = tool.arguments;
  const parts: string[] = [];
  if (typeof args["repo"] === "string") {
    // args is Record<string, unknown>: String() on a non-string owner would
    // render "[object Object]" into the card
    const owner = typeof args["owner"] === "string" ? args["owner"] : "";
    parts.push(`${owner}/${args["repo"]}`);
  }
  const subject = args["query"] ?? args["path"] ?? args["q"];
  if (typeof subject === "string") parts.push(subject);
  if (typeof args["symbol"] === "string") parts.push(`::${args["symbol"]}`);
  return parts.join(" ");
}

function duration(tool: ToolInvocation): string | null {
  if (tool.endedAt === undefined) return null;
  const ms = tool.endedAt - tool.startedAt;
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

// memo, because a streaming answer re-renders its turn once per token delta
// (thousands per turn) and a finished tool card never changes. chatStore's
// updateTurn rebuilds only the tool whose event arrived, so every other card
// keeps its object identity and this bails out.
export const ToolCallCard = memo(function ToolCallCard({ tool, step, snapshots }: Props) {
  const [open, setOpen] = useState(false);
  const elapsed = duration(tool);
  const detail = summarise(tool);

  return (
    <li className={`tool tool--${tool.server} tool--${tool.status}`}>
      <span className="tool__step mono" aria-hidden="true">
        {String(step).padStart(2, "0")}
      </span>

      <div className="tool__body">
        <button
          type="button"
          className="tool__head"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
        >
          <span className="tool__name mono">{tool.name}</span>
          {tool.server === "github" && <span className="tool__live">live</span>}
          {detail && <span className="tool__detail mono">{detail}</span>}
          <span className="tool__meta">
            {tool.status === "running" && <span className="tool__pulse" aria-label="running" />}
            {tool.status === "error" && <span className="tool__failed">failed</span>}
            {elapsed && <span className="tool__time mono">{elapsed}</span>}
          </span>
        </button>

        {tool.hits.length > 0 && (
          <ul className="tool__hits">
            {tool.hits.map((hit) => (
              <li key={hit.citation}>
                <CitationLink
                  path={hit.path}
                  line={hit.start_line}
                  snapshots={snapshots}
                  label={hit.citation}
                />
              </li>
            ))}
          </ul>
        )}

        {open && (
          <div className="tool__expanded">
            <dl className="tool__args">
              {Object.entries(tool.arguments).map(([key, value]) => (
                <div key={key}>
                  <dt className="mono">{key}</dt>
                  <dd className="mono">{JSON.stringify(value)}</dd>
                </div>
              ))}
            </dl>
            {tool.preview && <pre className="tool__preview">{tool.preview}</pre>}
          </div>
        )}
      </div>
    </li>
  );
});
