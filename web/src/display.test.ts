import { describe, expect, it } from "vitest";
import type { AskResponse } from "./ask";
import { censusFetchFailed, estimatePairs, estimatesByGeography, redactCensusUrl } from "./display";

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

describe("estimatesByGeography", () => {
  it("keeps one geography on a single-row response", () => {
    expect(estimatesByGeography(harris)).toEqual([
      {
        geoid: "0500000US48201",
        name: "Harris County, Texas",
        pairs: [{ variable: "B01003_001E", estimate: "4838303", moe: "123" }],
      },
    ]);
  });

  it("does not collapse several geographies onto the first row", () => {
    const oregon: AskResponse = {
      ...harris,
      geoid: "",
      rows: [
        {
          NAME: "Baker County, Oregon",
          GEO_ID: "0500000US41001",
          B01003_001E: "16668",
          B01003_001M: "24",
        },
        {
          NAME: "Benton County, Oregon",
          GEO_ID: "0500000US41003",
          B01003_001E: "95184",
          B01003_001M: "51",
        },
      ],
      moe: [
        { GEO_ID: "0500000US41001", NAME: "Baker County, Oregon", B01003_001M: "24" },
        { GEO_ID: "0500000US41003", NAME: "Benton County, Oregon", B01003_001M: "51" },
      ],
    };
    const areas = estimatesByGeography(oregon);
    expect(areas).toHaveLength(2);
    expect(areas.map((area) => area.geoid)).toEqual(["0500000US41001", "0500000US41003"]);
    expect(areas.map((area) => area.pairs[0]?.estimate)).toEqual(["16668", "95184"]);
  });
});
