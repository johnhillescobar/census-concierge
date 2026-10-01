import type { components } from "../../packages/client/schema";

export type Alternative = components["schemas"]["Alternative"];
export type AskWarning = components["schemas"]["AskWarning"];
export type AskResponse = components["schemas"]["AskResponse"];
export type ChartSpec = components["schemas"]["ChartSpec"];
export type ResultPlan = components["schemas"]["ResultPlan"];
export type Turn = components["schemas"]["Turn"];
export type GeoSpec = components["schemas"]["GeoSpec"];

const PLAN_FIELDS = new Set([
  "table_id",
  "variables",
  "dataset",
  "years",
  "requested_years",
  "geographies",
  "allow_overlapping_acs5",
]);

type DetailItem = { loc?: unknown; msg?: unknown };

export class AskError extends Error {
  readonly status: number;
  readonly field: string;

  constructor(message: string, status = 0, field = "") {
    super(message);
    this.name = "AskError";
    this.status = status;
    this.field = field;
  }
}

export function fieldFromDetail(detail: unknown): string {
  if (!Array.isArray(detail) || detail.length === 0) {
    return "";
  }
  const first = detail[0] as DetailItem;
  const msg = typeof first.msg === "string" ? first.msg : "";
  const loc = Array.isArray(first.loc) ? first.loc.map(String) : [];
  const named = [...loc].reverse().find((part) => PLAN_FIELDS.has(part));
  if (named === "requested_years") {
    return "years";
  }
  if (named === "variables") {
    return "table_id";
  }
  if (named === "allow_overlapping_acs5") {
    return "plan";
  }
  if (named) {
    return named;
  }
  if (/GEOID/i.test(msg)) {
    return "geographies";
  }
  if (/year/i.test(msg)) {
    return "years";
  }
  if (/ZCTA|ACS1 is not published/i.test(msg)) {
    return "dataset";
  }
  if (/variable/i.test(msg)) {
    return "table_id";
  }
  return loc.includes("plan") ? "plan" : "";
}

export function messageFromDetail(detail: unknown): string {
  if (!Array.isArray(detail) || detail.length === 0) {
    return "";
  }
  const first = detail[0] as DetailItem;
  return typeof first.msg === "string" ? first.msg.replace(/^Value error, /i, "") : "";
}

async function call<T>(path: string, init: RequestInit = {}, extra: HeadersInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...extra },
    });
  } catch {
    throw new AskError("Could not reach the API");
  }
  if (!response.ok) {
    let message = `ask failed (${response.status})`;
    let field = "";
    try {
      const body: unknown = await response.json();
      const detail =
        body && typeof body === "object" && "detail" in body
          ? (body as { detail: unknown }).detail
          : undefined;
      const parsed = messageFromDetail(detail);
      if (parsed) {
        message = parsed;
      }
      if (response.status === 422) {
        field = fieldFromDetail(detail);
      }
    } catch {
      /* keep the status message when the body is not JSON */
    }
    if ([404, 409].includes(response.status) && path.startsWith("/conversations/")) {
      localStorage.removeItem("cc.thread_id"); // expired, unknown or full: start fresh next ask
    }
    throw new AskError(message, response.status, field);
  }
  return (await response.json()) as T;
}

export function ask(question: string, plan?: ResultPlan): Promise<AskResponse> {
  return call("/ask", { method: "POST", body: JSON.stringify(plan ? { question, plan } : { question }) });
}

// A bearer secret until slice 8: never displayed, never logged.
function userHeaders(): HeadersInit {
  const id = localStorage.getItem("cc.user_id") ?? crypto.randomUUID();
  localStorage.setItem("cc.user_id", id);
  return { "X-User-Id": id };
}

export async function askInThread(question: string, plan?: ResultPlan): Promise<AskResponse> {
  const headers = userHeaders();
  let threadId = localStorage.getItem("cc.thread_id");
  if (!threadId) {
    threadId = (await call<{ thread_id: string }>("/conversations", { method: "POST" }, headers)).thread_id;
    localStorage.setItem("cc.thread_id", threadId);
  }
  const init = { method: "POST", body: JSON.stringify(plan ? { question, plan } : { question }) };
  return call(`/conversations/${threadId}/turns`, init, headers);
}

// null when there is nothing to restore; throws on network error or 5xx, keeping the thread id.
export async function loadLatestTurn(): Promise<Turn | null> {
  const threadId = localStorage.getItem("cc.thread_id");
  if (!threadId) {
    return null;
  }
  try {
    const found = await call<{ turns: Turn[] }>(`/conversations/${threadId}`, {}, userHeaders());
    return found.turns[found.turns.length - 1] ?? null;
  } catch (cause) {
    if (cause instanceof AskError && cause.status === 404) {
      return null;
    }
    throw cause;
  }
}
