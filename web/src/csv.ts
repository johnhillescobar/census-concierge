import type { DatasetRow } from "./display";

export const CSV_HEADERS = [
  "dataset", "vintage", "period", "table_id", "variable", "GEO_ID", "NAME", "estimate", "moe", "universe",
] as const;

function csvField(value: string): string {
  return /[",\r\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

function csvRow(row: DatasetRow): string {
  return [row.dataset, row.year, row.period, row.tableId, row.variable, row.geoid, row.name, row.estimate ?? "", row.moe ?? "", row.universe]
    .map(csvField)
    .join(",");
}

export function rowsToCsv(rows: DatasetRow[]): string {
  return [CSV_HEADERS.join(","), ...rows.map(csvRow)].map((line) => `${line}\r\n`).join("");
}

export function csvFilename(tableId: string, dataset: string, vintage: string): string {
  const clean = (value: string) => value.replace(/[^A-Za-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "") || "export";
  return `${[tableId, dataset, vintage].map(clean).join("-")}.csv`;
}

export function downloadCsv(filename: string, csv: string): void {
  const url = URL.createObjectURL(new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" }));
  const anchor = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(anchor).click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
