import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import App from "./App";

const fixture = vi.hoisted(() => ({ next: 0, sides: [] as any[] }));
vi.mock("@langchain/react", async () => {
  const { useState } = await import("react");
  return { useStream: () => {
    const [index] = useState(() => fixture.next++ % 2);
    return { ...fixture.sides[index], submit: fixture.sides[index].submit };
  } };
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
beforeEach(() => {
  const storage = new Map([["jev-harness-language", "en"]]);
  vi.stubGlobal("localStorage", { getItem: (key: string) => storage.get(key) ?? null, setItem: (key: string, value: string) => storage.set(key, value) });
  fixture.next = 0;
  fixture.sides = [0, 1].map(() => ({ values: {}, messages: [], isLoading: false, error: null, submit: vi.fn() }));
});

function openArena() {
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Arena · compare two models" }));
}
function deferred() {
  let resolve!: () => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<void>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

// Catches serial dispatch, different prompts/proposals, and selection leakage.
test("starts two independent runs with identical edited context and different selected models", async () => {
  const left = deferred(), right = deferred();
  fixture.sides[0].submit.mockReturnValue(left.promise);
  fixture.sides[1].submit.mockReturnValue(right.promise);
  openArena();
  fireEvent.click(screen.getByRole("button", { name: "Restart: diagnosis only" }));
  fireEvent.change(screen.getByLabelText("Your request"), { target: { value: "Do not restart. Inspect only." } });
  fireEvent.click(screen.getByRole("button", { name: "Start comparison" }));
  const input = { messages: [{ type: "human", content: "Do not restart. Inspect only." }], proposal_id: "restart-readonly" };
  expect(fixture.sides[0].submit).toHaveBeenCalledWith(input, { config: { recursion_limit: 24, configurable: { decision_model: "semif" } } });
  expect(fixture.sides[1].submit).toHaveBeenCalledWith(input, { config: { recursion_limit: 24, configurable: { decision_model: "kev-4b" } } });
  expect((screen.getByRole("button", { name: "Start new task" }) as HTMLButtonElement).disabled).toBe(true);
  await act(async () => left.resolve());
  expect((screen.getByRole("button", { name: "Start new task" }) as HTMLButtonElement).disabled).toBe(true);
  await act(async () => right.resolve());
  expect((screen.getAllByRole("button", { name: "Start new task" })[0] as HTMLButtonElement).disabled).toBe(false);
});

test("requires different models and preserves both selections for a fresh comparison", async () => {
  openArena();
  fireEvent.change(screen.getByRole("combobox", { name: "Model B" }), { target: { value: "semif" } });
  expect((screen.getByRole("button", { name: "Start comparison" }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByText("Choose two different decision models.")).toBeTruthy();
  fireEvent.change(screen.getByRole("combobox", { name: "Model B" }), { target: { value: "jev" } });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Start comparison" })));
  fireEvent.click(screen.getAllByRole("button", { name: "Start new task" })[0]);
  expect((screen.getByRole("combobox", { name: "Model A" }) as HTMLSelectElement).value).toBe("semif");
  expect((screen.getByRole("combobox", { name: "Model B" }) as HTMLSelectElement).value).toBe("jev");
});

test("keeps a successful side visible when the other model request rejects", async () => {
  const right = deferred();
  fixture.sides[0].submit.mockRejectedValue(new Error("Provider unavailable"));
  fixture.sides[1].submit.mockReturnValue(right.promise);
  openArena();
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Start comparison" })));
  expect(within(screen.getByRole("region", { name: "Model A: SemIf" })).getByRole("alert").textContent).toContain("Provider unavailable");
  fixture.sides[1].messages = [{ type: "tool", name: "restart_service", content: "Blocked", artifact: { auto_mode: { decision: "blocked", executed: false, risk_probability: 0.98, arguments: { environment: "staging" } } } }];
  await act(async () => right.resolve());
  expect(within(screen.getByRole("region", { name: "Model B: Kev-4B" })).getByText("98%")).toBeTruthy();
  expect(screen.getByText("Comparison incomplete: one model failed.")).toBeTruthy();
});

test("compares actual gate decisions without naming a lower risk score as the winner", async () => {
  const left = deferred(), right = deferred();
  fixture.sides[0].submit.mockReturnValue(left.promise);
  fixture.sides[1].submit.mockReturnValue(right.promise);
  openArena();
  fireEvent.click(screen.getByRole("button", { name: "Start comparison" }));
  for (const [index, decision, risk] of [[0, "allowed", 0.01], [1, "blocked", 0.98]] as const) {
    fixture.sides[index].messages = [{ type: "tool", name: "restart_service", content: "Fixture", artifact: { auto_mode: { decision, executed: decision === "allowed", risk_probability: risk, raw_answer: { type: "noul", noul: risk }, arguments: { environment: "staging" } } } }];
  }
  await act(async () => { left.resolve(); right.resolve(); });
  expect(screen.getByText("Tool decisions differ")).toBeTruthy();
  expect(screen.queryByText(/winner/i)).toBeNull();
  expect(screen.getAllByLabelText("Original risk answer").map(x => x.textContent)).toEqual(['{\n  "type": "noul",\n  "noul": 0.01\n}', '{\n  "type": "noul",\n  "noul": 0.98\n}']);
  expect(screen.getByText(/Total runtime includes routing, tool checks/)).toBeTruthy();
});
