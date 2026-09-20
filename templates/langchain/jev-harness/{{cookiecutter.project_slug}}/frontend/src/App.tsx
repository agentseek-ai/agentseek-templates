import { FormEvent, useEffect, useState } from "react";
import { useStream } from "@langchain/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Translate, TranslationKey, useLanguage } from "./i18n";

type Audit = { decision: "allowed" | "blocked"; executed: boolean; risk_probability: number | null };
type Message = { id?: string; type: string; content: unknown; name?: string; tool_call_id?: string;
  artifact?: { auto_mode?: Audit } };
type Route = { choice: string; model: string; confidence: number; probabilities: Record<string, number> };
type HarnessState = { messages: Message[]; route_report?: Route };

const scenarios: [TranslationKey, TranslationKey][] = [
  ["statusScenario", "statusPrompt"],
  ["recoveryScenario", "recoveryPrompt"],
  ["riskyScenario", "riskyPrompt"],
  ["untrustedScenario", "untrustedPrompt"],
];
const percent = (value: number) => `${Math.round(value * 100)}%`;

function messageText(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) return content.map(part => typeof part === "string" ? part : part?.text ?? "").join("");
  return "";
}

function NewTaskButton({ onClick, disabled, t }: { onClick: () => void; disabled: boolean; t: Translate }) {
  return <button type="button" className="new-run" disabled={disabled} onClick={onClick}>
    <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
    {t("newRun")}
  </button>;
}

function HarnessRun({ onLoadingChange, onNewRun, focusTask, t }: {
  onLoadingChange: (loading: boolean) => void; onNewRun: () => void; focusTask: boolean; t: Translate;
}) {
  const [scenario, setScenario] = useState<TranslationKey | null>("statusPrompt");
  const [customInput, setCustomInput] = useState("");
  const input = scenario === null ? customInput : t(scenario);
  const [submitted, setSubmitted] = useState(false);
  const stream = useStream<HarnessState>({
    apiUrl: import.meta.env.VITE_LANGGRAPH_API_URL ?? "http://127.0.0.1:{{ cookiecutter.langgraph_port }}",
    assistantId: "agent",
  });
  const route = stream.values.route_report;
  useEffect(() => onLoadingChange(stream.isLoading), [stream.isLoading, onLoadingChange]);
  const messages = stream.messages as Message[];
  const tools = messages.filter(message => message.type === "tool");
  const answers = messages.filter(message => message.type === "ai" && messageText(message.content));

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!input.trim() || stream.isLoading || submitted) return;
    setCustomInput(input);
    setScenario(null);
    setSubmitted(true);
    void stream.submit({ messages: [{ type: "human", content: input.trim() }] }, { config: { recursion_limit: 24 } });
  }

  return <div className="workspace">
    <section className="request-panel" aria-labelledby="request-heading">
      <h2 id="request-heading">{t("taskHeading")}</h2>
      <p className="muted">{t("taskIntro")}</p>
      <div className="scenarios">{scenarios.map(([title, prompt]) =>
        <button key={title} type="button" onClick={() => setScenario(prompt)} disabled={submitted}>{t(title)}</button>)}</div>
      <form onSubmit={submit}>
        <label htmlFor="task">{t("request")}</label>
        <textarea id="task" value={input} onChange={event => { setScenario(null); setCustomInput(event.target.value); }} disabled={submitted} maxLength={4000} rows={7} autoFocus={focusTask} />
        {submitted && !stream.isLoading ? <div className="next-task">
          <NewTaskButton onClick={onNewRun} disabled={false} t={t} />
          <p className="muted small">{t("newRunHelp")}</p>
        </div> : <button className="run-button" disabled={stream.isLoading || !input.trim()}>
          {stream.isLoading ? t("runningButton") : t("run")}
        </button>}
      </form>
      <p className="setup">{t("setup")}</p>
      <details className="small"><summary>{t("providerHelp")}</summary><p className="muted">{t("providerSettings")}</p></details>
      <p className="muted small">{t("dataBoundary")}</p>
    </section>

    <section className="evidence-panel" aria-label={t("decisions")}>
      <div className="route-section">
        <div className="section-heading"><h2>{t("routing")}</h2><span className="badge">{t("once")}</span></div>
        {route ? <>
          <div className="chosen-model"><span>{route.choice === "fast" ? t("fast") : route.choice === "powerful" ? t("powerful") : route.choice}</span><strong>{route.model}</strong></div>
          <div className="probabilities">{Object.entries(route.probabilities).map(([label, probability]) =>
            <div key={label}><span>{label === "fast" ? t("fast") : label === "powerful" ? t("powerful") : label}</span><meter min={0} max={1} value={probability} aria-label={`${label} ${t("probability")}`} /><b>{percent(probability)}</b></div>)}</div>
          <p className="muted">{t("confidence")} <strong>{percent(route.confidence)}</strong>. {t("confidenceHelp")}</p>
        </> : <p className="empty">{t("routeEmpty")}</p>}
      </div>

      <div className="tools-section">
        <div className="section-heading"><h2>{t("autoMode")}</h2><span className="badge">{t("eachTool")}</span></div>
        <p className="muted">{t("gatePolicy")}</p>
        {tools.length === 0 && <p className="empty">{t("toolEmpty")}</p>}
        <ol className="tool-list">{tools.map((message, index) => {
          const audit = message.artifact?.auto_mode;
          return <li key={message.id ?? message.tool_call_id ?? index} className={audit?.decision ?? "unknown"}>
            <div className="tool-heading"><code>{message.name ?? t("tool")}</code><strong>{audit ? audit.decision === "blocked" ? t("blocked") : t("allowed") : t("result")}</strong></div>
            {audit && <p>{audit.executed ? t("toolRan") : t("toolDidNotRun")} {audit.risk_probability === null ? t("scoreUnavailable") : `${t("riskProbability")} ${percent(audit.risk_probability)}.`}</p>}
            <details><summary>{t("inspectResult")}</summary><pre>{messageText(message.content)}</pre></details>
          </li>;
        })}</ol>
      </div>

      <div className="answer-section" aria-live="polite">
        <h2>{t("response")}</h2>
        {answers.map((message, index) => <div key={message.id ?? index} className="answer"><ReactMarkdown remarkPlugins={[remarkGfm]}>{messageText(message.content)}</ReactMarkdown></div>)}
        {!answers.length && <p className="empty">{t("responseEmpty")}</p>}
        {stream.isLoading && <p className="running" role="status">{t("running")}</p>}
        {stream.error ? <p className="error" role="alert">{String(stream.error)}. {t("failureHelp")}</p> : null}
      </div>
    </section>
  </div>;
}

