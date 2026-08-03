import type { RunReport } from "./contracts";

type AcceptanceGateProps = {
  report: RunReport | null;
};

export function AcceptanceGate({ report }: AcceptanceGateProps) {
  if (report === null) {
    return (
      <section aria-labelledby="acceptance-gate-title">
        <h2 id="acceptance-gate-title">Acceptance Gate</h2>
        <p>No completed report yet.</p>
      </section>
    );
  }

  const coherentAcceptance =
    report.accepted &&
    report.terminalStatus === "satisfied" &&
    report.gateReason === "satisfied_with_current_evidence";
  const contractError = report.accepted && !coherentAcceptance;
  const heading = contractError
    ? "Report contract error"
    : coherentAcceptance
      ? "Accepted"
      : "Not accepted";

  return (
    <section aria-labelledby="acceptance-gate-result">
      <p>Acceptance Gate</p>
      <h2 id="acceptance-gate-result">{heading}</h2>
      <dl>
        <div>
          <dt>Terminal status</dt>
          <dd>{report.terminalStatus}</dd>
        </div>
        <div>
          <dt>Gate reason</dt>
          <dd>{report.gateReason}</dd>
        </div>
      </dl>
    </section>
  );
}
