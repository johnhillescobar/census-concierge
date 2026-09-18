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
  year: string;
  dataset: string;
  period: string;
  tableId: string;
  pairs: EstimateCell[];
};

const CENSUS_MISSING = new Set([
  "",
  "-999999999",
  "-888888888",
  "-666666666",
  "-555555555",
  "-333333333",
  "-222222222",
]);

export function redactCensusUrl(url: string): string {
  if (!url) {
    return "";
  }
  try {
    const parsed = new URL(url);
    for (const name of [...parsed.searchParams.keys()]) {
      if (name.toLowerCase() === "key") {
        parsed.searchParams.delete(name);
      }
    }
    return parsed.toString();
  } catch {
    return url
      .replace(/([?&])key=[^&]*/gi, "$1")
      .replace(/\?&+/g, "?")
      .replace(/[?&]$/, "");
  }
}

export function formatCensusValue(raw: string | null | undefined): string {
  if (raw == null || CENSUS_MISSING.has(raw)) {
    return "—";
  }
  return raw;
}

export function censusUrls(response: AskResponse): string[] {
  return response.urls.map(redactCensusUrl).filter(Boolean);
}

export function censusFetchFailed(response: AskResponse): boolean {
  return censusUrls(response).length > 0 && response.rows.length === 0;
}

export function censusYearsIncomplete(response: AskResponse): boolean {
  if (censusFetchFailed(response) || censusUrls(response).length === 0) {
    return false;
  }
  return response.failed_years.length > 0 || response.omitted_years.length > 0;
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
    .map((variable) => {
      const raw = margins[`${variable.slice(0, -1)}M`] ?? null;
      return {
        variable,
        estimate: row[variable] ?? null,
        moe: raw == null || CENSUS_MISSING.has(raw) ? null : raw,
      };
    });
}

export function estimatesByGeography(response: AskResponse): GeographyEstimates[] {
  return response.rows.map((row, index) => ({
    geoid: row.GEO_ID ?? "",
    name: row.NAME ?? "",
    year: row.year ?? row.vintage ?? "",
    dataset: row.dataset ?? "",
    period: row.period ?? "",
    tableId: row.table_id ?? "",
    pairs: estimatePairs(row, response.moe[index]),
  }));
}
