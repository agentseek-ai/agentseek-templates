import { FormEvent, useEffect, useRef, useState } from "react";
import { Translate, TranslationKey, useLanguage } from "./i18n";
import { RunEvidence } from "./RunEvidence";
import { HarnessRun, useHarnessRun } from "./useHarnessRun";

const decisionModels = [{ id: "semif", label: "SemIf" }, { id: "kev-4b", label: "Kev-4B" }, { id: "diffusiongemma", label: "DiffusionGemma" }, { id: "jev", label: "Jev" }];
const modelLabel = (id: string) => decisionModels.find(model => model.id === id)?.label ?? id;
type Mode = "single" | "arena";
const experiments: { id: string; title: TranslationKey; prompt: TranslationKey; proposal: string }[] = [
  { id: "restart-approved", title: "restartApproved", prompt: "restartApprovedPrompt", proposal: 'restart_service(environment="staging")' },
  { id: "restart-readonly", title: "restartReadonly", prompt: "restartReadonlyPrompt", proposal: 'restart_service(environment="staging")' },
  { id: "cleanup-expired", title: "cleanupExpired", prompt: "cleanupExpiredPrompt", proposal: 'delete_backups(environment="staging", scope="expired")' },
  { id: "delete-production", title: "deleteProduction", prompt: "deleteProductionPrompt", proposal: 'delete_backups(environment="production", scope="all")' },
  { id: "injected-note", title: "injectedNote", prompt: "injectedNotePrompt", proposal: 'read_incident_note() → restart_service(environment="staging")' },
];

function NewTaskButton({ onClick, disabled, t }: { onClick: () => void; disabled: boolean; t: Translate }) {
  return <button type="button" className="new-run" disabled={disabled} onClick={onClick}>
    <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
    {t("newRun")}
  </button>;
}

function ModelPicker({ id, label, value, onChange, disabled, t }: {
  id: string; label: string; value: string; onChange: (value: string) => void; disabled: boolean; t: Translate;
}) {
  return <div className="model-picker">
    <label htmlFor={id}>{label}</label>
    <select id={id} value={value} onChange={event => onChange(event.target.value)} disabled={disabled} aria-describedby={`${id}-help`}>
      <optgroup label="SiliconFlow"><option value="semif">SemIf · {t("defaultModel")}</option><option value="kev-4b">Kev-4B</option><option value="diffusiongemma">DiffusionGemma</option></optgroup>
      <optgroup label="TypeSafe"><option value="jev">Jev · {t("officialModel")}</option></optgroup>
    </select>
    <p id={`${id}-help`} className="decision-key-help">{t(value === "jev" ? "jevKeyHelp" : "siliconflowKeyHelp")}</p>
  </div>;
}

function Comparison({ left, right, t, submitted }: { left: HarnessRun; right: HarnessRun; t: Translate; submitted: boolean }) {
  const finished = submitted && !left.isLoading && !right.isLoading && left.elapsed !== null && right.elapsed !== null;
  // Missing audits are unknown, never interpreted as an allowed or matching call.
  const comparable = left.tools.length > 0 && left.tools.length === right.tools.length && left.tools.every((tool, i) => {
    const a = tool.artifact?.auto_mode, b = right.tools[i].artifact?.auto_mode;
    return a && b && tool.name === right.tools[i].name && JSON.stringify(a.arguments) === JSON.stringify(b.arguments);
  });
  const same = comparable && left.tools.every((tool, i) => tool.artifact!.auto_mode!.decision === right.tools[i].artifact!.auto_mode!.decision);
  return <section className="comparison-summary" aria-label={t("comparisonSummary")} aria-live="polite">
    <div><h2>{t("arenaTitle")}</h2><p>{t("arenaHelp")}</p></div>
    <div className={`comparison-verdict ${finished && comparable && !same ? "different" : ""}`}>
      <strong>{t(!submitted ? "comparisonReady" : !finished ? "comparisonRunning" : left.error || right.error ? "comparisonFailed" : !comparable ? "comparisonUnknown" : same ? "decisionsAgree" : "decisionsDiffer")}</strong>
      {finished && left.route && right.route && <span>{t(left.route.choice === right.route.choice ? "routesAgree" : "routesDiffer")}</span>}
    </div>
    <p className="comparison-footnote">{t("comparisonCaveat")}</p>
  </section>;
}

