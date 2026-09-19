import { useEffect, useState } from "react";
import { useI18n } from "./i18n";

type Entry = {
  text: string;
  version: number;
  citation: { entry_id: string; entry_version_id: string; memory_ref: { revision: number } };
};
type Inventory = { scope_id: string; entries: Entry[] };

export default function MemoryPanel({ apiUrl, disabled }: { apiUrl: string; disabled: boolean }) {
  const { t } = useI18n();
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [text, setText] = useState(() => t("demo.memory"));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState("");

  async function request(path = "", body?: object) {
    const response = await fetch(`${apiUrl}/custom/memory${path}`, body === undefined ? undefined : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : t("memory.requestError"));
    return data;
  }

  async function refresh() {
    setBusy(true);
    setError(null);
    try { setInventory(await request()); }
    catch (cause) { setError(cause instanceof Error ? cause.message : t("memory.loadError")); }
    finally { setBusy(false); }
  }

  useEffect(() => { void refresh(); }, [apiUrl]);

  async function mutate(action: "initialize" | "save") {
    setBusy(true);
    setError(null);
    setNotice("");
    try {
      const result = await request(action === "initialize" ? "/initialize" : "", action === "save" ? { text: text.trim() } : {});
      setNotice(action === "initialize" ? t("memory.ready") : result.entry
        ? t("memory.saved", { version: result.entry.version })
        : t("memory.savedNoEntry"));
      if (action === "save") setText("");
      setInventory(await request());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t("memory.unconfirmed"));
    } finally { setBusy(false); }
  }

  return (
    <section className="memory-panel" aria-label={t("memory.aria")}>
      <div className="section-heading">
        <div><p className="eyebrow">{t("memory.eyebrow")}</p><h2>{t("memory.heading")}</h2></div>
        <button className="secondary" disabled={disabled || busy} onClick={() => void refresh()}>{t("memory.refresh")}</button>
      </div>
      <p>{t("memory.intro")}</p>
      {!inventory && <button disabled={disabled || busy} onClick={() => void mutate("initialize")}>{t("memory.create")}</button>}
      {inventory && <>
        <label htmlFor="memory-text">{t("memory.textLabel")}</label>
        <textarea id="memory-text" value={text} onChange={(event) => setText(event.target.value)} maxLength={2000} disabled={disabled || busy} rows={3} />
        <div className="actions">
          <button disabled={disabled || busy || !text.trim()} onClick={() => void mutate("save")}>{t("memory.save")}</button>
          <button className="secondary" disabled={disabled || busy} onClick={() => setText(t("demo.memory"))}>{t("memory.useExample")}</button>
        </div>
        <div className="memory-entries">
          {inventory.entries.length === 0 && <p className="hint">{t("memory.empty")}</p>}
          {inventory.entries.map((entry) => <article key={entry.citation.entry_id} className="memory-entry">
            <p>{entry.text}</p>
            <details><summary>{t("memory.savedEvidence", { version: entry.version })}</summary><pre>{JSON.stringify(entry.citation, null, 2)}</pre></details>
          </article>)}
        </div>
        <details className="scope-details"><summary>{t("memory.scope")}</summary><code>{inventory.scope_id}</code></details>
      </>}
      {busy && <p role="status">{t("memory.connecting")}</p>}
      {notice && <p role="status" className="success-text">{notice}</p>}
      {error && <p role="alert" className="error-text">{error}</p>}
    </section>
  );
}
