import { sourceUrl, type Snapshots } from "@/lib/citations";
import "./CitationLink.css";

interface Props {
  path: string;
  line: number | undefined;
  snapshots: Snapshots;
  label?: string;
}

export function CitationLink({ path, line, snapshots, label }: Props) {
  const href = sourceUrl(path, line, snapshots);
  const text = label ?? (line === undefined ? path : `${path}:${line}`);
  const ref = href.split("/blob/")[1]?.split("/")[0];
  return (
    <a
      className="citation mono"
      href={href}
      target="_blank"
      rel="noreferrer"
      title={ref === "main" ? "at main" : `at commit ${ref?.slice(0, 12) ?? ""}`}
    >
      {text}
    </a>
  );
}
