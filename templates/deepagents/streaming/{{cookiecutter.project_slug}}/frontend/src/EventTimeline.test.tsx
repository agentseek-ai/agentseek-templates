import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import EventTimeline, { type StreamEvent } from "./EventTimeline";

describe("EventTimeline", () => {
  it("presents subagent, tool, values, output, and raw events distinctly", () => {
    const events: StreamEvent[] = [
      { kind: "subagent", phase: "started", name: "researcher", status: "started", path: ["researcher:1"] },
      { kind: "tool_call", phase: "failed", tool_name: "inspect_streaming_topic", error: "offline", source: "subagent" },
      { kind: "values", snapshot: { messages: [] } },
      { kind: "output", output: { status: "completed" } },
      { kind: "output", phase: "failed", error: "output unavailable" },
      { kind: "raw", sequence: 8, method: "messages", namespace: [], data: {} },
      { kind: "error", message: "stream failed" },
    ];
    render(<EventTimeline events={events} />);
    expect(screen.getByText("researcher")).toBeTruthy();
    expect(screen.getByText("inspect_streaming_topic")).toBeTruthy();
    expect(screen.getByText("values · state snapshot")).toBeTruthy();
    expect(screen.getByText("output · final run state")).toBeTruthy();
    expect(screen.getByText("output · failed")).toBeTruthy();
    expect(screen.getByText(/output unavailable/)).toBeTruthy();
    expect(screen.getByText(/raw · seq 8/)).toBeTruthy();
    expect(screen.getByText("stream failed")).toBeTruthy();
  });
});
