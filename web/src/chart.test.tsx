import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ChartSpec } from "./ask";
import { ResultChart } from "./ResultChart";
import { chartView, EMBED_OPTIONS, type ChartPoint } from "./chart";
import type { DatasetRow } from "./display";

const LINE: ChartSpec = { type: "line", x: "year", y: "estimate", title: "Population", show_moe: true, series_by: null };
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
  return view.kind === "spec" ? (view.spec.data as { values: ChartPoint[] }).values : [];
}

describe("chartView", () => {
  it("maps a line spec onto year/period, estimate, and 90% MOE bounds", () => {
    expect(values(LINE, [row({ year: "2019", period: "2015-2019", estimate: "100", moe: "10" })])).toEqual([
      { x: "2015-2019", estimate: 100, low: 90, high: 110, series: "Estimate", segment: 0 },
    ]);
    const view = chartView(LINE, [row({ year: "2019", period: "2015-2019" })], false);
    expect(view.kind).toBe("spec");
    if (view.kind !== "spec") return;
    const encoding = view.spec.encoding as { x: { title: string }; color: { legend: null } };
    const layer = view.spec.layer as { mark: { type: string }; encoding: { y?: { title: string } } }[];
    expect(JSON.stringify(view.spec)).not.toMatch(/"url"\s*:/);
    expect(view.spec).not.toHaveProperty("signals");
    expect([view.title, encoding.x.title, encoding.color.legend, layer[0]?.mark.type, layer[1]?.mark.type]).toEqual([
      "Population",
      "Period",
      null,
      "line",
      "errorbar",
    ]);
    expect(layer.map((item) => item.encoding.y?.title)).toEqual(["Total population", "Total population"]);
  });

  it("maps a bar spec onto geography categories", () => {
    const points = values(BAR, [
      row({ name: "Springfield", geoid: "m", estimate: "100", moe: "8" }),
      row({ name: "Springfield", geoid: "i", estimate: "200", moe: "12" }),
    ]);
    expect(points.map((point) => [point.x, point.estimate, point.low, point.high]).sort()).toEqual([
      ["Springfield (i)", 200, 188, 212],
      ["Springfield (m)", 100, 92, 108],
    ]);
  });

  it("splits two geography series on a shared year domain", () => {
    const spec: ChartSpec = { ...LINE, title: "B01003" };
    const rows = [
      row({ name: "Dallas", geoid: "d", year: "2022", period: "2022", estimate: "2", moe: "1" }),
      row({ name: "Dallas", geoid: "d", year: "2021", period: "2021", estimate: "1", moe: "1" }),
      row({ name: "Austin", geoid: "a", year: "2021", period: "2021", estimate: "3", moe: "1" }),
      row({ name: "Austin", geoid: "a", year: "2023", period: "2023", estimate: "4", moe: "1" }),
    ];
    const points = values(spec, rows);
    expect([...new Set(points.map((point) => point.series))].sort()).toEqual(["Austin", "Dallas"]);
    const view = chartView(spec, rows, false);
    if (view.kind !== "spec") return;
    const encoding = view.spec.encoding as {
      x: { scale: { domain: string[] }; sort: string[] };
      xOffset: { value: number };
      color: { scale: { domain: string[] }; legend: { title: string } };
    };
    expect(view.title).toBe("Total population — Austin and Dallas");
    expect([view.spec.title, encoding.color.scale.domain, encoding.color.legend.title, encoding.x.scale.domain, encoding.x.sort, encoding.xOffset]).toEqual([
      view.title,
      ["Austin", "Dallas"],
      "Geography",
      ["2021", "2022", "2023"],
      ["2021", "2022", "2023"],
      undefined,
    ]);
    expect(chartView({ ...spec, title: "FY2024 revenue" }, rows, false)).toMatchObject({ kind: "spec", title: "FY2024 revenue" });
  });

  it("does not dodge a multi-geography bar chart, and pins its scale to band so bars align with ticks", () => {
    const rows = [row({ name: "Chicago", geoid: "c1" }), row({ name: "Los Angeles", geoid: "c2" })];
    const view = chartView(BAR, rows, false);
    if (view.kind !== "spec") throw new Error("expected a spec");
    const encoding = view.spec.encoding as { xOffset?: { field?: string }; x: { scale: { type: string } } };
    expect([encoding.xOffset, encoding.x.scale.type]).toEqual([undefined, "band"]);
  });

  it("splits two variable series with stable labels", () => {
    const spec: ChartSpec = { ...BAR, series_by: "variable" };
    const rows = [
      row({ variable: "B01003_001E", name: "Austin", estimate: "10", moe: "1" }),
      row({ variable: "B01001_001E", name: "Austin", estimate: "9", moe: "1" }),
    ];
    expect([...new Set(values(spec, rows).map((point) => point.series))].sort()).toEqual(["B01001_001E", "B01003_001E"]);
    const view = chartView(spec, rows, false);
    if (view.kind === "spec") {
      expect((view.spec.encoding as { xOffset: { field: string } }).xOffset).toEqual({ field: "series" });
    }
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
    expect(values(BAR, [row({ name: "Austin", estimate: null, moe: null })])).toEqual([
      { x: "Austin", estimate: null, low: null, high: null, series: "Estimate", segment: 0 },
    ]);
  });

  it("falls back to the table above 12 series or 500 points", () => {
    const geos = Array.from({ length: 13 }, (_, i) => row({ name: `G${i}`, geoid: String(i) }));
    expect(chartView({ ...BAR, series_by: "geography" }, geos, false)).toMatchObject({ kind: "table", message: /use the table/i });
    expect(chartView(LINE, Array.from({ length: 501 }, (_, i) => row({ year: String(2000 + i), period: String(2000 + i) })), false).kind).toBe(
      "table",
    );
  });

  it("shows a chart error for an invalid spec or a failed model chart", () => {
    expect(chartView({ ...LINE, type: "bar" } as ChartSpec, [row({})], false).kind).toBe("error");
    expect(chartView(null, [row({})], true).kind).toBe("error");
    expect(chartView(null, [row({})], false).kind).toBe("empty");
    expect(chartView(LINE, [row({ geoid: "a" }), row({ name: "Dallas", geoid: "b", variable: "B01001_001E" })], false).kind).toBe("error");
    expect(chartView({ ...LINE, series_by: "variable" }, [row({ geoid: "a", year: "2021", period: "2021" }), row({ name: "Dallas", geoid: "b", year: "2021", period: "2021" })], false).kind).toBe("error");
    const sneaky = { ...LINE, data: { url: "https://example.invalid/chart.json" } } as ChartSpec;
    const view = chartView(sneaky, [row({ year: "2019", period: "2019" })], false);
    expect(view.kind).toBe("spec");
    expect(JSON.stringify(view)).not.toContain("example.invalid");
    expect(JSON.stringify(view)).not.toMatch(/"url"\s*:/);
  });

  it("disables Vega actions so CSV is the only export", async () => {
    expect(EMBED_OPTIONS).toEqual({ actions: false, renderer: "svg" });
    vi.mocked((await import("vega-embed")).default).mockRejectedValueOnce(new Error("vega"));
    render(<ResultChart spec={LINE} rows={[row({ year: "2019", period: "2019" })]} unavailable={false} />);
    await waitFor(() => expect(screen.getByRole("status").textContent).toMatch(/could not be drawn/i));
  });
});
