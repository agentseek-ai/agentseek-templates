import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Translate } from "./i18n";
import { messageText, percent, providerName } from "./harness";
import { HarnessRun } from "./useHarnessRun";

export function RunEvidence({ run, t, label, side, modelLabel }: {
  run: HarnessRun; t: Translate; label?: string; side?: string; modelLabel?: string;
}) {
  const { route, tools, answers } = run;
  return (
    <section className="evidence-panel" aria-label={label ?? t("decisions")}>
      {label && <header className="contender-heading"><div><span>{side}</span><h2>{modelLabel}</h2></div><div className="run-status"><strong>{t(run.error ? "runFailed" : run.isLoading ? "runningButton" : run.elapsed !== null ? "runComplete" : "ready")}</strong>{run.elapsed !== null && <span>{t("totalTime")}: {(run.elapsed / 1000).toFixed(1)} s</span>}</div></header>}
      {run.error ? <p className="error" role="alert">{String(run.error)}. {t("failureHelp")}</p> : null}
      <div className="route-section">
        <div className="section-heading"><h2>{t("routing")}</h2><span className="badge">{t("once")}</span></div>
        <p className="decision-attribution"><span>{t("decidedBy")}</span><strong>{route?.decision_model ? providerName(route.decision_model) : route ? t("legacyJev") : t("awaitingRoute")}</strong></p>
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
          const rawAnswer = audit?.raw_answer ?? audit?.jev_answer;
          return <li key={message.id ?? message.tool_call_id ?? index} className={audit?.decision ?? "unknown"}>
            <div className="tool-heading"><code>{message.name ?? t("tool")}</code><strong>{audit ? audit.decision === "blocked" ? t("blocked") : t("allowed") : t("result")}</strong></div>
            {audit && <>
              <p className="tool-provider">{t("decidedBy")}: <strong>{audit.decision_model ? providerName(audit.decision_model) : t("legacyJev")}</strong></p>
              <div className="audit-source"><span>{t(audit.proposal_source === "preset" ? "fixedProposal" : "modelProposal")}</span><span>{t(audit.execution_status === "failed" ? "toolFailed" : audit.executed ? "toolRan" : "toolDidNotRun")}</span></div>
              {audit.arguments && <pre className="tool-arguments" aria-label={t("toolArguments")}>{JSON.stringify(audit.arguments, null, 2)}</pre>}
              {typeof audit.risk_probability === "number" ? <div className="risk-score"><span>{t("riskProbability")}</span><meter min={0} max={1} value={audit.risk_probability} aria-label={t("riskProbability")} /><strong>{percent(audit.risk_probability)}</strong></div> : <p>{t("scoreUnavailable")}</p>}
            </>}
            <details className="decision-details"><summary>{t("inspectResult")}</summary>
              {audit && <div className="decision-record"><h3>{t("rawAnswer")}</h3><p>{t("rawAnswerHelp")}</p>
                {rawAnswer ? <pre aria-label={t("rawAnswer")}>{JSON.stringify(rawAnswer, null, 2)}</pre> : <p>{t("rawAnswerUnavailable")}</p>}
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
        <p className="score-note">{t("responseNote")}</p>
        {answers.map((message, index) => <div key={message.id ?? index} className="answer"><ReactMarkdown remarkPlugins={[remarkGfm]}>{messageText(message.content)}</ReactMarkdown></div>)}
        {!answers.length && <p className="empty">{t("responseEmpty")}</p>}
        {run.isLoading && <p className="running" role="status">{t("running")}</p>}
      </div>
    </section>
  );
}
