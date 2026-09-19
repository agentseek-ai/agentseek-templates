import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import MemoryPanel from "./MemoryPanel";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("writes only after an explicit save and displays the returned evidence", async () => {
  let saved = false;
  const entry = { text: "Phoenix needs review", version: 1, citation: { entry_id: "entry-1", entry_version_id: "version-1", memory_ref: { revision: 1 } } };
  const fetchMock = vi.fn(async (_url: string, options?: RequestInit) => {
    if (options?.method === "POST") { saved = true; return Response.json({ entry }); }
    return Response.json({ scope_id: "scope-one", entries: saved ? [entry] : [] });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<MemoryPanel apiUrl="http://localhost" disabled={false} />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Save decision" })).toBeTruthy());
  expect(saved).toBe(false);
  fireEvent.change(screen.getByLabelText("Decision to keep across conversations"), { target: { value: "Phoenix needs review" } });
  fireEvent.click(screen.getByRole("button", { name: "Save decision" }));
  await waitFor(() => expect(screen.getByText("Phoenix needs review")).toBeTruthy());
  expect(screen.getByText(/Saved to PowerContext/)).toBeTruthy();
  expect(fetchMock.mock.calls.find(([, options]) => options?.method === "POST")?.[1]?.body).toBe(JSON.stringify({ text: "Phoenix needs review" }));
});

it("reports a failed write without claiming it was saved", async () => {
  vi.stubGlobal("fetch", vi.fn(async (_url: string, options?: RequestInit) => options?.method === "POST"
    ? Response.json({ detail: "Memory operation was not confirmed." }, { status: 503 })
    : Response.json({ scope_id: "scope-one", entries: [] })));
  render(<MemoryPanel apiUrl="http://localhost" disabled={false} />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Save decision" })).toBeTruthy());
  fireEvent.click(screen.getByRole("button", { name: "Save decision" }));
  await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("not confirmed"));
  expect(screen.queryByText(/Saved to PowerContext/)).toBeNull();
});
