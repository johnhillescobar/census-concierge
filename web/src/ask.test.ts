import { afterEach, describe, expect, it, vi } from "vitest";
import { ask, AskError, type AskResponse } from "./ask";

const harris: AskResponse = {
  answer: "Harris County has 4,838,303 people.",
  urls: [
    "https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B01003_001E,B01003_001M&for=county:201&in=state:48",
  ],
  requested_years: [2024],
  attempted_years: [2024],
  succeeded_years: [2024],
  failed_years: [],
  omitted_years: [],
  omission_reasons: [],
  legs: [],
  rows: [{ NAME: "Harris County, Texas", GEO_ID: "0500000US48201", B01003_001E: "4838303" }],
  moe: [{ B01003_001M: "123" }],
  geoid: "0500000US48201",
  universe: "Total population",
  table_id: "B01003",
  alternatives: [],
  warnings: [],
  comparisons: [],
  plan: {
    table_id: "B01003",
    variables: ["B01003_001E"],
    dataset: "acs5",
    years: [2024],
    requested_years: [2024],
    geographies: [],
    allow_overlapping_acs5: false,
  },
  chart_unavailable: false,
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ask", () => {
  it("POSTs the question as JSON to /ask", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => harris,
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(ask("population of Harris County")).resolves.toEqual(harris);
    expect(fetchMock).toHaveBeenCalledWith("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: "population of Harris County" }),
    });
  });

  it("POSTs an optional plan override beside the question", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => harris,
    });
    vi.stubGlobal("fetch", fetchMock);
    await ask("population of Harris County", harris.plan);
    expect(fetchMock).toHaveBeenCalledWith("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: "population of Harris County", plan: harris.plan }),
    });
  });

  it("throws on a non-2xx response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
      }),
    );
    await expect(ask("population of Harris County")).rejects.toThrow("ask failed (500)");
  });

  it("throws a network error when fetch itself fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(ask("population of Harris County")).rejects.toThrow("Could not reach the API");
  });

  it("surfaces a 422 as a field-specific AskError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({
          detail: [
            {
              type: "value_error",
              loc: ["body", "plan", "table_id"],
              msg: "Value error, invalid table_id override",
            },
          ],
        }),
      }),
    );
    const error = await ask("median household income", harris.plan).catch((cause) => cause);
    expect(error).toBeInstanceOf(AskError);
    expect(error.message).toBe("invalid table_id override");
    expect(error.status).toBe(422);
    expect(error.field).toBe("table_id");
  });

  it("maps a GEOID 422 onto geographies even when loc is only body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({
          detail: [
            {
              loc: ["body"],
              msg: "Value error, geography override requires an executable GEOID",
            },
          ],
        }),
      }),
    );
    const error = await ask("population of Harris County", harris.plan).catch((cause) => cause);
    expect(error.field).toBe("geographies");
    expect(error.message).toMatch(/GEOID/i);
  });
});
