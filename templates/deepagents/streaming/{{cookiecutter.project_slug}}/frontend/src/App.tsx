import { FormEvent, useMemo, useState } from "react";
import EventTimeline, { type StreamEvent } from "./EventTimeline";

function projectionCounts(events: StreamEvent[]): Record<string, number> {
  return events.reduce<Record<string, number>>((counts, event) => {
    counts[event.kind] = (counts[event.kind] ?? 0) + 1;
    return counts;
  }, {});
}

async function readSse(response: Response, onEvent: (event: StreamEvent) => void): Promise<void> {
  if (!response.ok || !response.body) throw new Error(`Streaming request failed (${response.status})`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const chunk = await reader.read();
    buffer += decoder.decode(chunk.value ?? new Uint8Array(), { stream: !chunk.done });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (line.startsWith("data: ")) onEvent(JSON.parse(line.slice(6)) as StreamEvent);
    }
    if (chunk.done) break;
  }
}

export default function App() {
  const apiUrl = import.meta.env.VITE_STREAMING_API_URL ?? "http://127.0.0.1:{{ cookiecutter.langgraph_port }}";
  const [input, setInput] = useState("");
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [threadId, setThreadId] = useState(() => new URLSearchParams(window.location.search).get("thread") ?? "");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const counts = useMemo(() => projectionCounts(events), [events]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text || isLoading) return;
    setInput("");
    setEvents([]);
    setError(null);
    setIsLoading(true);
    const nextThread = threadId || crypto.randomUUID();
    setThreadId(nextThread);
    const url = new URL(window.location.href);
    url.searchParams.set("thread", nextThread);
    window.history.replaceState({}, "", url);
    try {
      const response = await fetch(`${apiUrl}/custom/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ thread_id: nextThread, messages: [{ role: "user", content: text }] }),
      });
      await readSse(response, (next) => setEvents((current) => [...current, next]));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main>
      <header className="hero">
        <p className="eyebrow">Deep Agents · Event Streaming v3</p>
        <h1>{{ cookiecutter.project_name }}</h1>
        <p className="lede">Watch coordinator messages, delegated sub-agents, tool execution, state snapshots, final output, and the raw protocol arrive as one run unfolds.</p>
      </header>

      <section className="session-banner" aria-label="Session">
        <strong>{threadId ? "Thread active" : "Thread ready"}</strong>
        <span>{threadId ? threadId : "A stable thread id is created when you send the first request."}</span>
      </section>

      <section className="projection-strip" aria-label="Projection summary">
        <div><strong>{counts.subagent ?? 0}</strong><span>subagent events</span></div>
        <div><strong>{counts.message ?? 0}</strong><span>messages</span></div>
        <div><strong>{counts.tool_call ?? 0}</strong><span>tool events</span></div>
        <div><strong>{counts.values ?? 0}</strong><span>state snapshots</span></div>
        <div><strong>{counts.raw ?? 0}</strong><span>raw events</span></div>
      </section>

      <EventTimeline events={events} />
      {isLoading && <div className="activity" aria-live="polite">Streaming the run…</div>}
      {error && <p className="error-text">{error}</p>}
      {events.length === 0 && !isLoading && <p className="hint">Try: “Explain the difference between subagents and subgraphs in Event Streaming v3.”</p>}

      <form className="composer" onSubmit={onSubmit}>
        <input value={input} onChange={(event) => setInput(event.target.value)} placeholder="Ask about Event Streaming…" disabled={isLoading} autoFocus />
        <button type="submit" disabled={isLoading || !input.trim()}>Send</button>
      </form>
    </main>
  );
}
