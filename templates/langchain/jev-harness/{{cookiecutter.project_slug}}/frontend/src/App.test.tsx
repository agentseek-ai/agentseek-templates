import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import App from "./App";

const fixture = vi.hoisted(() => ({
  submit: vi.fn(),
  state: { values: {}, messages: [], isLoading: false, error: null } as Record<string, unknown>,
}));
vi.mock("@langchain/react", () => ({ useStream: () => ({ ...fixture.state, submit: fixture.submit }) }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
beforeEach(() => {
  // Vitest can inherit Node's non-browser Storage global on recent Node releases.
  const values = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
  });
  window.localStorage.setItem("jev-harness-language", "en");
  fixture.submit.mockReset();
  fixture.state = { values: {}, messages: [], isLoading: false, error: null };
});

test("switches the entire console to Chinese and persists the selection", () => {
  const view = render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "中文" }));
  expect(screen.getByRole("heading", { name: "模型路由" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "运行 Harness" })).toBeTruthy();
  expect(screen.getByLabelText("任务内容").textContent).toContain("授权");
  expect(screen.getByText(/OPENAI_API_KEY 填写硅基流动密钥/)).toBeTruthy();
  expect(screen.getByText("使用自己的模型服务")).toBeTruthy();
  expect(window.localStorage.getItem("jev-harness-language")).toBe("zh");
  expect(document.documentElement.lang).toBe("zh-CN");
  view.unmount();
  render(<App />);
  expect(screen.getByRole("heading", { name: "模型路由" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "English" }));
  expect(screen.getByRole("heading", { name: "Model routing" })).toBeTruthy();
});

test("language changes preserve a manually edited task", () => {
  render(<App />);
  fireEvent.change(screen.getByLabelText("Your request"), { target: { value: "My custom request" } });
  fireEvent.click(screen.getByRole("button", { name: "中文" }));
  expect((screen.getByLabelText("任务内容") as HTMLTextAreaElement).value).toBe("My custom request");
});

test("only exposes context experiments and submits the chosen fixed proposal", () => {
  render(<App />);
  expect(screen.getByText(/Default setup: fill OPENAI_API_KEY/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Agent chooses tools" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Cleanup: expired test backups" }));
  fireEvent.click(screen.getByRole("button", { name: "Run harness" }));
  expect(fixture.submit).toHaveBeenCalledWith(
    expect.objectContaining({ proposal_id: "cleanup-expired" }),
    expect.objectContaining({ config: { recursion_limit: 24, configurable: { decision_model: "semif" } } }),
  );
});

test("displays route confidence separately from probabilities and blocked execution", () => {
  fixture.state = {
    values: { route_report: { choice: "powerful", model: "my-reasoner", confidence: 0.72,
      probabilities: { fast: 0.1, powerful: 0.9 } } },
    messages: [{ type: "tool", name: "delete_backups", content: "Tool blocked.", tool_call_id: "a",
      artifact: { auto_mode: { decision: "blocked", executed: false, risk_probability: 0.97 } } }],
    isLoading: false, error: null,
  };
  render(<App />);
  expect(screen.getByText("my-reasoner")).toBeTruthy();
  expect(screen.getByText("72%")).toBeTruthy();
  expect(screen.getByText("90%")).toBeTruthy();
  expect(screen.getByText("Blocked")).toBeTruthy();
  expect(screen.getByText(/Tool did not run/)).toBeTruthy();
  expect(screen.getByText(/97%/)).toBeTruthy();
});

test("does not fabricate a risk score for an allowed tool", () => {
  fixture.state.messages = [{ type: "tool", name: "read_service_status", content: "fixture",
    artifact: { auto_mode: { decision: "allowed", executed: true, risk_probability: null } } }];
  render(<App />);
  expect(screen.getByText("Allowed")).toBeTruthy();
  expect(screen.getByText(/Risk probability unavailable/)).toBeTruthy();
});

test("submits an editable context with a fixed proposal and identifies its source", () => {
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Restart: diagnosis only" }));
  expect(screen.getByText(/restart_service/)).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Your request"), { target: { value: "Only read. Do not restart staging." } });
  fireEvent.click(screen.getByRole("button", { name: "Run harness" }));
  expect(fixture.submit).toHaveBeenCalledWith({ messages: [{ type: "human", content: "Only read. Do not restart staging." }], proposal_id: "restart-readonly" }, expect.anything());
});

test("shows allowed risk probability, arguments and the Noul confidence boundary", () => {
  fixture.state.messages = [{ type: "tool", name: "restart_service", content: "Simulated restart.",
    artifact: { auto_mode: { decision: "allowed", executed: true, risk_probability: 0.06,
      confidence: null, arguments: { environment: "staging" }, proposal_source: "preset" } } }];
  render(<App />);
  expect(screen.getByText("6%")).toBeTruthy();
  expect(screen.getByText("Fixed proposal")).toBeTruthy();
  expect(screen.getByText(/Noul does not return a separate confidence/)).toBeTruthy();
  expect(screen.getByText(/"environment": "staging"/)).toBeTruthy();
});

