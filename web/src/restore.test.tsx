import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { askInThread, loadLatestTurn, type AskResponse, type GeoSpec, type Turn } from "./ask";

function place(name: string, geoid: string, forSpec: string, inSpec: string): GeoSpec {
  return {
    level: "place",
    name,
    geoid,
    for_spec: forSpec,
    in_spec: inSpec,
    dataset: "acs5",
    vintage: 2024,
    codes: {},
  };
}

const springfieldMo = place(
  "Springfield city, Missouri",
  "1600000US2970000",
  "place:70000",
  "state:29",
);
const springfield: AskResponse = {
  answer: "Springfield, Missouri has 169,176 people.",
  urls: [
    "https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B01003_001E,B01003_001M&for=place:70000&in=state:29",
  ],
  requested_years: [2024],
  attempted_years: [2024],
  succeeded_years: [2024],
  failed_years: [],
  omitted_years: [],
  omission_reasons: [],
  legs: [],
  rows: [
    {
      NAME: "Springfield city, Missouri",
      GEO_ID: springfieldMo.geoid,
      B01003_001E: "169176",
      B01003_001M: "88",
    },
  ],
  moe: [{ GEO_ID: springfieldMo.geoid, B01003_001M: "88" }],
  geoid: springfieldMo.geoid,
  universe: "Total population",
  table_id: "B01003",
  alternatives: [
    {
      table_id: "B01001",
      title: "Sex by Age",
      universe: "Total population",
      reason: "age breakdown of the same universe",
    },
  ],
  warnings: [
    {
      code: "ambiguous_place",
      detail: "several Springfields",
      candidates: [springfieldMo],
    },
  ],
  comparisons: [],
  plan: {
    table_id: "B01003",
    variables: ["B01003_001E"],
    dataset: "acs5",
    years: [2024],
    requested_years: [2024],
    geographies: [springfieldMo],
    allow_overlapping_acs5: false,
  },
  chart_unavailable: false,
};


const TID = "11111111-1111-4111-8111-111111111111";
const turn: Turn = {
  question: "Population of Springfield",
  plan: null,
  response: springfield,
  created_at: "2026-10-01T00:00:00Z",
};

function reply(status: number, body: unknown = {}) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

function mockFetch(handler: (path: string, init: RequestInit) => Promise<Response>) {
  const spy = vi.fn((path: string, init: RequestInit) => handler(path, init));
  vi.stubGlobal("fetch", spy);
  return spy;
}

beforeEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe("askInThread", () => {
  it("creates one conversation, then appends every question to it", async () => {
    const spy = mockFetch((path) => (path === "/conversations" ? reply(201, { thread_id: TID }) : reply(200, springfield)));
    await askInThread("a");
    await askInThread("b");
    expect(spy.mock.calls.map(([path]) => path)).toEqual([
      "/conversations",
      `/conversations/${TID}/turns`,
      `/conversations/${TID}/turns`,
    ]);
    expect(localStorage.getItem("cc.thread_id")).toBe(TID);
  });

  it("sends a stable generated X-User-Id on every call", async () => {
    const spy = mockFetch((path) => (path === "/conversations" ? reply(201, { thread_id: TID }) : reply(200, springfield)));
    await askInThread("a");
    const ids = spy.mock.calls.map(([, init]) => (init.headers as Record<string, string>)["X-User-Id"]);
    expect(ids[0]).toMatch(/^[0-9a-f-]{36}$/);
    expect(new Set(ids).size).toBe(1);
    expect(localStorage.getItem("cc.user_id")).toBe(ids[0]);
  });

  it("stores no thread id when create fails", async () => {
    mockFetch(() => reply(503, { detail: "persistence unavailable" }));
    await expect(askInThread("a")).rejects.toThrow();
    expect(localStorage.getItem("cc.thread_id")).toBeNull();
  });

  it("sends the plan to the turns endpoint", async () => {
    localStorage.setItem("cc.thread_id", TID);
    const spy = mockFetch(() => reply(200, springfield));
    await askInThread("a", springfield.plan!);
    expect(JSON.parse(spy.mock.calls[0][1].body as string)).toEqual({ question: "a", plan: springfield.plan });
  });

  it("drops an expired thread id when append returns 404", async () => {
    localStorage.setItem("cc.thread_id", TID);
    mockFetch(() => reply(404, { detail: "conversation not found" }));
    await expect(askInThread("a")).rejects.toThrow();
    expect(localStorage.getItem("cc.thread_id")).toBeNull();
  });
});

