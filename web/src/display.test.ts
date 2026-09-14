import { describe, expect, it } from "vitest";
import type { AskResponse } from "./ask";
import { censusFetchFailed, estimatePairs, redactCensusUrl } from "./display";

const harris: AskResponse = {
  answer: "Harris County has 4,838,303 people.",
  url: "https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B01003_001E,B01003_001M&for=county:201&in=state:48",
  rows: [
    {
      NAME: "Harris County, Texas",
      GEO_ID: "0500000US48201",
      B01003_001E: "4838303",
      B01003_001M: "123",
    },
  ],
  moe: [{ GEO_ID: "0500000US48201", NAME: "Harris County, Texas", B01003_001M: "123" }],
  geoid: "0500000US48201",
  universe: "Total population",
  table_id: "B01003",
  alternatives: [{ table_id: "B01001", reason: "related table" }],
  warnings: [],
};

describe("estimatePairs", () => {
  it("pairs each estimate with its matching 90% MOE", () => {
    expect(estimatePairs(harris.rows[0], harris.moe[0])).toEqual([
      { variable: "B01003_001E", estimate: "4838303", moe: "123" },
    ]);
  });

  it("keeps an estimate when the matching MOE is missing", () => {
    expect(estimatePairs({ B19013_001E: "1", GEO_ID: "x" }, { GEO_ID: "x" })).toEqual([
      { variable: "B19013_001E", estimate: "1", moe: null },
    ]);
  });
});

describe("censusFetchFailed", () => {
  it("is true when a URL shipped and Census returned no rows", () => {
    expect(
      censusFetchFailed({
        ...harris,
        rows: [],
        moe: [],
        answer: "The fetch failed.",
      }),
    ).toBe(true);
  });

  it("is false when rows arrived", () => {
    expect(censusFetchFailed(harris)).toBe(false);
  });
});

describe("redactCensusUrl", () => {
  it("strips key= from a Census URL", () => {
    const raw = `${harris.url}&key=secret`;
    expect(redactCensusUrl(raw)).not.toContain("key=");
    expect(redactCensusUrl(raw)).toContain("get=NAME");
  });
});
