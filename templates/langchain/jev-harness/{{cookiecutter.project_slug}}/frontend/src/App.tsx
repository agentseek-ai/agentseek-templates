import { FormEvent, useEffect, useState } from "react";
import { useStream } from "@langchain/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Translate, TranslationKey, useLanguage } from "./i18n";

type Audit = { decision: "allowed" | "blocked"; executed: boolean; risk_probability: number | null;
  jev_answer?: { type: "noul"; noul: number };
  execution_status?: "completed" | "failed" | "blocked";
  confidence?: null; arguments?: Record<string, unknown>; proposal_source?: "preset" | "agent" };
type Message = { id?: string; type: string; content: unknown; name?: string; tool_call_id?: string;
  artifact?: { auto_mode?: Audit } };
type Route = { choice: string; model: string; confidence: number; probabilities: Record<string, number>; models?: Record<string, string> };
type HarnessState = { messages: Message[]; route_report?: Route; proposal_id?: string | null };
const experiments: { id: string; title: TranslationKey; prompt: TranslationKey; proposal: string }[] = [
  { id: "restart-approved", title: "restartApproved", prompt: "restartApprovedPrompt", proposal: 'restart_service(environment="staging")' },
  { id: "restart-readonly", title: "restartReadonly", prompt: "restartReadonlyPrompt", proposal: 'restart_service(environment="staging")' },
  { id: "cleanup-expired", title: "cleanupExpired", prompt: "cleanupExpiredPrompt", proposal: 'delete_backups(environment="staging", scope="expired")' },
  { id: "delete-production", title: "deleteProduction", prompt: "deleteProductionPrompt", proposal: 'delete_backups(environment="production", scope="all")' },
  { id: "injected-note", title: "injectedNote", prompt: "injectedNotePrompt", proposal: 'read_incident_note() → restart_service(environment="staging")' },
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
  const [experiment, setExperiment] = useState(experiments[0]);
  const [scenario, setScenario] = useState<TranslationKey | null>(experiments[0].prompt);
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
    void stream.submit({ messages: [{ type: "human", content: input.trim() }], proposal_id: experiment.id }, { config: { recursion_limit: 24 } });
  }

  return <div className="workspace">
    <section className="request-panel" aria-labelledby="request-heading">
      <h2 id="request-heading">{t("experimentHeading")}</h2>
      <p className="muted">{t("experimentHelp")}</p>
      <div className="scenarios">{experiments.map(item =>
        <button key={item.id} type="button" aria-pressed={experiment.id === item.id} onClick={() => { setExperiment(item); setScenario(item.prompt); }} disabled={submitted}>{t(item.title)}</button>)}</div>
      <div className="proposal-preview"><span>{t("proposedAction")}</span><code>{experiment.proposal}</code><p>{t("editContext")}</p></div>
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
        <div className="route-models">{(["fast", "powerful"] as const).map(key => {
          const probability = route?.probabilities[key];
          const selected = route?.choice === key;
          const model = route?.models?.[key] ?? (selected ? route.model : null);
          return <article key={key} className={`route-model${selected ? " selected" : ""}`} aria-label={t(key)}>
            <div className="model-heading"><h3>{t(key)}</h3><span className="model-status">{selected ? t("selectedModel") : route ? t("notSelectedModel") : t("awaitingRoute")}</span></div>
            <p className="model-id">{model ?? t("configuredModel")}</p>
            <div className="model-probability"><span>{t("routeProbability")}</span><strong>{typeof probability === "number" ? percent(probability) : "—"}</strong></div>
            {typeof probability === "number" && <meter min={0} max={1} value={probability} aria-label={`${key} ${t("probability")}`} />}
          </article>;
        })}</div>
        {route ? <p className="route-confidence muted">{t("confidence")} <strong>{percent(route.confidence)}</strong>. {t("confidenceHelp")}</p> : <p className="empty">{t("routeEmpty")}</p>}
      </div>

      <div className="tools-section">
        <div className="section-heading"><h2>{t("autoMode")}</h2><span className="badge">{t("eachTool")}</span></div>
        <p className="muted">{t("gatePolicy")}</p>
        <details className="gate-explanation"><summary>{t("policyHeading")}</summary><p>{t("contextPolicy")}</p></details>
        <p className="score-note">{t("noulConfidence")}</p>
        {tools.length === 0 && <p className="empty">{t("toolEmpty")}</p>}
        <ol className="tool-list">{tools.map((message, index) => {
          const audit = message.artifact?.auto_mode;
          return <li key={message.id ?? message.tool_call_id ?? index} className={audit?.decision ?? "unknown"}>
            <div className="tool-heading"><code>{message.name ?? t("tool")}</code><strong>{audit ? audit.decision === "blocked" ? t("blocked") : t("allowed") : t("result")}</strong></div>
            {audit && <>
              <div className="audit-source"><span>{t(audit.proposal_source === "preset" ? "fixedProposal" : "modelProposal")}</span><span>{t(audit.execution_status === "failed" ? "toolFailed" : audit.executed ? "toolRan" : "toolDidNotRun")}</span></div>
              {audit.arguments && <pre className="tool-arguments" aria-label={t("toolArguments")}>{JSON.stringify(audit.arguments, null, 2)}</pre>}
              {typeof audit.risk_probability === "number" ? <div className="risk-score"><span>{t("riskProbability")}</span><meter min={0} max={1} value={audit.risk_probability} aria-label={t("riskProbability")} /><strong>{percent(audit.risk_probability)}</strong></div> : <p>{t("scoreUnavailable")}</p>}
            </>}
            <details className="decision-details"><summary>{t("inspectResult")}</summary>
              {audit && <div className="decision-record"><h3>{t("jevAnswer")}</h3><p>{t("jevAnswerHelp")}</p>
                {audit.jev_answer ? <pre aria-label={t("jevAnswer")}>{JSON.stringify(audit.jev_answer, null, 2)}</pre> : <p>{t("rawAnswerUnavailable")}</p>}
              </div>}
              <h3>{t(audit?.decision === "blocked" ? "blockMessage" : "toolOutput")}</h3>
              <p>{t(audit?.decision === "blocked" ? "blockMessageHelp" : "toolOutputHelp")}</p>
              <pre aria-label={t(audit?.decision === "blocked" ? "blockMessage" : "toolOutput")}>{messageText(message.content)}</pre>
            </details>
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
