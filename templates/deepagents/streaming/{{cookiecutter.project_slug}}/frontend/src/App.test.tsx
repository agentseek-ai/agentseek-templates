import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

afterEach(() => cleanup());

describe("Event Streaming UI", () => {
  it("renders the projection vocabulary and empty state", () => {
    render(<App />);
    expect(screen.getByText("Deep Agents · Event Streaming v3")).toBeTruthy();
    expect(screen.getByText("subagent events")).toBeTruthy();
    expect(screen.getByText(/Explain the difference/)).toBeTruthy();
  });

  it("posts the thread and renders streamed SSE events", async () => {
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('data: {"kind":"message","source":"coordinator","text":"hello"}\n\n'));
        controller.enqueue(new TextEncoder().encode('data: {"kind":"output","output":{"done":true}}\n\n'));
        controller.close();
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(new Response(body, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "thread-test" });

    render(<App />);
    fireEvent.change(screen.getByPlaceholderText("Ask about Event Streaming…"), {
      target: { value: "Explain v3" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(screen.getByText("hello")).toBeTruthy());
    expect(screen.getByText("output · final run state")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:2024/custom/stream",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ thread_id: "thread-test", messages: [{ role: "user", content: "Explain v3" }] }),
      }),
    );
    expect(window.location.search).toContain("thread=thread-test");
  });

  it("renders a structured stream error", async () => {
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('data: {"kind":"error","message":"provider unavailable"}\n\n'));
        controller.close();
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { status: 200 })));

    render(<App />);
    fireEvent.change(screen.getByPlaceholderText("Ask about Event Streaming…"), {
      target: { value: "Trigger error" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(screen.getByText("provider unavailable")).toBeTruthy());
  });
});
