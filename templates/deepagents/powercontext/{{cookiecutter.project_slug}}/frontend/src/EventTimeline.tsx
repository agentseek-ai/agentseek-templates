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

/**
 * Renders only the recalled PowerContext evidence and the agents' answer.
 * The stream still carries the v3 protocol projections, but the browser
 * deliberately hides raw, state, sub-agent and tool events.
 */
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
        if (event.kind === "powercontext") {
          return (
            <article className="event-card event-card--powercontext" key={key}>
              <div className="event-card__eyebrow">PowerContext · {event.status}</div>
              <p>{t("timeline.bytesPrepared", { bytes: event.content_bytes ?? 0 })}{event.max_bytes !== undefined ? ` / ${event.max_bytes}` : ""}{event.detail ? ` · ${event.detail}` : ""}</p>
              {event.status === "empty" && <p>{t("timeline.empty")}</p>}
              {event.status === "disabled" && <p>{t("timeline.disabled")}</p>}
              {event.status === "unavailable" && <p>{t("timeline.unavailable")}</p>}
              {event.content && <details open><summary>{t("timeline.contextSummary")}</summary><pre>{event.content}</pre><small>{t("timeline.contextNote")}</small></details>}
            </article>
          );
        }
        if (event.kind === "message") {
          return (
            <article className="event-card event-card--message" key={key}>
              <div className="event-card__eyebrow">{sourceLabel(event.source)} · {t("timeline.message")}</div>
              <p>{event.text}</p>
              <small>{pathLabel(event.path)}</small>
            </article>
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
        return null;
      })}
    </section>
  );
}