function HarnessLab({ mode, onModeChange, models, onModelChange, onLoadingChange, onNewRun, focusTask, t }: {
  mode: Mode; onModeChange: (mode: Mode) => void; models: [string, string]; onModelChange: (side: number, value: string) => void;
  onLoadingChange: (loading: boolean) => void; onNewRun: () => void; focusTask: boolean; t: Translate;
}) {
  const [experiment, setExperiment] = useState(experiments[0]);
  const [scenario, setScenario] = useState<TranslationKey | null>(experiments[0].prompt);
  const [customInput, setCustomInput] = useState("");
  const input = scenario === null ? customInput : t(scenario);
  const [submitted, setSubmitted] = useState(false);
  const resultsRef = useRef<HTMLDivElement>(null);
  const left = useHarnessRun(), right = useHarnessRun();
  const arena = mode === "arena";
  const isLoading = left.isLoading || (arena && right.isLoading);
  const duplicate = arena && models[0] === models[1];
  useEffect(() => onLoadingChange(isLoading), [isLoading, onLoadingChange]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!input.trim() || isLoading || submitted || duplicate) return;
    const content = input.trim();
    setCustomInput(input);
    setScenario(null);
    setSubmitted(true);
    void left.start(content, experiment.id, models[0]);
    if (arena) {
      void right.start(content, experiment.id, models[1]);
      resultsRef.current?.scrollIntoView?.({ block: "start", behavior: "auto" });
    }
  }

  return <>
    <div className="mode-switch" role="group" aria-label={t("experimentMode")}>
      <button type="button" aria-pressed={!arena} onClick={() => onModeChange("single")} disabled={submitted || isLoading}>{t("singleMode")}</button>
      <button type="button" aria-pressed={arena} onClick={() => onModeChange("arena")} disabled={submitted || isLoading}>{t("arenaMode")}</button>
    </div>
    <div className={`workspace${arena ? " arena-workspace" : ""}`}>
      <section className="request-panel" aria-labelledby="request-heading">
        <div className={`decision-picker${arena ? " arena-pickers" : ""}`}>
          <ModelPicker id="decision-model-a" label={t(arena ? "modelA" : "decisionModel")} value={models[0]} onChange={value => onModelChange(0, value)} disabled={submitted || isLoading} t={t} />
          {arena && <ModelPicker id="decision-model-b" label={t("modelB")} value={models[1]} onChange={value => onModelChange(1, value)} disabled={submitted || isLoading} t={t} />}
          <p className="picker-help">{t(arena ? "arenaModelHelp" : "decisionModelHelp")}</p>
          {duplicate && <p className="picker-help error" role="alert">{t("differentModels")}</p>}
        </div>
        <div className="experiment-context">
          <h2 id="request-heading">{t(arena ? "sharedContext" : "experimentHeading")}</h2>
          <p className="muted">{t(arena ? "sharedContextHelp" : "experimentHelp")}</p>
          <div className="scenarios">{experiments.map(item => <button key={item.id} type="button" aria-pressed={experiment.id === item.id} onClick={() => { setExperiment(item); setScenario(item.prompt); }} disabled={submitted || isLoading}>{t(item.title)}</button>)}</div>
          <div className="proposal-preview"><span>{t("proposedAction")}</span><code>{experiment.proposal}</code><p>{t("editContext")}</p></div>
        </div>
        <form className="request-form" onSubmit={submit}>
          <label htmlFor="task">{t("request")}</label>
          <textarea id="task" value={input} onChange={event => { setScenario(null); setCustomInput(event.target.value); }} disabled={submitted || isLoading} maxLength={4000} rows={7} autoFocus={focusTask} />
          {submitted && !isLoading ? <div className="next-task"><NewTaskButton onClick={onNewRun} disabled={false} t={t} /><p className="muted small">{t("newRunHelp")}</p></div> : <button className="run-button" disabled={isLoading || !input.trim() || duplicate}>{isLoading ? t("runningButton") : t(arena ? "startComparison" : "run")}</button>}
          {arena && <p className="score-note">{t("arenaRequests")}</p>}
        </form>
        <div className="setup-notes"><p className="setup">{t("setup")}</p><details className="small"><summary>{t("providerHelp")}</summary><p className="muted">{t("providerSettings")}</p></details><p className="muted small">{t("dataBoundary")}</p></div>
      </section>
      {arena ? <div className="arena-results" ref={resultsRef}>
        <Comparison left={left} right={right} t={t} submitted={submitted} />
        <div className="arena-columns">
          <RunEvidence run={left} t={t} side="A" modelLabel={modelLabel(models[0])} label={`${t("modelA")}: ${modelLabel(models[0])}`} />
          <RunEvidence run={right} t={t} side="B" modelLabel={modelLabel(models[1])} label={`${t("modelB")}: ${modelLabel(models[1])}`} />
        </div>
      </div> : <RunEvidence run={left} t={t} />}
    </div>
  </>;
}

export default function App() {
  const [models, setModels] = useState<[string, string]>(["semif", "kev-4b"]);
  const [mode, setMode] = useState<Mode>("single");
  const [runId, setRunId] = useState(0);
  const { language, setLanguage, t } = useLanguage();
  const [isRunning, setIsRunning] = useState(false);
  const startNewRun = () => setRunId(id => id + 1);
  return <main>
    <header className="masthead"><div><p className="brand">LangChain / System One</p><h1>{t("title")}</h1><p>{t("subtitle")}</p></div>
      <div className="header-actions"><div className="language-switch" role="group" aria-label={t("language")}><button type="button" aria-pressed={language === "zh"} onClick={() => setLanguage("zh")}>中文</button><button type="button" aria-pressed={language === "en"} onClick={() => setLanguage("en")}>English</button></div><div className="new-task-action"><NewTaskButton onClick={startNewRun} disabled={isRunning} t={t} /><p>{t(isRunning ? "newRunWaiting" : "newRunHelp")}</p></div></div>
    </header>
    <section className="harness-guide" aria-labelledby="guide-heading">
      <div className="guide-heading"><h2 id="guide-heading">{t("guideHeading")}</h2><p>{t("guideIntro")}</p></div>
      <ol className="guide-steps">{([["routeStep", "routeExplanation"], ["gateStep", "gateExplanation"], ["answerStep", "answerExplanation"]] as [TranslationKey, TranslationKey][]).map(([heading, description], index) => <li key={heading}><span className="step-number" aria-hidden="true">{index + 1}</span><div><h3>{t(heading)}</h3><p>{t(description)}</p></div></li>)}</ol>
    </section>
    <HarnessLab key={runId} mode={mode} onModeChange={setMode} models={models} onModelChange={(side, value) => setModels(current => side === 0 ? [value, current[1]] : [current[0], value])} onLoadingChange={setIsRunning} onNewRun={startNewRun} focusTask={runId > 0} t={t} />
    <footer>{t("footer")} · <a href="https://www.langchain.com/blog/building-a-harness-with-jev">{t("source")}</a></footer>
  </main>;
}
