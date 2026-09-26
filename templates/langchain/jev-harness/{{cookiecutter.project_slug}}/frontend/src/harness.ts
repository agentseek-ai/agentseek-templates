export type DecisionModel = { selection: string; provider: string; model: string; label: string };
export type Audit = { decision: "allowed" | "blocked"; executed: boolean; risk_probability: number | null;
  jev_answer?: { type: "noul"; noul: number }; // Historical Jev records.
  raw_answer?: { type: "noul"; noul: number }; decision_model?: DecisionModel;
  execution_status?: "completed" | "failed" | "blocked";
  confidence?: null; arguments?: Record<string, unknown>; proposal_source?: "preset" | "agent" };
export type Message = { id?: string; type: string; content: unknown; name?: string; tool_call_id?: string;
  artifact?: { auto_mode?: Audit } };
export type Route = { decision_model?: DecisionModel; choice: string; model: string; confidence: number; probabilities: Record<string, number>; models?: Record<string, string> };
export type HarnessState = { messages: Message[]; route_report?: Route; proposal_id?: string | null };
export const providerName = (model: DecisionModel) => `${model.provider === "siliconflow" ? "SiliconFlow" : "TypeSafe"} / ${model.model}`;

export const percent = (value: number) => `${Math.round(value * 100)}%`;

export function messageText(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) return content.map(part => typeof part === "string" ? part : part?.text ?? "").join("");
  return "";
}
