const CITATION = /\b([\w./-]+\.(?:py|mdx?|graphql|ya?ml|toml|json))(?::(\d+))?/g;

export interface CorpusRepo {
  repo: string;
  prefix: string;
}

export const DEFAULT_REPOS: CorpusRepo[] = [
  { repo: "saleor/saleor", prefix: "saleor/" },
  { repo: "saleor/saleor-docs", prefix: "docs/" },
];

export function repoForPath(path: string, repos: CorpusRepo[] = DEFAULT_REPOS): string {
  let best = "";
  let chosen = repos[0]?.repo ?? "";
  for (const { repo, prefix } of repos) {
    if (prefix && path.startsWith(prefix) && prefix.length > best.length) {
      best = prefix;
      chosen = repo;
    }
  }
  return chosen;
}

export type Snapshots = Record<string, string>;

export function sourceUrl(
  path: string,
  line: number | undefined,
  snapshots: Snapshots,
  repos: CorpusRepo[] = DEFAULT_REPOS,
): string {
  const repo = repoForPath(path, repos);
  const ref = snapshots[repo] ?? "main";
  const fragment = line === undefined ? "" : `#L${line}`;
  return `https://github.com/${repo}/blob/${ref}/${path}${fragment}`;
}

export interface CitationMatch {
  text: string;
  path: string;
  line: number | undefined;
  index: number;
}

export function findCitations(text: string): CitationMatch[] {
  const found: CitationMatch[] = [];
  for (const match of text.matchAll(CITATION)) {
    const [full, path, line] = match;
    if (path === undefined) continue;
    found.push({
      text: full,
      path,
      line: line === undefined ? undefined : Number(line),
      index: match.index,
    });
  }
  return found;
}
