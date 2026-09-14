/** Temporary contract types. CC-27 replaces this module with packages/client. */

export type Alternative = {
  table_id: string;
  reason: string;
};

export type AskWarning = {
  code: string;
  detail: string;
};

export type AskResponse = {
  answer: string;
  url: string;
  rows: Record<string, string | null>[];
  moe: Record<string, string | null>[];
  geoid: string;
  universe: string;
  table_id: string;
  alternatives: Alternative[];
  warnings: AskWarning[];
};

export async function ask(question: string): Promise<AskResponse> {
  const response = await fetch("/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!response.ok) {
    throw new Error(`ask failed (${response.status})`);
  }
  return (await response.json()) as AskResponse;
}
