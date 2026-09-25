import { describe, expect, it } from "vitest";
import type { ChartSpec } from "./ask";
import { chartView, EMBED_OPTIONS, type ChartPoint } from "./chart";
import type { DatasetRow } from "./display";

const LINE: ChartSpec = {
  type: "line",
  x: "year",
  y: "estimate",
  title: "Population",
  show_moe: true,
  series_by: null,
};
const BAR: ChartSpec = { ...LINE, type: "bar", x: "geography", title: "Rent" };

function row(partial: Partial<DatasetRow>): DatasetRow {
  return {
    dataset: "acs5",
    year: "2024",
    period: "2020-2024",
    tableId: "B01003",
    variable: "B01003_001E",
    geoid: "1600000US4805000",
    name: "Austin",
    estimate: "100",
    moe: "10",
    universe: "Total population",
    ...partial,
  };
}

function values(spec: ChartSpec | null | undefined, rows: DatasetRow[], unavailable = false): ChartPoint[] {
  const view = chartView(spec, rows, unavailable);
  expect(view.kind).toBe("spec");
  if (view.kind !== "spec") {
    return [];
  }
  const data = view.spec.data as { values: ChartPoint[] };
  return data.values;
}

describe("chartView", () => {
  it("maps a line spec onto year/period, estimate, and 90% MOE bounds", () => {
    const points = values(LINE, [row({ year: "2019", period: "2015-2019", estimate: "100", moe: "10" })]);
    expect(points).toEqual([
      { x: "2015-2019", estimate: 100, low: 90, high: 110, series: "Estimate", segment: 0 },
    ]);
    const view = chartView(LINE, [row({ year: "2019", period: "2015-2019" })], false);
    expect(view.kind).toBe("spec");
    if (view.kind === "spec") {
      expect(JSON.stringify(view.spec)).not.toMatch(/"url"\s*:/);
      expect(view.spec).not.toHaveProperty("signals");
      expect(view.title).toBe("Population");
      const encoding = view.spec.encoding as { x: { title: string }; color: { legend: null } };
      const layer = view.spec.layer as { mark: { type: string }; encoding: { y?: { title: string } } }[];
      expect(encoding.x.title).toBe("Period");
      expect(encoding.color.legend).toBeNull();
      expect(layer[0]?.mark.type).toBe("line");
      expect(layer[1]?.mark.type).toBe("errorbar");
      expect(layer[0]?.encoding.y?.title).toBe("Total population");
    }
  });

  it("maps a bar spec onto geography categories", () => {
    const points = values(BAR, [
      row({ name: "Austin", geoid: "1600000US4805000", estimate: "100", moe: "8" }),
      row({ name: "Dallas", geoid: "1600000US4819000", estimate: "200", moe: "12" }),
    ]);
    expect(points.map((point) => [point.x, point.estimate, point.low, point.high])).toEqual([
      ["Austin", 100, 92, 108],
      ["Dallas", 200, 188, 212],
    ]);
  });

  it("splits two geography series with stable labels", () => {
    const spec: ChartSpec = { ...LINE, series_by: "geography" };
    const points = values(spec, [
      row({ name: "Austin", geoid: "a", year: "2019", period: "2019", estimate: "1", moe: "1" }),
      row({ name: "Dallas", geoid: "d", year: "2019", period: "2019", estimate: "2", moe: "1" }),
      row({ name: "Austin", geoid: "a", year: "2021", period: "2021", estimate: "3", moe: "1" }),
      row({ name: "Dallas", geoid: "d", year: "2021", period: "2021", estimate: "4", moe: "1" }),
    ]);
    expect([...new Set(points.map((point) => point.series))].sort()).toEqual(["Austin", "Dallas"]);
    const view = chartView(spec, [row({ name: "Austin" }), row({ name: "Dallas", geoid: "d" })], false);
    if (view.kind === "spec") {
      const color = (view.spec.encoding as { color: { scale: { domain: string[] }; legend: { title: string } } })
        .color;
      expect(color.scale.domain).toEqual(["Austin", "Dallas"]);
      expect(color.legend.title).toBe("Geography");
    }
  });

  it("splits two variable series with stable labels", () => {
    const spec: ChartSpec = { ...BAR, series_by: "variable" };
    const points = values(spec, [
      row({ variable: "B01003_001E", name: "Austin", estimate: "10", moe: "1" }),
      row({ variable: "B01001_001E", name: "Austin", estimate: "9", moe: "1" }),
    ]);
    expect([...new Set(points.map((point) => point.series))].sort()).toEqual(["B01001_001E", "B01003_001E"]);
  });

  it("does not interpolate a missing year or a Census sentinel", () => {
    const points = values(LINE, [
      row({ year: "2019", period: "2019", estimate: "100", moe: "10" }),
      row({ year: "2020", period: "2020", estimate: null, moe: null }),
      row({ year: "2021", period: "2021", estimate: "120", moe: "10" }),
    ]);
    expect(points.map((point) => [point.x, point.estimate, point.segment])).toEqual([
      ["2019", 100, 0],
      ["2021", 120, 1],
    ]);
    expect(points.some((point) => point.estimate === 0)).toBe(false);
  });

  it("keeps a bar category with a missing estimate as null, not zero", () => {
    const points = values(BAR, [row({ name: "Austin", estimate: null, moe: null })]);
    expect(points).toEqual([
      { x: "Austin", estimate: null, low: null, high: null, series: "Estimate", segment: 0 },
    ]);
  });

  it("falls back to the table above 12 series or 500 points", () => {
    const geos = Array.from({ length: 13 }, (_, i) => row({ name: `G${i}`, geoid: String(i) }));
    expect(chartView({ ...BAR, series_by: "geography" }, geos, false)).toMatchObject({
      kind: "table",
      message: /use the table/i,
    });
    const many = Array.from({ length: 501 }, (_, i) => row({ year: String(2000 + i), period: String(2000 + i) }));
    expect(chartView(LINE, many, false).kind).toBe("table");
  });

  it("shows a chart error for an invalid spec or a failed model chart", () => {
    expect(chartView({ ...LINE, type: "bar" } as ChartSpec, [row({})], false).kind).toBe("error");
    expect(chartView(null, [row({})], true).kind).toBe("error");
    expect(chartView(null, [row({})], false).kind).toBe("empty");
    const sneaky = { ...LINE, data: { url: "https://example.invalid/chart.json" } } as ChartSpec;
    const view = chartView(sneaky, [row({ year: "2019", period: "2019" })], false);
    expect(view.kind).toBe("spec");
    expect(JSON.stringify(view)).not.toContain("example.invalid");
    expect(JSON.stringify(view)).not.toMatch(/"url"\s*:/);
  });

  it("disables Vega actions so CSV is the only export", () => {
    expect(EMBED_OPTIONS).toEqual({ actions: false, renderer: "svg" });
  });
});
