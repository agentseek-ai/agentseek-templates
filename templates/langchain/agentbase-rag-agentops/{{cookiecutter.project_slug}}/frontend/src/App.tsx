import { FormEvent, useMemo, useState } from "react";
import { useStream } from "@langchain/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { parseEvidence, type Evidence } from "./evidence";

type Message = { id?: string; type: string; content: unknown; tool_calls?: { id?: string; name?: string; args?: unknown }[]; tool_call_id?: string; artifact?: unknown };
type Card = { id: string; name: string; args: unknown; result: string | null; evidence: Evidence[]; pending: boolean };

function text(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) return content.map((part) => typeof part === "string" ? part : typeof part === "object" && part !== null && "text" in part ? String((part as { text?: unknown }).text ?? "") : "").join("");
  return "";
}


function EvidenceCard({ card }: { card: Card }) {
  return <details className="evidence-card" open={card.pending}><summary><strong>{card.name}</strong><span>{card.pending ? "searching…" : `${card.evidence.length} sources`}</span></summary><div className="card-body"><div className="label">query</div><pre>{JSON.stringify(card.args, null, 2)}</pre>{card.evidence.map((item, index) => <article className="evidence" key={item.chunk_id ?? index}><header><strong>{String(item.source?.name ?? item.source_id ?? "AgentBase document")}</strong><span>score {item.score?.toFixed?.(3) ?? "—"}</span></header><p>{item.content}</p><small>{item.chunk_id ?? ""}{item.index_source ? ` · ${item.index_source}` : ""}{item.locator && Object.keys(item.locator).length ? ` · ${JSON.stringify(item.locator)}` : ""}</small></article>)}</div></details>;
}

function rows(messages: Message[]) {
  const cards = new Map<string, Card>();
  const output: (JSX.Element | null)[] = [];
  messages.forEach((message, index) => {
    if (message.type === "human") output.push(<article className="message human" key={message.id ?? `h-${index}`}>{text(message.content)}</article>);
    if (message.type === "ai") {
      const body = text(message.content).trim();
      if (body) output.push(<article className="message ai" key={message.id ?? `a-${index}`}><ReactMarkdown remarkPlugins={[remarkGfm]}>{body}</ReactMarkdown></article>);
      message.tool_calls?.forEach((call, callIndex) => { const id = call.id ?? `${index}-${callIndex}`; const card = { id, name: call.name ?? "search_knowledge_base", args: call.args ?? {}, result: null, evidence: [], pending: true }; cards.set(id, card); output.push(<EvidenceCard key={`c-${id}`} card={card} />); });
    }
    if (message.type === "tool" && message.tool_call_id) { const card = cards.get(message.tool_call_id); if (card) { card.result = text(message.content); card.evidence = parseEvidence(card.result, message.artifact); card.pending = false; } }
  });
  return output;
}

export default function App() {
  const apiUrl = import.meta.env.VITE_LANGGRAPH_API_URL ?? `http://${window.location.hostname || "127.0.0.1"}:2024`;
  const [threadId, setThreadId] = useState<string | null>(null);
  const stream = useStream<{ messages: Message[] }>({
    apiUrl,
    assistantId: "agentbase_rag",
    threadId,
    onThreadId: setThreadId,
  });
  const [input, setInput] = useState("");
  const sessionId = useMemo(() => crypto.randomUUID(), []);
  function submit(event: FormEvent) { event.preventDefault(); const question = input.trim(); if (!question || stream.isLoading) return; setInput(""); const userId = import.meta.env.VITE_AGENTBASE_USER_ID || "demo-user"; stream.submit({ messages: [{ type: "human", content: question }] }, { config: { metadata: { session_id: sessionId, user_id: userId }, tags: ["agentbase", "rag", "browser"] } } as never); }
  return <main><header><p>AGENTBASE · AGENTOPS</p><h1>Observable RAG workspace</h1><span>Session {sessionId.slice(0, 8)} · retrieval evidence is shown below each search</span></header><section className="conversation">{rows(stream.messages as Message[])}{stream.isLoading && <p className="loading">Agent is retrieving context and synthesizing an answer…</p>}{stream.error ? <p className="error">{String(stream.error)}</p> : null}</section><form onSubmit={submit}><input value={input} onChange={(event) => setInput(event.target.value)} placeholder="Ask your AgentBase knowledge base…" disabled={stream.isLoading} /><button disabled={stream.isLoading || !input.trim()}>Send</button></form></main>;
}
