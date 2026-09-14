import { afterEach, describe, expect, it, vi } from "vitest";
import { ask, type AskResponse } from "./ask";

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
  legs: [],
  rows: [{ NAME: "Harris County, Texas", GEO_ID: "0500000US48201", B01003_001E: "4838303" }],
  moe: [{ B01003_001M: "123" }],
  geoid: "0500000US48201",
  universe: "Total population",
  table_id: "B01003",
  alternatives: [],
  warnings: [],
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
});
