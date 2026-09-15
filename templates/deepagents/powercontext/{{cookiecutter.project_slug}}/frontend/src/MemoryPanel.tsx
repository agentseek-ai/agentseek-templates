import { useEffect, useState } from "react";

export const DEMO_QUESTION = "What is the release plan for Project Phoenix?";
const DEMO_MEMORY = "Project Phoenix release: deploy to the Singapore region on Tuesday at 10:00 UTC. Require Mei's approval and a tested rollback before release.";

type Entry = {
  text: string;
  version: number;
  citation: { entry_id: string; entry_version_id: string; memory_ref: { revision: number } };
};
type Inventory = { scope_id: string; entries: Entry[] };

export default function MemoryPanel({ apiUrl, disabled }: { apiUrl: string; disabled: boolean }) {
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [text, setText] = useState(DEMO_MEMORY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState("");

  async function request(path = "", body?: object) {
    const response = await fetch(`${apiUrl}/custom/memory${path}`, body === undefined ? undefined : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Memory request failed.");
    return data;
  }

  async function refresh() {
    setBusy(true);
    setError(null);
    try { setInventory(await request()); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load project memory."); }
    finally { setBusy(false); }
  }

  useEffect(() => { void refresh(); }, [apiUrl]);

  async function mutate(action: "initialize" | "save") {
    setBusy(true);
    setError(null);
    setNotice("");
    try {
      const result = await request(action === "initialize" ? "/initialize" : "", action === "save" ? { text: text.trim() } : {});
      setNotice(action === "initialize" ? "Project memory is ready." : result.entry
        ? `Saved to PowerContext · entry version ${result.entry.version}.`
        : "PowerContext accepted the write without an entry receipt. Refresh to inspect it.");
      if (action === "save") setText("");
      setInventory(await request());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Memory operation was not confirmed.");
    } finally { setBusy(false); }
  }

  return (
    <section className="memory-panel" aria-label="Project memory">
      <div className="section-heading">
        <div><p className="eyebrow">01 · Remember</p><h2>Project decisions</h2></div>
        <button className="secondary" disabled={disabled || busy} onClick={() => void refresh()}>Refresh memory</button>
      </div>
      <p>Save a decision here. It stays in PowerContext when you start a new conversation or restart this app.</p>
      {!inventory && <button disabled={disabled || busy} onClick={() => void mutate("initialize")}>Create project memory</button>}
      {inventory && <>
        <label htmlFor="memory-text">Decision to keep across conversations</label>
        <textarea id="memory-text" value={text} onChange={(event) => setText(event.target.value)} maxLength={2000} disabled={disabled || busy} rows={3} />
        <div className="actions">
          <button disabled={disabled || busy || !text.trim()} onClick={() => void mutate("save")}>Save decision</button>
          <button className="secondary" disabled={disabled || busy} onClick={() => setText(DEMO_MEMORY)}>Use example decision</button>
        </div>
        <div className="memory-entries">
          {inventory.entries.length === 0 && <p className="hint">No saved decisions yet. Save the example to try cross-conversation recall.</p>}
          {inventory.entries.map((entry) => <article key={entry.citation.entry_id} className="memory-entry">
            <p>{entry.text}</p>
            <details><summary>Saved evidence · version {entry.version}</summary><pre>{JSON.stringify(entry.citation, null, 2)}</pre></details>
          </article>)}
        </div>
        <details className="scope-details"><summary>Project scope</summary><code>{inventory.scope_id}</code></details>
      </>}
      {busy && <p role="status">Connecting to PowerContext…</p>}
      {notice && <p role="status" className="success-text">{notice}</p>}
      {error && <p role="alert" className="error-text">{error}</p>}
    </section>
  );
}
