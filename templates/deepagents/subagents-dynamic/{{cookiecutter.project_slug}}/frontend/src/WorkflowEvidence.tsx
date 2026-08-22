{% raw %}
export type WorkflowToolCall = {
  id?: string;
  name?: string;
  args?: unknown;
};

export type WorkflowMessage = {
  id?: string;
  type: string;
  content: unknown;
  tool_calls?: WorkflowToolCall[];
  tool_call_id?: string;
};

export type SubagentActivity = {
  id: string;
  evalId?: string;
  name: string;
  description: string;
  status: "pending" | "running" | "complete" | "error";
};

type StageState = "waiting" | "running" | "complete" | "error";

export function messageText(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .map((part) =>
      typeof part === "string"
        ? part
        : typeof part === "object" && part !== null && "text" in part
          ? String((part as { text?: unknown }).text ?? "")
          : "",
    )
    .join("");
}

export function findEvalCall(messages: WorkflowMessage[]): WorkflowToolCall | undefined {
  return messages
    .flatMap((message) => message.tool_calls ?? [])
    .reverse()
    .find((call) => call.name === "eval");
}

export function findEvalResult(
  messages: WorkflowMessage[],
  evalCall: WorkflowToolCall | undefined,
): WorkflowMessage | undefined {
  if (!evalCall?.id) return undefined;
  return messages.find(
    (message) => message.type === "tool" && message.tool_call_id === evalCall.id,
  );
}

export function isSuccessfulEvalResult(evalResult: WorkflowMessage | undefined): boolean {
  if (!evalResult) return false;
  const output = messageText(evalResult.content).trim();
  return /<result(?:\s[^>]*)?>[\s\S]*<\/result>$/i.test(output);
}

function stageClass(state: StageState): string {
  return `trace-step trace-step--${state}`;
}

export default function WorkflowEvidence({
  messages,
  activities,
  isLoading,
}: {
  messages: WorkflowMessage[];
  activities: SubagentActivity[];
  isLoading: boolean;
}) {
  const keywordDetected = messages.some(
    (message) => message.type === "human" && /\bworkflow\b/i.test(messageText(message.content)),
  );
  const evalCall = findEvalCall(messages);
  const evalResult = findEvalResult(messages, evalCall);
  const evalSucceeded = isSuccessfulEvalResult(evalResult);
  const evalFailed = Boolean(evalResult && !evalSucceeded);
  const evalResultIndex = evalResult ? messages.indexOf(evalResult) : -1;
  const finalAnswer =
    evalSucceeded && evalResultIndex >= 0
      ? messages.find(
          (message, index) =>
            index > evalResultIndex &&
            message.type === "ai" &&
            messageText(message.content).trim().length > 0,
        )
      : undefined;
  const hasEvalScopedActivities = activities.some((activity) => activity.evalId);
  const visibleActivities =
    evalCall?.id && hasEvalScopedActivities
      ? activities.filter((activity) => activity.evalId === evalCall.id)
      : activities;
  const completeCount = visibleActivities.filter((activity) => activity.status === "complete").length;
  const errorCount = visibleActivities.filter((activity) => activity.status === "error").length;
  const allComplete = visibleActivities.length > 0 && completeCount === visibleActivities.length;
  const allTerminal =
    visibleActivities.length > 0 &&
    visibleActivities.every(
      (activity) => activity.status === "complete" || activity.status === "error",
    );
  const workflowComplete = Boolean(evalSucceeded && finalAnswer && allComplete);

  const keywordState: StageState = keywordDetected ? "complete" : "waiting";
  const triggerState: StageState = evalCall ? "complete" : "waiting";
  const dispatchState: StageState =
    visibleActivities.length === 0
      ? "waiting"
      : allTerminal && errorCount > 0
        ? "error"
        : allComplete
          ? "complete"
          : "running";
  const completeState: StageState = evalFailed ? "error" : workflowComplete ? "complete" : "waiting";

  return (
    <>
      <section className="panel trace-panel" aria-label="Activation evidence">
        <div className="panel__head">
          <span>Activation evidence</span>
          <span>
            {workflowComplete ? "workflow complete" : evalFailed ? "workflow failed" : isLoading ? "live" : "ready"}
          </span>
        </div>
        <div className="trace-grid">
          <div
            className={stageClass(keywordState)}
            data-state={keywordState}
            data-testid="keyword-stage"
          >
            <i aria-hidden="true" />
            <strong>Workflow keyword</strong>
            <small>{keywordDetected ? "已检测到 workflow 关键词" : "等待自然任务请求"}</small>
          </div>
          <div
            className={stageClass(triggerState)}
            data-state={triggerState}
            data-testid="trigger-stage"
          >
            <i aria-hidden="true" />
            <strong>Dynamic triggered</strong>
            <small>{evalCall ? "已观察到解释器 tool call" : "等待解释器调用"}</small>
          </div>
          <div
            className={stageClass(dispatchState)}
            data-state={dispatchState}
            data-testid="dispatch-stage"
          >
            <i aria-hidden="true" />
            <strong>Agents dispatched</strong>
            <small>
              {visibleActivities.length > 0
                ? `${completeCount} / ${visibleActivities.length} completed`
                : "等待真实 subagent 事件"}
            </small>
          </div>
          <div
            className={stageClass(completeState)}
            data-state={completeState}
            data-testid="complete-stage"
          >
            <i aria-hidden="true" />
            <strong>Workflow complete</strong>
            <small>
              {workflowComplete
                ? "当前 Pattern 已达到结束条件"
                : evalFailed
                  ? "解释器返回错误，当前 Pattern 未完成"
                  : "等待解释器结果与最终回答"}
            </small>
          </div>
        </div>
      </section>

      <section className="panel activity-panel" aria-label="Subagent activity">
        <div className="panel__head">
          <span>Subagent activity</span>
          <span>
            {visibleActivities.length > 0
              ? `${visibleActivities.length} observed`
              : "stream evidence"}
          </span>
        </div>
        {visibleActivities.length > 0 ? (
          <ul className="activity-list">
            {visibleActivities.map((activity) => (
              <li className={`activity-item activity-item--${activity.status}`} key={activity.id}>
                <i aria-hidden="true" />
                <span>{activity.name} · {activity.description}</span>
                <span>{activity.status}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="activity-empty">
            运行后，这里只展示从 subagent stream 观察到的角色和状态，不用预设数据填充。
          </p>
        )}
      </section>
    </>
  );
}
{% endraw %}
