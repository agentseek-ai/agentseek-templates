import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import EventTimeline, { type StreamEvent } from "./EventTimeline";

describe("EventTimeline", () => {
  it("shows only the recalled PowerContext context, the answer, and stream errors", () => {
    const events: StreamEvent[] = [
      { kind: "subagent", phase: "started", name: "researcher", status: "started", path: ["researcher:1"] },
      { kind: "tool_call", phase: "failed", tool_name: "release_checklist", error: "offline", source: "subagent" },
      { kind: "values", snapshot: { messages: [] } },
      { kind: "output", output: { status: "completed" } },
      { kind: "output", phase: "failed", error: "output unavailable" },
      { kind: "raw", sequence: 8, method: "messages", namespace: [], data: {} },
      { kind: "powercontext", status: "ready", content_bytes: 42, max_bytes: 8000, content: "Phoenix: Singapore, Tuesday" },
      { kind: "message", source: "coordinator", text: "Deploy to Singapore on Tuesday.", path: [] },
      { kind: "error", message: "stream failed" },
    ];
    render(<EventTimeline events={events} />);

    expect(screen.getByText(/PowerContext · ready/)).toBeTruthy();
    expect(screen.getByText(/Phoenix: Singapore, Tuesday/)).toBeTruthy();
    expect(screen.getByText("Deploy to Singapore on Tuesday.")).toBeTruthy();
    expect(screen.getByText("stream failed")).toBeTruthy();

    expect(screen.queryByText("researcher")).toBeNull();
    expect(screen.queryByText("release_checklist")).toBeNull();
    expect(screen.queryByText("values · state snapshot")).toBeNull();
    expect(screen.queryByText("output · final run state")).toBeNull();
    expect(screen.queryByText("output · failed")).toBeNull();
    expect(screen.queryByText(/output unavailable/)).toBeNull();
    expect(screen.queryByText(/raw · seq/)).toBeNull();
  });
});
