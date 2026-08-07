import type { Turn } from "@/state/chatStore";

export function turnTranscript(turn: Turn): string {
  const lines: string[] = [];

  if (turn.question) {
    lines.push(`Q: ${turn.question}`, "");
  }

  turn.tools.forEach((tool, index) => {
    const step = String(index + 1).padStart(2, "0");
    const elapsed =
      tool.endedAt === undefined ? "running" : `${tool.endedAt - tool.startedAt}ms`;
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

  return lines.join("\n");
}
