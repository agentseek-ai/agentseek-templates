import { describe, expect, it } from "vitest";
import { parseEvidence } from "./evidence";

describe("AgentBase evidence protocol", () => {
  it("normalizes LangChain Document metadata including score", () => {
    const [evidence] = parseEvidence(null, [{
      page_content: "The guide is in docs.",
      metadata: { score: 0.984, agentbase_chunk_id: "chunk-1", source: { name: "guide.md" } },
    }]);
    expect(evidence).toMatchObject({ content: "The guide is in docs.", score: 0.984, chunk_id: "chunk-1" });
  });

  it("parses serialized evidence and tolerates malformed payloads", () => {
    expect(parseEvidence('AGENTBASE_EVIDENCE_JSON=[{"content":"answer","score":1}]', null)[0].score).toBe(1);
    expect(parseEvidence("AGENTBASE_EVIDENCE_JSON=not-json", null)).toEqual([]);
  });
});