test("shows provider failures and disables duplicate submissions", () => {
  fixture.state.error = new Error("Classifier unavailable");
  fixture.state.isLoading = true;
  render(<App />);
  expect(screen.getByRole("alert").textContent).toContain("Classifier unavailable");
  expect((screen.getByRole("button", { name: "Running…" }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole("button", { name: "Start new task" }) as HTMLButtonElement).disabled).toBe(true);
});

test("offers a fresh task at the point of completion and focuses the editable request", () => {
  const view = render(<App />);
  fireEvent.change(screen.getByLabelText("Your request"), { target: { value: "My completed task" } });
  fireEvent.click(screen.getByRole("button", { name: "Run harness" }));
  fixture.state.isLoading = true;
  view.rerender(<App />);
  expect(screen.getAllByRole("button", { name: "Start new task" })).toHaveLength(1);
  fixture.state.isLoading = false;
  view.rerender(<App />);
  const buttons = screen.getAllByRole("button", { name: "Start new task" });
  expect(buttons).toHaveLength(2);
  fireEvent.click(buttons[1]);
  const input = screen.getByLabelText("Your request") as HTMLTextAreaElement;
  expect(input.disabled).toBe(false);
  expect(input.value).not.toBe("My completed task");
  expect(document.activeElement).toBe(input);
  expect((screen.getByRole("button", { name: "Run harness" }) as HTMLButtonElement).disabled).toBe(false);
});


test("distinguishes gate approval from failed tool execution", () => {
  fixture.state.messages = [{ type: "tool", name: "restart_service", content: "Missing environment.",
    artifact: { auto_mode: { decision: "allowed", executed: false, execution_status: "failed", risk_probability: 0.1 } } }];
  render(<App />);
  expect(screen.getByText("Allowed")).toBeTruthy();
  expect(screen.getByText(/argument validation or tool execution failed/)).toBeTruthy();
  expect(screen.queryByText("Simulated tool ran.")).toBeNull();
});


test("keeps Fast on the left and Powerful on the right when response order and winner change", () => {
  const view = render(<App />);
  const names = () => screen.getAllByRole("article").map(card => card.getAttribute("aria-label"));
  expect(names()).toEqual(["Fast", "Powerful"]);
  for (const choice of ["powerful", "fast"]) {
    fixture.state.values = { route_report: { choice, model: choice === "fast" ? "custom-flash" : "custom-pro", confidence: 0.8,
      models: { fast: "custom-flash", powerful: "custom-pro" },
      probabilities: { powerful: choice === "powerful" ? 0.9 : 0.1, fast: choice === "fast" ? 0.9 : 0.1 } } };
    view.rerender(<App />);
    expect(names()).toEqual(["Fast", "Powerful"]);
    expect(within(screen.getByRole("article", { name: choice === "fast" ? "Fast" : "Powerful" })).getByText("Selected")).toBeTruthy();
    expect(screen.getByText("custom-flash")).toBeTruthy();
    expect(screen.getByText("custom-pro")).toBeTruthy();
  }
});

test("shows the original Jev answer separately from an unchanged allowed tool payload", () => {
  const content = '{"simulation":true,"operation":"delete_backups"}';
  fixture.state.messages = [{ type: "tool", name: "delete_backups", content,
    artifact: { auto_mode: { decision: "allowed", executed: true, risk_probability: 0.052,
      jev_answer: { type: "noul", noul: 0.052 } } } }];
  render(<App />);
  fireEvent.click(screen.getByText("Inspect decision and execution"));
  expect(screen.getByLabelText("Original risk answer").textContent).toContain('"noul": 0.052');
  expect(screen.getByLabelText("Simulated tool output").textContent).toBe(content);
  expect(screen.getByText("5%")).toBeTruthy();
});


test("selects a decision model for the run and retains it for a new comparison", () => {
  render(<App />);
  const select = screen.getByRole("combobox", { name: "Decision model" }) as HTMLSelectElement;
  expect(select.value).toBe("semif");
  fireEvent.change(select, { target: { value: "jev" } });
  fireEvent.click(screen.getByRole("button", { name: "Run harness" }));
  expect(fixture.submit).toHaveBeenCalledWith(expect.anything(), {
    config: { recursion_limit: 24, configurable: { decision_model: "jev" } },
  });
  expect(select.disabled).toBe(true);
  fireEvent.click(screen.getAllByRole("button", { name: "Start new task" })[0]);
  expect((screen.getByRole("combobox", { name: "Decision model" }) as HTMLSelectElement).value).toBe("jev");
});

test("attributes SemIf decisions to the returned provider without calling them Jev answers", () => {
  fixture.state.values = { route_report: { choice: "fast", model: "chat-fast", confidence: 0.8,
    probabilities: { fast: 0.9, powerful: 0.1 },
    decision_model: { selection: "semif", provider: "siliconflow", model: "semif", label: "SemIf" } } };
  fixture.state.messages = [{ type: "tool", name: "restart_service", content: "Simulated restart.",
    artifact: { auto_mode: { decision: "allowed", executed: true, risk_probability: 0.04,
      decision_model: { selection: "semif", provider: "siliconflow", model: "semif", label: "SemIf" },
      raw_answer: { type: "noul", noul: 0.04 } } } }];
  render(<App />);
  expect(screen.getByLabelText("Original risk answer").textContent).toContain('"noul": 0.04');
  expect(screen.getAllByText("SiliconFlow / semif").length).toBeGreaterThan(0);
  expect(screen.queryByText("Original Jev risk answer")).toBeNull();
});
