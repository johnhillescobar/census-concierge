import type { ChartSpec } from "./ask";
import type { DatasetRow } from "./display";

export const CHART_SERIES_MAX = 12;
export const CHART_POINTS_MAX = 500;
export const EMBED_OPTIONS = { actions: false, renderer: "svg" as const };
export const CHART_FAIL = "Chart could not be drawn. The table below is complete.";

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

function geoName(rows: DatasetRow[], row: DatasetRow): string {
  const name = row.name || row.geoid;
  const id = row.geoid || row.name;
  return rows.some((other) => (other.geoid || other.name) !== id && (other.name || other.geoid) === name)
    ? `${name} (${id})`
    : name;
}

function seriesBy(spec: ChartSpec, rows: DatasetRow[]): ChartSpec["series_by"] | false {
  if (spec.series_by) return spec.series_by;
  const geos = new Set(rows.map((row) => row.geoid)).size > 1;
  const vars = new Set(rows.map((row) => row.variable)).size > 1;
  return geos && vars ? false : geos ? "geography" : vars ? "variable" : null;
}

function seriesLabel(row: DatasetRow, by: ChartSpec["series_by"], rows: DatasetRow[]): string {
  return by === "variable" ? row.variable : by === "geography" ? geoName(rows, row) : "Estimate";
}

function xLabel(row: DatasetRow, x: ChartSpec["x"], rows: DatasetRow[]): string {
  return x === "year" ? row.period || row.year : geoName(rows, row);
}

function chartTitle(spec: ChartSpec, rows: DatasetRow[]): string {
  const tableId = rows.find((row) => row.tableId)?.tableId || "";
  const universe = rows.find((row) => row.universe)?.universe || "";
  const raw = spec.title.trim();
  if (raw && raw !== tableId && !/^[BC]\d{5}[A-I]?$/i.test(raw)) return raw;
  const names = [...new Set(rows.map((row) => row.name).filter(Boolean))].sort();
  return universe && names.length > 0 && names.length <= 3
    ? `${universe} — ${names.join(" and ")}`
    : universe || raw || tableId || "Estimate";
}

function xDomain(spec: ChartSpec, rows: DatasetRow[]): string[] {
  const rank = new Map<string, number>();
  for (const row of rows) {
    const label = xLabel(row, spec.x, rows);
    if (!rank.has(label)) rank.set(label, spec.x === "year" ? (yearOf(row) ?? rank.size) : rank.size);
  }
  return [...rank.entries()].sort((a, b) => a[1] - b[1] || a[0].localeCompare(b[0])).map(([k]) => k);
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
    const key = seriesLabel(row, spec.series_by, rows);
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
        if (year == null) continue;
        const prev = byYear.get(year);
        if (prev && (prev.geoid !== row.geoid || prev.variable !== row.variable)) return [];
        byYear.set(year, row);
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
        points.push({ x: xLabel(row!, spec.x, rows), estimate, series, segment, ...bounds(estimate, num(row!.moe)) });
        open = true;
      }
    } else {
      const seen = new Map<string, DatasetRow>();
      for (const row of list) {
        const x = xLabel(row, spec.x, rows);
        const prev = seen.get(x);
        if (prev && (prev.geoid !== row.geoid || prev.variable !== row.variable)) return [];
        seen.set(x, row);
        const estimate = num(row.estimate);
        points.push({ x, estimate, series, segment: 0, ...bounds(estimate, num(row.moe)) });
      }
    }
  }
  return points;
}

function vegaSpec(spec: ChartSpec, points: ChartPoint[], rows: DatasetRow[]): Record<string, unknown> {
  const series = [...new Set(points.map((point) => point.series))].sort();
  const domain = xDomain(spec, rows);
  const yTitle = rows.find((row) => row.universe)?.universe || "Estimate";
  const xTitle = spec.x === "year" ? (rows.some((row) => row.period) ? "Period" : "Year") : "Geography";
  const legendTitle = spec.series_by === "variable" ? "Variable" : "Geography";
  const dodge = spec.type === "bar" && new Set(points.map((point) => point.x)).size < points.length;
  const title = chartTitle(spec, rows);
  return {
    title,
    description: title,
    width: "container",
    autosize: { type: "fit", contains: "padding" },
    data: { values: points },
    encoding: {
      x: { field: "x", type: "ordinal", title: xTitle, sort: domain, scale: { type: "band", domain } },
      ...(dodge ? { xOffset: { field: "series" } } : {}),
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
        encoding: {
          y: { field: "low", type: "quantitative", title: yTitle },
          y2: { field: "high" },
        },
      },
    ],
  };
}

export function chartView(
  spec: ChartSpec | null | undefined,
  rows: DatasetRow[],
  unavailable: boolean,
): ChartView {
  if (unavailable) return { kind: "error", message: CHART_FAIL };
  if (spec == null) return { kind: "empty" };
  if (!isChartSpec(spec)) return { kind: "error", message: ERROR_NOTICE };
  const by = seriesBy(spec, rows);
  if (by === false) return { kind: "error", message: ERROR_NOTICE };
  const drawn = { ...spec, series_by: by };
  const series = new Set(rows.map((row) => seriesLabel(row, by, rows)));
  if (series.size > CHART_SERIES_MAX || rows.length > CHART_POINTS_MAX) {
    return { kind: "table", message: TABLE_NOTICE };
  }
  const points = chartPoints(drawn, rows);
  if (points.length === 0) return { kind: "error", message: ERROR_NOTICE };
  const vega = vegaSpec(drawn, points, rows);
  return { kind: "spec", title: String(vega.title), spec: vega };
}
