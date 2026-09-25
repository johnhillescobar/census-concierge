import type { ChartSpec } from "./ask";
import type { DatasetRow } from "./display";

export const CHART_SERIES_MAX = 12;
export const CHART_POINTS_MAX = 500;
export const EMBED_OPTIONS = { actions: false, renderer: "svg" as const };

export type ChartPoint = {
  x: string;
  estimate: number | null;
  low: number | null;
  high: number | null;
  series: string;
  segment: number;
};

export type ChartView =
  | { kind: "empty" }
  | { kind: "table"; message: string }
  | { kind: "error"; message: string }
  | { kind: "spec"; title: string; spec: Record<string, unknown> };

const TABLE_NOTICE = "Too many series or points to chart. Use the table.";
const ERROR_NOTICE = "This chart specification is not supported. The table below is complete.";

function num(raw: string | null): number | null {
  return raw != null && /^-?\d+(\.\d+)?$/.test(raw) ? Number(raw) : null;
}

function yearOf(row: DatasetRow): number | null {
  return row.year && /^\d+$/.test(row.year) ? Number(row.year) : null;
}

function seriesLabel(row: DatasetRow, by: ChartSpec["series_by"]): string {
  if (by === "variable") return row.variable;
  if (by === "geography") return row.name || row.geoid;
  return "Estimate";
}

function xLabel(row: DatasetRow, x: ChartSpec["x"]): string {
  return x === "year" ? row.period || row.year : row.name || row.geoid;
}

function bounds(estimate: number | null, moe: number | null): { low: number | null; high: number | null } {
  return estimate == null || moe == null ? { low: null, high: null } : { low: estimate - moe, high: estimate + moe };
}

function isChartSpec(value: ChartSpec | null | undefined): value is ChartSpec {
  if (value == null || value.y !== "estimate" || value.show_moe !== true) return false;
  return value.type === "line" ? value.x === "year" : value.type === "bar" && value.x === "geography";
}

export function chartPoints(spec: ChartSpec, rows: DatasetRow[]): ChartPoint[] {
  const groups = new Map<string, DatasetRow[]>();
  for (const row of rows) {
    const key = seriesLabel(row, spec.series_by);
    const list = groups.get(key);
    if (list) list.push(row);
    else groups.set(key, [row]);
  }
  const points: ChartPoint[] = [];
  for (const [series, list] of groups) {
    if (spec.type === "line") {
      const byYear = new Map<number, DatasetRow>();
      for (const row of list) {
        const year = yearOf(row);
        if (year != null) byYear.set(year, row);
      }
      const years = [...byYear.keys()].sort((a, b) => a - b);
      if (years.length === 0) continue;
      let segment = 0;
      let open = false;
      for (let year = years[0]; year <= years[years.length - 1]; year += 1) {
        const row = byYear.get(year);
        const estimate = row ? num(row.estimate) : null;
        if (estimate == null) {
          if (open) {
            segment += 1;
            open = false;
          }
          continue;
        }
        points.push({ x: xLabel(row!, spec.x), estimate, series, segment, ...bounds(estimate, num(row!.moe)) });
        open = true;
      }
    } else {
      for (const row of list) {
        const estimate = num(row.estimate);
        points.push({ x: xLabel(row, spec.x), estimate, series, segment: 0, ...bounds(estimate, num(row.moe)) });
      }
    }
  }
  return points;
}

function vegaSpec(spec: ChartSpec, points: ChartPoint[], rows: DatasetRow[]): Record<string, unknown> {
  const series = [...new Set(points.map((point) => point.series))].sort();
  const yTitle = rows.find((row) => row.universe)?.universe || "Estimate";
  const xTitle = spec.x === "year" ? (rows.some((row) => row.period) ? "Period" : "Year") : "Geography";
  const legendTitle = spec.series_by === "variable" ? "Variable" : "Geography";
  return {
    title: spec.title,
    description: spec.title,
    width: "container",
    autosize: { type: "fit", contains: "padding" },
    data: { values: points },
    encoding: {
      x: { field: "x", type: "ordinal", title: xTitle },
      color: {
        field: "series",
        type: "nominal",
        title: legendTitle,
        scale: { domain: series },
        legend: series.length > 1 ? { title: legendTitle } : null,
      },
    },
    layer: [
      {
        mark: spec.type === "line" ? { type: "line", point: true } : { type: "bar" },
        encoding: {
          y: { field: "estimate", type: "quantitative", title: yTitle },
          ...(spec.type === "line" ? { detail: { field: "segment", type: "nominal" } } : {}),
        },
      },
      {
        mark: { type: "errorbar" },
        encoding: { y: { field: "low", type: "quantitative" }, y2: { field: "high" } },
      },
    ],
  };
}

export function chartView(
  spec: ChartSpec | null | undefined,
  rows: DatasetRow[],
  unavailable: boolean,
): ChartView {
  if (unavailable) {
    return { kind: "error", message: "Chart could not be drawn. The table below is complete." };
  }
  if (spec == null) {
    return { kind: "empty" };
  }
  if (!isChartSpec(spec)) {
    return { kind: "error", message: ERROR_NOTICE };
  }
  const series = new Set(rows.map((row) => seriesLabel(row, spec.series_by)));
  if (series.size > CHART_SERIES_MAX || rows.length > CHART_POINTS_MAX) {
    return { kind: "table", message: TABLE_NOTICE };
  }
  const points = chartPoints(spec, rows);
  if (points.length === 0) {
    return { kind: "error", message: ERROR_NOTICE };
  }
  return { kind: "spec", title: spec.title, spec: vegaSpec(spec, points, rows) };
}
