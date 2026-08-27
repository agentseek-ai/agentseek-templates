import { FormEvent, Fragment, useCallback, useEffect, useState } from "react";
import { useStream, type UseStream as UseStreamResult } from "@langchain/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { PATTERNS, PatternGlyph, type PatternDefinition } from "./patterns";
import WorkflowEvidence, {
  findEvalCall,
  findEvalResult,
  isSuccessfulEvalResult,
  messageText,
  type SubagentActivity,
  type WorkflowMessage,
  type WorkflowToolCall,
} from "./WorkflowEvidence";

const DEFAULT_API_URL = "http://127.0.0.1:{{ cookiecutter.langgraph_port }}";

{% raw %}
type Message = WorkflowMessage;
type StreamState = { messages: Message[] };

type QuickJsSubagentEvent = {
  id: string;
  eval_id?: string;
  type: "subagent";
  phase: "start" | "complete" | "error";
  subagent_type?: string;
  label?: string;
  description?: string;
};

function evalCode(call: WorkflowToolCall): string {
  if (!call.args || typeof call.args !== "object" || !("code" in call.args)) return "";
  return String((call.args as { code?: unknown }).code ?? "");
}

function compactDescription(value: unknown, fallback: string): string {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!text) return fallback;
  return text.length > 86 ? text.slice(0, 83) + "…" : text;
}

function isQuickJsSubagentEvent(value: unknown): value is QuickJsSubagentEvent {
  if (!value || typeof value !== "object") return false;
  const event = value as Partial<QuickJsSubagentEvent>;
  return (
    event.type === "subagent" &&
    typeof event.id === "string" &&
    (event.phase === "start" || event.phase === "complete" || event.phase === "error")
  );
}

function PatternTopology({ pattern }: { pattern: PatternDefinition }) {
  return (
    <div className="topology" aria-label={pattern.title + " topology"}>
      {pattern.topology.map((group, index) => (
        <Fragment key={pattern.assistantId + "-" + group.join("-")}>
          <div className="topology-stack">
            {group.map((node) => (
              <span
                className={[
                  "topology-node",
                  index === 0 ? "topology-node--signal" : "",
                  index === pattern.topology.length - 1 ? "topology-node--result" : "",
                ].filter(Boolean).join(" ")}
                key={node}
              >
                {node}
              </span>
            ))}
          </div>
          {index < pattern.topology.length - 1 ? (
            <span className="topology-arrow" aria-hidden="true">→</span>
          ) : null}
        </Fragment>
      ))}
    </div>
  );
}

function RunSession({ pattern }: { pattern: PatternDefinition }) {
  const apiUrl = import.meta.env.VITE_LANGGRAPH_API_URL ?? DEFAULT_API_URL;
  const [threadId, setThreadId] = useState<string | null>(null);
  const [input, setInput] = useState(pattern.prompt);
  const [pendingInput, setPendingInput] = useState<string | null>(null);
  const [activityMap, setActivityMap] = useState<Map<string, SubagentActivity>>(() => new Map());
  const onCustomEvent = useCallback((value: unknown) => {
    if (!isQuickJsSubagentEvent(value)) return;
    setActivityMap((previous) => {
      const next = new Map(previous);
      if (value.phase === "start") {
        next.set(value.id, {
          id: value.id,
          evalId: value.eval_id,
          name: value.subagent_type ?? "specialist",
          description: compactDescription(value.label ?? value.description, "dispatch"),
          status: "running",
        });
      } else {
        const existing = next.get(value.id);
        if (existing) {
          next.set(value.id, {
            ...existing,
            evalId: value.eval_id ?? existing.evalId,
            status: value.phase === "complete" ? "complete" : "error",
          });
        }
      }
      return next;
    });
  }, []);
  const stream = useStream<StreamState>({
    apiUrl,
    assistantId: pattern.assistantId,
    threadId,
    onThreadId: setThreadId,
    onCustomEvent,
    filterSubagentMessages: true,
  } as never) as unknown as UseStreamResult<StreamState>;
  const isBusy = stream.isLoading || pendingInput !== null;

  useEffect(() => {
    if (pendingInput === null || threadId !== null || stream.isLoading) return;
    const nextInput = pendingInput;
    setPendingInput(null);
    void stream.submit(
      { messages: [{ type: "human", content: nextInput }] },
      { streamSubgraphs: true },
    );
  }, [pendingInput, stream.isLoading, stream.submit, threadId]);

  const messages = stream.messages as Message[];
  const activities = Array.from(activityMap.values());
  const evalCall = findEvalCall(messages);
  const evalResult = findEvalResult(messages, evalCall);
  const evalSucceeded = isSuccessfulEvalResult(evalResult);
  const evalFailed = Boolean(evalResult && !evalSucceeded);
  const evalResultIndex = evalResult ? messages.indexOf(evalResult) : -1;
  const finalAnswer =
    evalSucceeded && evalResultIndex >= 0
      ? [...messages]
          .reverse()
          .find(
            (message, reverseIndex) =>
              message.type === "ai" &&
              messageText(message.content).trim().length > 0 &&
              messages.length - 1 - reverseIndex > evalResultIndex,
          )
      : undefined;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const nextInput = input.trim();
    if (!nextInput || isBusy) return;
    setActivityMap(new Map());
    setPendingInput(nextInput);
    stream.switchThread(null);
  }

  return (
    <>
      <div className="scenario-grid">
        <form className="panel prompt-panel" onSubmit={onSubmit}>
          <div className="panel__head">
            <span>Scenario prompt</span>
            <span>natural goal only</span>
          </div>
          <div className="prompt-body">
            <textarea
              aria-label={pattern.title + " scenario prompt"}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              disabled={isBusy}
              rows={8}
            />
          </div>
          <div className="run-bar">
            <small>包含 workflow 关键词，不声明解释器 API、调用方式或角色名。</small>
            <button
              className="run-button"
              type="submit"
              disabled={isBusy || !input.trim()}
              aria-label={"Run " + pattern.title + " workflow"}
            >
              {isBusy ? "Workflow running" : "Run workflow"}
            </button>
          </div>
        </form>

        <section className="panel topology-panel">
          <div className="panel__head">
            <span>Pattern topology</span>
            <span>{pattern.topologyLabel}</span>
          </div>
          <div className="topology-body">
            <PatternTopology pattern={pattern} />
            <p><strong>完成条件</strong>{pattern.completion}</p>
          </div>
        </section>
      </div>

      <WorkflowEvidence messages={messages} activities={activities} isLoading={isBusy} />

      <section className="panel result-panel" aria-label="Workflow result">
        <div className="panel__head">
          <span>Workflow result</span>
          <span>
            {isBusy
              ? "coordinator working"
              : finalAnswer
                ? "published"
                : evalFailed
                  ? "failed"
                  : threadId
                    ? "thread ready"
                    : "waiting"}
          </span>
        </div>
        {finalAnswer ? (
          <article className="report-card">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {messageText(finalAnswer.content)}
            </ReactMarkdown>
          </article>
        ) : (
          <div className="result-empty">
            <span>06</span>
            <p>运行当前 Pattern 后，coordinator 的真实结果会显示在这里。</p>
          </div>
        )}
        {stream.error || evalFailed ? (
          <div className="run-error" role="alert">
            <strong>当前 Pattern 未完成。</strong>
            <span>
              {stream.error
                ? String(stream.error instanceof Error ? stream.error.message : stream.error)
                : "解释器返回错误；可展开运行证据查看详情。"}
            </span>
            <small>检查模型凭证和后端日志后，可在同一场景重新运行。</small>
          </div>
        ) : null}
      </section>

      <details className="evidence">
        <summary>
          <strong>运行证据 · QuickJS 与 interpreter result</strong>
          <span>{evalCall ? "captured" : "waiting"}</span>
        </summary>
        {evalCall ? (
          <div className="evidence-grid">
            <section>
              <span>Generated QuickJS</span>
              <pre>{evalCode(evalCall) || JSON.stringify(evalCall.args, null, 2)}</pre>
            </section>
            <section>
              <span>Interpreter result</span>
              <pre>{evalResult ? messageText(evalResult.content) : "Waiting for interpreter result…"}</pre>
            </section>
          </div>
        ) : (
          <p>模型尚未调用解释器。这里不会因为提示词包含 workflow 就提前显示运行成功。</p>
        )}
      </details>
    </>
  );
}