export default function App() {
  const [runId, setRunId] = useState(0);
  const { language, setLanguage, t } = useLanguage();
  const [isRunning, setIsRunning] = useState(false);
  const startNewRun = () => setRunId(id => id + 1);
  return <main>
    <header className="masthead"><div><p className="brand">LangChain / Jev</p><h1>{t("title")}</h1><p>{t("subtitle")}</p></div>
      <div className="header-actions"><div className="language-switch" role="group" aria-label={t("language")}><button type="button" aria-pressed={language === "zh"} onClick={() => setLanguage("zh")}>中文</button><button type="button" aria-pressed={language === "en"} onClick={() => setLanguage("en")}>English</button></div>
        <div className="new-task-action"><NewTaskButton onClick={startNewRun} disabled={isRunning} t={t} /><p>{t(isRunning ? "newRunWaiting" : "newRunHelp")}</p></div>
      </div></header>
    <section className="harness-guide" aria-labelledby="guide-heading">
      <div className="guide-heading"><h2 id="guide-heading">{t("guideHeading")}</h2><p>{t("guideIntro")}</p></div>
      <ol className="guide-steps">
        {([["routeStep", "routeExplanation"], ["gateStep", "gateExplanation"], ["answerStep", "answerExplanation"]] as [TranslationKey, TranslationKey][]).map(([heading, description], index) =>
          <li key={heading}><span className="step-number" aria-hidden="true">{index + 1}</span><div><h3>{t(heading)}</h3><p>{t(description)}</p></div></li>)}
      </ol>
    </section>
    <HarnessRun key={runId} onLoadingChange={setIsRunning} onNewRun={startNewRun} focusTask={runId > 0} t={t} />
    <footer>{t("footer")} · <a href="https://www.langchain.com/blog/building-a-harness-with-jev">{t("source")}</a></footer>
  </main>;
}
