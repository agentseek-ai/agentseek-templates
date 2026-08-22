{% raw %}
import { describe, expect, it } from "vitest";
import { PATTERNS } from "./patterns";

describe("pattern catalog", () => {
  it("maps the six official patterns to six independent assistants", () => {
    expect(PATTERNS.map((pattern) => pattern.assistantId)).toEqual([
      "classify_and_act",
      "fan_out_and_synthesize",
      "adversarial_verification",
      "generate_and_filter",
      "tournament",
      "loop_until_done",
    ]);
  });

  it("keeps example prompts natural while retaining the workflow trigger", () => {
    const forbidden = [
      "eval",
      "task()",
      "subagenttype",
      "responseschema",
      "bug-fixer",
      "feature-analyst",
      "support-agent",
      "reviewer",
      "verifier",
      "architect",
      "writer",
      "judge",
      "analyzer",
    ];

    for (const pattern of PATTERNS) {
      const prompt = pattern.prompt.toLowerCase();
      expect(prompt).toContain("workflow");
      for (const token of forbidden) expect(prompt).not.toContain(token);
    }
  });
});
{% endraw %}