export default function App() {
  const [selectedId, setSelectedId] = useState(PATTERNS[0].assistantId);
  const selected = PATTERNS.find((pattern) => pattern.assistantId === selectedId) ?? PATTERNS[0];

  return (
    <div className="shell">
      <div className="topbar">
        <div className="topbar__brand">
          <span className="topbar__pulse" aria-hidden="true" />
          <span>Dynamic Subagents / Pattern Lab</span>
        </div>
        <span className="runtime-badge">6 independent assistants · beta</span>
      </div>

      <header className="hero">
        <div>
          <span className="eyebrow">Six official patterns · one visible trigger</span>
          <h1>一个关键词，<br /><span>六种编排形状。</span></h1>
          <p className="hero__lead">
            选择适合任务的场景，观察 <strong>workflow</strong> 如何触发解释器，让模型从代码中动态分派
            subagents、管理中间结果并判断何时结束。
          </p>
        </div>
        <aside className="trigger-console" aria-label="Workflow trigger explanation">
          <div className="trigger-console__head"><span>Trigger monitor</span><span>evidence based</span></div>
          <div className="trigger-console__body">
            <code>Run a <span>workflow</span> to…</code>
            <p>页面只在观察到真实解释器调用后标记 Dynamic triggered，不会仅凭提示词宣称成功。</p>
          </div>
        </aside>
      </header>

      <main className="workspace">
        <aside className="pattern-chooser">
          <div className="section-heading"><h2>选择验证场景</h2><span>6 patterns</span></div>
          <div className="pattern-list">
            {PATTERNS.map((pattern) => {
              const selectedCard = pattern.assistantId === selected.assistantId;
              return (
                <button
                  className={"pattern-card " + (selectedCard ? "pattern-card--selected" : "")}
                  type="button"
                  key={pattern.assistantId}
                  onClick={() => setSelectedId(pattern.assistantId)}
                  aria-pressed={selectedCard}
                  aria-label={"选择 " + pattern.title + " Pattern"}
                >
                  <span className="pattern-card__map"><PatternGlyph kind={pattern.kind} /></span>
                  <span className="pattern-card__copy"><strong>{pattern.title}</strong><small>{pattern.short}</small></span>
                  <span className="pattern-card__arrow" aria-hidden="true">→</span>
                </button>
              );
            })}
          </div>
        </aside>

        <section className="pattern-stage">
          <header className="stage-title">
            <div>
              <span className="eyebrow">{selected.family}</span>
              <h2>{selected.title}</h2>
              <p>{selected.description}</p>
            </div>
            <span className="official-tag">Official pattern</span>
          </header>
          <RunSession key={selected.assistantId} pattern={selected} />
        </section>
      </main>
    </div>
  );
}
{% endraw %}