describe("loadLatestTurn", () => {
  it("makes no request without a thread id", async () => {
    const spy = mockFetch(() => reply(200));
    expect(await loadLatestTurn()).toBeNull();
    expect(spy).not.toHaveBeenCalled();
  });

  it("returns the latest of several turns", async () => {
    localStorage.setItem("cc.thread_id", TID);
    const older = { ...turn, question: "older" };
    mockFetch(() => reply(200, { turns: [older, turn] }));
    expect((await loadLatestTurn())?.question).toBe(turn.question);
  });

  it("clears the thread id on 404 and returns null", async () => {
    localStorage.setItem("cc.thread_id", TID);
    mockFetch(() => reply(404, { detail: "conversation not found" }));
    expect(await loadLatestTurn()).toBeNull();
    expect(localStorage.getItem("cc.thread_id")).toBeNull();
  });

  it("keeps the thread id on 5xx and on network error", async () => {
    localStorage.setItem("cc.thread_id", TID);
    mockFetch(() => reply(503, { detail: "persistence unavailable" }));
    await expect(loadLatestTurn()).rejects.toThrow();
    mockFetch(() => Promise.reject(new TypeError("down")));
    await expect(loadLatestTurn()).rejects.toThrow();
    expect(localStorage.getItem("cc.thread_id")).toBe(TID);
  });
});

describe("restore in App", () => {
  it("renders a stored turn with the same elements as a freshly asked one", async () => {
    const restored = render(<App loadFn={() => Promise.resolve(turn)} askFn={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "Plan" })).toBeTruthy());
    const restoredHtml = restored.container.innerHTML;
    const restoredText = restored.container.textContent ?? "";
    restored.unmount();

    const user = userEvent.setup({ delay: null });
    const fresh = render(<App loadFn={() => Promise.resolve(null)} askFn={() => Promise.resolve(springfield)} />);
    await user.type(screen.getByLabelText("Question"), turn.question);
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Plan" })).toBeTruthy());
    expect(restoredText).toContain(springfield.urls[0]);
    expect(restoredText).toContain("Active question: " + turn.question);
    expect(restoredText).toContain(springfield.answer);
    expect(fresh.container.innerHTML.replace(/<input[^>]*>/, "")).toBe(restoredHtml.replace(/<input[^>]*>/, ""));
  });

  it.each([true, false])("ignores a restore that settles after an ask (resolves: %s)", async (resolves) => {
    let settle = () => {};
    const late = new Promise<Turn | null>((res, rej) => {
      settle = () => (resolves ? res({ ...turn, question: "stale" }) : rej(new Error("late")));
    });
    const user = userEvent.setup({ delay: null });
    render(<App loadFn={() => late} askFn={() => Promise.resolve(springfield)} />);
    await user.type(screen.getByLabelText("Question"), turn.question);
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Plan" })).toBeTruthy());
    await act(async () => {
      settle();
      await late.catch(() => {});
    });
    expect(screen.getByText("Active question: " + turn.question)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows idle with a non-blocking error when restore fails", async () => {
    render(<App loadFn={() => Promise.reject(new Error("Could not reach the API"))} askFn={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Could not reach"));
    expect(screen.getByText(/Type a question/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Ask" })).toBeTruthy();
  });
});
