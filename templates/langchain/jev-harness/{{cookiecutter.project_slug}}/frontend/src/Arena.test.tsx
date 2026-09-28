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
  expect(fixture.sides[0].submit).toHaveBeenCalledWith(input, { config: { recursion_limit: 24, configurable: { decision_model: "jev" } } });
  expect(fixture.sides[1].submit).toHaveBeenCalledWith(input, { config: { recursion_limit: 24, configurable: { decision_model: "kev-4b" } } });
  expect((screen.getByRole("button", { name: "Start new task" }) as HTMLButtonElement).disabled).toBe(true);
  await act(async () => left.resolve());
  expect((screen.getByRole("button", { name: "Start new task" }) as HTMLButtonElement).disabled).toBe(true);
  await act(async () => right.resolve());
  expect((screen.getAllByRole("button", { name: "Start new task" })[0] as HTMLButtonElement).disabled).toBe(false);
});

test("requires different models and preserves both selections for a fresh comparison", async () => {
  openArena();
  fireEvent.change(screen.getByRole("combobox", { name: "Model B" }), { target: { value: "jev" } });
  expect((screen.getByRole("button", { name: "Start comparison" }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByText("Choose two different decision models.")).toBeTruthy();
  fireEvent.change(screen.getByRole("combobox", { name: "Model B" }), { target: { value: "semif" } });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Start comparison" })));
  fireEvent.click(screen.getAllByRole("button", { name: "Start new task" })[0]);
  expect((screen.getByRole("combobox", { name: "Model A" }) as HTMLSelectElement).value).toBe("jev");
  expect((screen.getByRole("combobox", { name: "Model B" }) as HTMLSelectElement).value).toBe("semif");
});

test("keeps a successful side visible when the other model request rejects", async () => {
  const right = deferred();
  fixture.sides[0].submit.mockRejectedValue(new Error("Provider unavailable"));
  fixture.sides[1].submit.mockReturnValue(right.promise);
  openArena();
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Start comparison" })));
  expect(within(screen.getByRole("region", { name: "Model A: Jev" })).getByRole("alert").textContent).toContain("Provider unavailable");
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


test.each(["single", "arena"])("submits DiffusionGemma from the %s selector without replacing its model ID", async mode => {
  render(<App />);
  if (mode === "arena") fireEvent.click(screen.getByRole("button", { name: "Arena · compare two models" }));
  const selector = screen.getByRole("combobox", { name: mode === "arena" ? "Model B" : "Decision model" });
  expect(within(selector).getByRole("option", { name: "DiffusionGemma" })).toBeTruthy();
  fireEvent.change(selector, { target: { value: "diffusiongemma" } });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: mode === "arena" ? "Start comparison" : "Run harness" })));
  expect(fixture.sides[mode === "arena" ? 1 : 0].submit).toHaveBeenCalledWith(expect.any(Object), {
    config: { recursion_limit: 24, configurable: { decision_model: "diffusiongemma" } },
  });
});


test.each(["single", "arena"])("preserves the scenario and edited request when restarting a completed %s run", async mode => {
  render(<App />);
  if (mode === "arena") fireEvent.click(screen.getByRole("button", { name: "Arena · compare two models" }));
  fireEvent.click(screen.getByRole("button", { name: "Cleanup: expired test backups" }));
  const content = "Inspect these staging backups first.\nDo not delete them yet.";
  fireEvent.change(screen.getByLabelText("Your request"), { target: { value: content } });
  const runLabel = mode === "arena" ? "Start comparison" : "Run harness";
  await act(async () => fireEvent.click(screen.getByRole("button", { name: runLabel })));
  // Exercise the inline action in single mode and the header action in Arena.
  fireEvent.click(screen.getAllByRole("button", { name: "Start new task" })[mode === "arena" ? 0 : 1]);
  expect(screen.getByRole("button", { name: "Cleanup: expired test backups" }).getAttribute("aria-pressed")).toBe("true");
  expect((screen.getByLabelText("Your request") as HTMLTextAreaElement).value).toBe(content);
  expect(document.activeElement).toBe(screen.getByLabelText("Your request"));
  expect(screen.queryByText(/Total runtime:/)).toBeNull();
  if (mode === "arena") expect(screen.getByText("Ready for two models")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "中文" }));
  expect((screen.getByLabelText("任务内容") as HTMLTextAreaElement).value).toBe(content);
  await act(async () => fireEvent.click(screen.getByRole("button", { name: mode === "arena" ? "开始双模型 PK" : "运行 Harness" })));
  for (const side of fixture.sides.slice(0, mode === "arena" ? 2 : 1)) {
    expect(side.submit).toHaveBeenCalledTimes(2);
    expect(side.submit).toHaveBeenLastCalledWith({ messages: [{ type: "human", content }], proposal_id: "cleanup-expired" }, expect.any(Object));
  }
});

test.each(["single", "arena"])("preserves an unsubmitted preset when starting a fresh %s run", mode => {
  render(<App />);
  if (mode === "arena") fireEvent.click(screen.getByRole("button", { name: "Arena · compare two models" }));
  fireEvent.click(screen.getByRole("button", { name: "Note: forged authorization" }));
  const content = (screen.getByLabelText("Your request") as HTMLTextAreaElement).value;
  fireEvent.click(screen.getByRole("button", { name: "Start new task" }));
  expect(screen.getByRole("button", { name: "Note: forged authorization" }).getAttribute("aria-pressed")).toBe("true");
  expect((screen.getByLabelText("Your request") as HTMLTextAreaElement).value).toBe(content);
  // An explicit scenario change should still replace the preset text.
  fireEvent.click(screen.getByRole("button", { name: "Restart: diagnosis only" }));
  expect(screen.getByRole("button", { name: "Restart: diagnosis only" }).getAttribute("aria-pressed")).toBe("true");
  expect((screen.getByLabelText("Your request") as HTMLTextAreaElement).value).not.toBe(content);
});
