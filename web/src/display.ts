import type { AskResponse } from "./ask";

export type PaneState = "idle" | "loading" | "error" | "result";

export type EstimateCell = {
  variable: string;
  estimate: string | null;
  moe: string | null;
};

export type GeographyEstimates = {
  geoid: string;
  name: string;
  pairs: EstimateCell[];
};

export function redactCensusUrl(url: string): string {
  if (!url) {
    return "";
  }
  try {
    const parsed = new URL(url);
    parsed.searchParams.delete("key");
    return parsed.toString();
  } catch {
    return url.replace(/(?:^|&)key=[^&]*/g, "").replace(/\?&/, "?").replace(/\?$/, "");
  }
}

export function censusFetchFailed(response: AskResponse): boolean {
  return Boolean(response.url) && response.rows.length === 0;
}

export function estimatePairs(
  row: Record<string, string | null> | undefined,
  moe: Record<string, string | null> | undefined,
): EstimateCell[] {
  if (!row) {
    return [];
  }
  const margins = moe ?? {};
  return Object.keys(row)
    .filter((key) => key.includes("_") && key.endsWith("E"))
    .map((variable) => ({
      variable,
      estimate: row[variable] ?? null,
      moe: margins[`${variable.slice(0, -1)}M`] ?? null,
    }));
}

export function estimatesByGeography(response: AskResponse): GeographyEstimates[] {
  return response.rows.map((row, index) => ({
    geoid: row.GEO_ID ?? "",
    name: row.NAME ?? "",
    pairs: estimatePairs(row, response.moe[index]),
  }));
}
