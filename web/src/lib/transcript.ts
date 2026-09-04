import type { Turn } from "@/state/chatStore";
import { duration, usd } from "@/lib/format";

export function turnTranscript(turn: Turn): string {
  const lines: string[] = [];

  if (turn.question) {
    lines.push(`Q: ${turn.question}`, "");
  }

  turn.tools.forEach((tool, index) => {
    const step = String(index + 1).padStart(2, "0");
    const elapsed = tool.durationMs === undefined ? "running" : `${tool.durationMs}ms`;
    lines.push(`[${step}] ${tool.name}  (${tool.status}, ${elapsed})`);
    lines.push(`     args: ${JSON.stringify(tool.arguments)}`);
    for (const hit of tool.hits) {
      lines.push(`     hit:  ${hit.citation}`);
    }
    if (tool.preview !== undefined && tool.preview.length > 0) {
      lines.push(`     result: ${tool.preview}`);
    }
    lines.push("");
  });

  lines.push("--- answer ---", turn.text);

  if (turn.status !== "completed") {
    lines.push("", `[turn ${turn.status}${turn.error ? `: ${turn.error}` : ""}]`);
  }

  // a transcript pasted into a PR carries its provenance; cost is part of that
  if (turn.stats) {
    const s = turn.stats;
    const parts = [
      s.model || "unknown model",
      s.ttft_ms === null ? null : `${duration(s.ttft_ms)} to first token`,
      `${duration(s.duration_ms)} total`,
      `${s.prompt_tokens} in / ${s.completion_tokens} out tokens`,
      s.cost_usd === null ? "cost unknown" : usd(s.cost_usd),
      `${s.steps} steps`,
      `${s.tool_calls} tool calls`,
    ].filter((part): part is string => part !== null);
    lines.push("", `[${parts.join(", ")}]`);
  }

  return lines.join("\n");
}
