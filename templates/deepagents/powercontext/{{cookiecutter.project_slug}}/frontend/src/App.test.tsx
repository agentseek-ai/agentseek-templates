import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { StreamEvent } from "./EventTimeline";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); window.history.replaceState({}, "", "/"); });

function mockBackend(events: StreamEvent[] = [{ kind: "message", source: "coordinator", text: "hello" }]) {
  const fetchMock = vi.fn(async (url: string, _options?: RequestInit) => {
    if (url.endsWith("/custom/memory")) return Response.json({ scope_id: "scope-test", entries: [] });
    return new Response(new ReadableStream({ start(controller) {
      for (const event of events) controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`));
      controller.close();
    } }), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("crypto", { randomUUID: vi.fn().mockReturnValueOnce("thread-first").mockReturnValueOnce("thread-second") });
  return fetchMock;
}

async function send(text = "Project Phoenix release?") {
  fireEvent.change(screen.getByRole("textbox", { name: "Message" }), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await waitFor(() => expect(screen.queryByText("Streaming the run…")).toBeNull());
}

describe("Project continuity UI", () => {
  it("offers explicit memory writes and fresh-conversation controls", async () => {
    mockBackend();
    render(<App />);
    expect(screen.getByText("Deep Agents + PowerContext")).toBeTruthy();
    expect(screen.getByRole("button", { name: "New conversation" })).toBeTruthy();
    await waitFor(() => expect(screen.getByRole("button", { name: "Save decision" })).toBeTruthy());
  });

  it("streams the question with a run-local recall switch and budget", async () => {
    const fetchMock = mockBackend();
    render(<App />);
    await send();
    await waitFor(() => expect(screen.getByText("hello")).toBeTruthy());
    const call = fetchMock.mock.calls.find(([url]) => url.endsWith("/custom/stream"))!;
    expect(JSON.parse(call[1]!.body as string)).toEqual({
      thread_id: "thread-first", messages: [{ role: "user", content: "Project Phoenix release?" }], recall_enabled: true, max_bytes: 8000,
    });
    expect(window.location.search).toContain("thread=thread-first");
  });

  it("uses a fresh thread when disabling recall and keeps durable memory visible", async () => {
    const fetchMock = mockBackend();
    render(<App />);
    await send();
    await waitFor(() => expect(screen.getByText("hello")).toBeTruthy());
    fireEvent.click(screen.getByRole("checkbox", { name: "Recall project memory" }));
    expect(window.location.search).not.toContain("thread=");
    expect(screen.queryByText("hello")).toBeNull();
    expect(screen.getByRole("button", { name: "Save decision" })).toBeTruthy();
    await send();
    const calls = fetchMock.mock.calls.filter(([url]) => url.endsWith("/custom/stream"));
    const payload = JSON.parse(calls[1][1]!.body as string);
    expect(payload.thread_id).toBe("thread-second");
    expect(payload.recall_enabled).toBe(false);
    expect(payload.messages).toHaveLength(1);
  });

  it("renders stream failures", async () => {
    mockBackend([{ kind: "error", source: "coordinator", text: "", message: "provider unavailable" }]);
    render(<App />);
    await send();
    await waitFor(() => expect(screen.getByText("provider unavailable")).toBeTruthy());
  });
});
