import type { components } from "../../packages/client/schema";

export type Alternative = components["schemas"]["Alternative"];
export type AskWarning = components["schemas"]["AskWarning"];
export type AskResponse = components["schemas"]["AskResponse"];
export type ResultPlan = components["schemas"]["ResultPlan"];

export async function ask(question: string, plan?: ResultPlan): Promise<AskResponse> {
  let response: Response;
  try {
    response = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(plan ? { question, plan } : { question }),
    });
  } catch {
    throw new Error("Could not reach the API");
  }
  if (!response.ok) {
    throw new Error(`ask failed (${response.status})`);
  }
  return (await response.json()) as AskResponse;
}
