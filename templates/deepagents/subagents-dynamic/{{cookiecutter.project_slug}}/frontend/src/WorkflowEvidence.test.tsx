{% raw %}
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import WorkflowEvidence, {
  findEvalCall,
  type SubagentActivity,
  type WorkflowMessage,
} from "./WorkflowEvidence";

afterEach(cleanup);

const evalMessages: WorkflowMessage[] = [
  { id: "human-1", type: "human", content: "Run a workflow for these requests" },
  {
    id: "ai-1",
    type: "ai",
    content: "",
    tool_calls: [{ id: "eval-1", name: "eval", args: { code: "await runDynamicWork();" } }],
  },
];

describe("WorkflowEvidence", () => {
  it("uses the latest interpreter attempt after the model retries", () => {
    const messages: WorkflowMessage[] = [
      ...evalMessages,
      { id: "tool-1", type: "tool", content: "<error>syntax</error>", tool_call_id: "eval-1" },
      {
        id: "ai-2",
        type: "ai",
        content: "Retrying",
        tool_calls: [{ id: "eval-2", name: "eval", args: { code: "await task({});" } }],
      },
    ];

    expect(findEvalCall(messages)?.id).toBe("eval-2");
  });

  it("does not claim a dynamic trigger from the keyword alone", () => {
    render(
      <WorkflowEvidence
        messages={[evalMessages[0]]}
        activities={[]}
        isLoading
      />,
    );

    expect(screen.getByTestId("keyword-stage").getAttribute("data-state")).toBe("complete");
    expect(screen.getByTestId("trigger-stage").getAttribute("data-state")).toBe("waiting");
    expect(screen.getByText("等待解释器调用")).toBeTruthy();
  });

  it("shows actual subagent stream roles and statuses", () => {
    const activities: SubagentActivity[] = [
      { id: "a", name: "reviewer", description: "orders.py", status: "complete" },
      { id: "b", name: "reviewer", description: "refunds.py", status: "running" },
    ];

    render(<WorkflowEvidence messages={evalMessages} activities={activities} isLoading />);

    expect(screen.getByTestId("trigger-stage").getAttribute("data-state")).toBe("complete");
    expect(screen.getByTestId("dispatch-stage").getAttribute("data-state")).toBe("running");
    expect(screen.getByText("reviewer · orders.py")).toBeTruthy();
    expect(screen.getByText("reviewer · refunds.py")).toBeTruthy();
    expect(screen.getByText("1 / 2 completed")).toBeTruthy();
  });

  it("marks the pattern complete only after interpreter result and final answer", () => {
    const completed: WorkflowMessage[] = [
      ...evalMessages,
      {
        id: "tool-1",
        type: "tool",
        content: '<stdout>progress</stdout>\n<result kind="json">{}</result>',
        tool_call_id: "eval-1",
      },
      { id: "ai-2", type: "ai", content: "## Result\nAll work is complete." },
    ];
    const activities: SubagentActivity[] = [
      { id: "a", name: "reviewer", description: "route", status: "complete" },
    ];

    render(<WorkflowEvidence messages={completed} activities={activities} isLoading={false} />);

    expect(screen.getByTestId("complete-stage").getAttribute("data-state")).toBe("complete");
    expect(screen.getByText("当前 Pattern 已达到结束条件")).toBeTruthy();
  });

  it("keeps a failed interpreter result from being marked complete", () => {
    const failed: WorkflowMessage[] = [
      ...evalMessages,
      {
        id: "tool-1",
        type: "tool",
        content: '<stdout>progress</stdout>\n<error type="Error">boom</error>',
        tool_call_id: "eval-1",
      },
      { id: "ai-2", type: "ai", content: "The run failed, so no result is available." },
    ];
    const activities: SubagentActivity[] = [
      { id: "a", name: "reviewer", description: "route", status: "complete" },
    ];

    render(<WorkflowEvidence messages={failed} activities={activities} isLoading={false} />);

    expect(screen.getByTestId("complete-stage").getAttribute("data-state")).toBe("error");
    expect(screen.getByText("解释器返回错误，当前 Pattern 未完成")).toBeTruthy();
  });
});
{% endraw %}
