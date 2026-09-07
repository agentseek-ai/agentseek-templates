export type Evidence = {
  content: string;
  source?: Record<string, unknown>;
  locator?: Record<string, unknown>;
  score?: number;
  chunk_id?: string;
  source_id?: string;
  index_source?: string;
};

export function normalizeEvidence(item: any): Evidence {
  if (!item?.metadata) return item as Evidence;
  const metadata = item.metadata as Record<string, any>;
  return {
    content: String(item.page_content ?? item.content ?? ""),
    source: metadata.source ?? {},
    locator: metadata.locator ?? {},
    score: typeof metadata.score === "number" ? metadata.score : undefined,
    chunk_id: metadata.agentbase_chunk_id,
    source_id: metadata.agentbase_source_id,
    index_source: metadata.index_source,
  };
}

export function parseEvidence(result: string | null, artifact: unknown): Evidence[] {
  if (Array.isArray(artifact)) return artifact.map(normalizeEvidence);
  const marker = "AGENTBASE_EVIDENCE_JSON=";
  if (!result?.startsWith(marker)) return [];
  try {
    const value = JSON.parse(result.slice(marker.length));
    return Array.isArray(value) ? value.map(normalizeEvidence) : [];
  } catch {
    return [];
  }
}
