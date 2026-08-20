import type { ReactNode } from "react";

export type StreamEvent = {
  kind: string;
  source?: string;
  path?: string[];
  phase?: string;
  name?: string;
  status?: string;
  text?: string;
  tool_name?: string;
  input?: unknown;
  delta?: unknown;
  output?: unknown;
  error?: unknown;
  snapshot?: unknown;
  sequence?: number;
  method?: string;
  namespace?: string[];
  data?: unknown;
  message?: string;
};

function json(value: unknown): string {
  if (value === undefined || value === null || value === "") return "";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function pathLabel(path: string[] | undefined): string {
  return path && path.length > 0 ? path.join(" / ") : "coordinator";
}

export default function EventTimeline({ events }: { events: StreamEvent[] }): ReactNode {
  return (
    <section className="timeline" aria-label="Event timeline">
      {events.map((event, index) => {
        const key = `${event.kind}-${event.sequence ?? index}`;
        if (event.kind === "message") {
          return (
            <article className="event-card event-card--message" key={key}>
              <div className="event-card__eyebrow">{event.source ?? "agent"} · message</div>
              <p>{event.text}</p>
              <small>{pathLabel(event.path)}</small>
            </article>
          );
        }
        if (event.kind === "subagent") {
          return (
            <article className={`event-card event-card--subagent event-card--${event.phase}`} key={key}>
              <div className="event-card__eyebrow">subagents · {event.phase}</div>
              <strong>{event.name}</strong>
              <span className="event-card__badge">{event.status}</span>
              <small>{pathLabel(event.path)}</small>
            </article>
          );
        }
        if (event.kind === "tool_call") {
          return (
            <details className={`event-card event-card--tool event-card--${event.phase}`} key={key} open={event.phase === "started"}>
              <summary>
                <span>{event.tool_name}</span>
                <span className="event-card__badge">{event.phase}</span>
              </summary>
              {event.input !== undefined && <pre>{json(event.input)}</pre>}
              {event.delta !== undefined && <pre>{json(event.delta)}</pre>}
              {event.output !== undefined && <pre>{json(event.output)}</pre>}
              {event.error !== undefined && <pre className="error-text">{json(event.error)}</pre>}
              <small>{event.source ?? "agent"} · {pathLabel(event.path)}</small>
            </details>
          );
        }
        if (event.kind === "values") {
          return (
            <details className="event-card event-card--values" key={key}>
              <summary>values · state snapshot</summary>
              <pre>{json(event.snapshot)}</pre>
            </details>
          );
        }
        if (event.kind === "output") {
          return (
            <details className={`event-card event-card--output event-card--${event.phase ?? "completed"}`} key={key} open>
              <summary>output · {event.phase === "failed" ? "failed" : "final run state"}</summary>
              {event.error !== undefined ? <pre className="error-text">{json(event.error)}</pre> : <pre>{json(event.output)}</pre>}
            </details>
          );
        }
        if (event.kind === "raw") {
          return (
            <details className="event-card event-card--raw" key={key}>
              <summary>raw · seq {event.sequence ?? "?"} · {event.method}</summary>
              <small>namespace: {pathLabel(event.namespace)}</small>
              <pre>{json(event.data)}</pre>
            </details>
          );
        }
        if (event.kind === "error") {
          return (
            <article className="event-card event-card--error" key={key}>
              <div className="event-card__eyebrow">stream · error</div>
              <p className="error-text">{event.message}</p>
            </article>
          );
        }
        return null;
      })}
    </section>
  );
}
