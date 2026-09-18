import type { ReactNode } from "react";
import { useI18n } from "./i18n";

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
  content_bytes?: number;
  max_bytes?: number;
  scope_id?: string;
  content?: string | null;
  detail?: string;
};

function json(value: unknown): string {
  if (value === undefined || value === null || value === "") return "";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export default function EventTimeline({ events }: { events: StreamEvent[] }): ReactNode {
  const { t } = useI18n();

  function sourceLabel(source: string | undefined): string {
    if (source === "coordinator") return t("timeline.source.coordinator");
    if (source === "subagent") return t("timeline.source.subagent");
    return source ?? t("timeline.source.agent");
  }

  function pathLabel(path: string[] | undefined): string {
    return path && path.length > 0 ? path.join(" / ") : t("timeline.source.coordinator");
  }

  return (
    <section className="timeline" aria-label={t("timeline.aria")}>
      {events.map((event, index) => {
        const key = `${event.kind}-${event.sequence ?? index}`;
        if (event.kind === "message") {
          return (
            <article className="event-card event-card--message" key={key}>
              <div className="event-card__eyebrow">{sourceLabel(event.source)} · {t("timeline.message")}</div>
              <p>{event.text}</p>
              <small>{pathLabel(event.path)}</small>
            </article>
          );
        }
        if (event.kind === "subagent") {
          return (
            <article className={`event-card event-card--subagent event-card--${event.phase}`} key={key}>
              <div className="event-card__eyebrow">{t("timeline.subagents")} · {event.phase}</div>
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
              <small>{sourceLabel(event.source)} · {pathLabel(event.path)}</small>
            </details>
          );
        }
        if (event.kind === "values") {
          return (
            <details className="event-card event-card--values" key={key}>
              <summary>{t("timeline.values")}</summary>
              <pre>{json(event.snapshot)}</pre>
            </details>
          );
        }
        if (event.kind === "output") {
          return (
            <details className={`event-card event-card--output event-card--${event.phase ?? "completed"}`} key={key} open>
              <summary>{event.phase === "failed" ? t("timeline.outputFailed") : t("timeline.output")}</summary>
              {event.error !== undefined ? <pre className="error-text">{json(event.error)}</pre> : <pre>{json(event.output)}</pre>}
            </details>
          );
        }
        if (event.kind === "raw") {
          return (
            <details className="event-card event-card--raw" key={key}>
              <summary>{t("timeline.raw", { sequence: event.sequence ?? "?" })} · {event.method}</summary>
              <small>{t("timeline.namespace")} {pathLabel(event.namespace)}</small>
              <pre>{json(event.data)}</pre>
            </details>
          );
        }
        if (event.kind === "error") {
          return (
            <article className="event-card event-card--error" key={key}>
              <div className="event-card__eyebrow">{t("timeline.streamError")}</div>
              <p className="error-text">{event.message}</p>
            </article>
          );
        }
        if (event.kind === "powercontext") {
          return (
            <article className="event-card event-card--powercontext" key={key}>
              <div className="event-card__eyebrow">PowerContext · {event.status}</div>
              <p>{t("timeline.bytesPrepared", { bytes: event.content_bytes ?? 0 })}{event.max_bytes !== undefined ? ` / ${event.max_bytes}` : ""}{event.detail ? ` · ${event.detail}` : ""}</p>
              {event.status === "empty" && <p>{t("timeline.empty")}</p>}
              {event.status === "disabled" && <p>{t("timeline.disabled")}</p>}
              {event.status === "unavailable" && <p>{t("timeline.unavailable")}</p>}
              {event.content && <details><summary>{t("timeline.contextSummary")}</summary><pre>{event.content}</pre><small>{t("timeline.contextNote")}</small></details>}
            </article>
          );
        }
        return null;
      })}
    </section>
  );
}
