import { FormEvent, useMemo, useState } from "react";
import EventTimeline, { type StreamEvent } from "./EventTimeline";
import MemoryPanel, { DEMO_QUESTION } from "./MemoryPanel";

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
  const [recallEnabled, setRecallEnabled] = useState(true);
  const [maxBytes, setMaxBytes] = useState(8000);
  const [lastQuestion, setLastQuestion] = useState("");
  const [showDebug, setShowDebug] = useState(false);
  const counts = useMemo(() => projectionCounts(events), [events]);
  const visibleEvents = showDebug ? events : events.filter((event) => !["raw", "values", "output"].includes(event.kind));

  function newConversation() {
    setThreadId("");
    setEvents([]);
    setError(null);
    setLastQuestion("");
    const url = new URL(window.location.href);
    url.searchParams.delete("thread");
    window.history.replaceState({}, "", url);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text || isLoading) return;
    setInput("");
    setLastQuestion(text);
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
        body: JSON.stringify({ thread_id: nextThread, messages: [{ role: "user", content: text }], recall_enabled: recallEnabled, max_bytes: maxBytes }),
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
        <p className="eyebrow">Deep Agents + PowerContext</p>
        <h1>{{ cookiecutter.project_name }}</h1>
        <p className="lede">New conversation. Same project knowledge. Save a release decision, start fresh, and watch your agents pick it up from PowerContext.</p>
      </header>

      <MemoryPanel apiUrl={apiUrl} disabled={isLoading} />

      <section className="session-banner" aria-label="Session">
        <p className="eyebrow">02 · Start fresh</p>
        <strong>{threadId ? "Thread active" : "Thread ready"}</strong>
        <span>{threadId ? threadId : "Your next request starts a fresh conversation. Project memory is kept."}</span>
        <div className="actions">
          <button disabled={isLoading} onClick={newConversation}>New conversation</button>
          <label><input type="checkbox" checked={recallEnabled} disabled={isLoading} onChange={(event) => { setRecallEnabled(event.target.checked); newConversation(); }} /> Recall project memory</label>
          <label>Context budget <select value={maxBytes} disabled={isLoading} onChange={(event) => { setMaxBytes(Number(event.target.value)); newConversation(); }}>
            <option value={512}>512 bytes</option><option value={2000}>2,000 bytes</option><option value={8000}>8,000 bytes</option>
          </select></label>
        </div>
        <p className="hint">Changing recall or its budget starts a fresh conversation for comparison. The backend may apply a lower configured budget.</p>
      </section>

      <div className="section-heading"><div><p className="eyebrow">03 · Recall and inspect</p><h2>Plan the next release</h2></div>
        <button className="secondary" disabled={isLoading} onClick={() => setInput(DEMO_QUESTION)}>Try release question</button>
      </div>

      <form className="composer" onSubmit={onSubmit}>
        <input aria-label="Message" value={input} onChange={(event) => setInput(event.target.value)} placeholder="Ask about your project's release…" disabled={isLoading} />
        <button type="submit" disabled={isLoading || !input.trim()}>Send</button>
      </form>
      {lastQuestion && <p className="question">{lastQuestion}</p>}

      <section className="projection-strip" aria-label="Projection summary">
        <div><strong>{counts.powercontext ?? 0}</strong><span>PowerContext events</span></div>
        <div><strong>{counts.subagent ?? 0}</strong><span>subagent events</span></div>
        <div><strong>{counts.message ?? 0}</strong><span>messages</span></div>
        <div><strong>{counts.tool_call ?? 0}</strong><span>tool events</span></div>
        <div><strong>{counts.values ?? 0}</strong><span>state snapshots</span></div>
        <div><strong>{counts.raw ?? 0}</strong><span>raw events</span></div>
      </section>

      <label className="debug-toggle"><input type="checkbox" checked={showDebug} onChange={(event) => setShowDebug(event.target.checked)} /> Show protocol and state details</label>
      <EventTimeline events={visibleEvents} />
      {isLoading && <div className="activity" aria-live="polite">Streaming the run…</div>}
      {error && <p className="error-text">{error}</p>}
      {events.length === 0 && !isLoading && <p className="hint">Try: “{DEMO_QUESTION}” Then turn recall off and ask the same question in a fresh conversation.</p>}
    </main>
  );
}
