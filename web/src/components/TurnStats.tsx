import { memo } from "react";
import type { TurnStats as Stats } from "@/protocol/events";
import { duration, tokens, usd } from "@/lib/format";
import "./TurnStats.css";

interface Props {
  stats: Stats;
}

/** Untruncated numbers for the tooltip; the visible row is terse. */
function detail(stats: Stats): string {
  const lines = [
    `model: ${stats.model || "unknown"}`,
    `prompt: ${stats.prompt_tokens} tokens ` +
      `(${stats.cached_tokens} cache read, ${stats.cache_write_tokens} cache write)`,
    `completion: ${stats.completion_tokens} tokens`,
    `total: ${stats.duration_ms} ms`,
  ];
  if (stats.ttft_ms !== null) lines.push(`first token: ${stats.ttft_ms} ms`);
  lines.push(
    stats.cost_usd === null
      ? "cost: no price on file for this model"
      : `cost: $${stats.cost_usd.toFixed(6)}`,
  );
  return lines.join("\n");
}

// memo for the same reason AssistantTurn is: the turn list rebuilds on every
// token delta, and stats arrive once and never change afterwards.
export const TurnStats = memo(function TurnStats({ stats }: Props) {
  return (
    <dl className="stats" title={detail(stats)}>
      <div className="stats__item">
        <dt className="visually-hidden">Model</dt>
        <dd className="stats__value mono">{stats.model || "unknown"}</dd>
      </div>

      {stats.ttft_ms !== null && (
        <div className="stats__item">
          <dt>first token</dt>
          <dd className="stats__value mono">{duration(stats.ttft_ms)}</dd>
        </div>
      )}

      <div className="stats__item">
        <dt>total</dt>
        <dd className="stats__value mono">{duration(stats.duration_ms)}</dd>
      </div>

      <div className="stats__item">
        <dt>tokens</dt>
        <dd className="stats__value mono">
          {tokens(stats.prompt_tokens)} in / {tokens(stats.completion_tokens)} out
        </dd>
      </div>

      <div className="stats__item">
        <dt>cost</dt>
        {/* a dash, never an estimate: see core/pricing.py */}
        <dd className="stats__value mono">
          {stats.cost_usd === null ? "—" : usd(stats.cost_usd)}
        </dd>
      </div>

      <div className="stats__item">
        <dt>steps</dt>
        <dd className="stats__value mono">{stats.steps}</dd>
      </div>

      {stats.tool_calls > 0 && (
        <div className="stats__item">
          <dt>tools</dt>
          <dd className="stats__value mono">{stats.tool_calls}</dd>
        </div>
      )}
    </dl>
  );
});
