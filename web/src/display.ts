import type { AskResponse } from "./ask";

export type PaneState = "idle" | "loading" | "error" | "result";

export type DatasetRow = {
  dataset: string;
  year: string;
  period: string;
  tableId: string;
  variable: string;
  geoid: string;
  name: string;
  estimate: string | null;
  moe: string | null;
  universe: string;
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

export function censusRaw(value: string | null | undefined): string | null {
  if (value == null || CENSUS_MISSING.has(value)) {
    return null;
  }
  return value;
}

export function formatCensusValue(raw: string | null | undefined): string {
  const value = censusRaw(raw);
  return value ?? "—";
}

export function formatCensusNumber(raw: string | null | undefined): string {
  const value = censusRaw(raw);
  if (value == null) {
    return "—";
  }
  if (!/^-?\d+(\.\d+)?$/.test(value)) {
    return value;
  }
  const negative = value.startsWith("-");
  const unsigned = negative ? value.slice(1) : value;
  const [whole, fraction] = unsigned.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${negative ? "-" : ""}${grouped}${fraction != null ? `.${fraction}` : ""}`;
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

export function estimateVariables(row: Record<string, string | null> | undefined): string[] {
  if (!row) {
    return [];
  }
  return Object.keys(row).filter((key) => key.includes("_") && key.endsWith("E"));
}

export function matchingMoe(
  variable: string,
  margins: Record<string, string | null> | undefined,
): string | null {
  if (!variable.endsWith("E") || !margins) {
    return null;
  }
  return censusRaw(margins[`${variable.slice(0, -1)}M`]);
}

export function normalizeActiveDataset(response: AskResponse): DatasetRow[] {
  const dataset: DatasetRow[] = [];
  response.rows.forEach((row, index) => {
    const margins = response.moe[index];
    for (const variable of estimateVariables(row)) {
      dataset.push({
        dataset: row.dataset || "",
        year: row.year || row.vintage || "",
        period: row.period || "",
        tableId: row.table_id || response.table_id || "",
        variable,
        geoid: row.GEO_ID || "",
        name: row.NAME || "",
        estimate: censusRaw(row[variable]),
        moe: matchingMoe(variable, margins),
        universe: response.universe || "",
      });
    }
  });
  return dataset;
}
