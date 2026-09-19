import { describe, expect, it } from "vitest";
import type { AskResponse } from "./ask";
import {
  censusFetchFailed,
  censusYearsIncomplete,
  estimatePairs,
  estimatesByGeography,
  formatCensusValue,
  redactCensusUrl,
} from "./display";

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
  comparisons: [],
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

  it("treats a Census sentinel MOE as missing, not as a number", () => {
    expect(
      estimatePairs({ B01003_001E: "10", GEO_ID: "x" }, { GEO_ID: "x", B01003_001M: "-555555555" }),
    ).toEqual([{ variable: "B01003_001E", estimate: "10", moe: null }]);
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

  it("is false when some years succeeded and others failed", () => {
    expect(
      censusFetchFailed({
        ...harris,
        urls: [
          harris.urls[0],
          harris.urls[0].replace("/2024/", "/2019/"),
        ],
        attempted_years: [2019, 2024],
        succeeded_years: [2024],
        failed_years: [2019],
      }),
    ).toBe(false);
  });
});

describe("censusYearsIncomplete", () => {
  it("is true when a year failed but rows arrived", () => {
    expect(
      censusYearsIncomplete({
        ...harris,
        urls: [
          harris.urls[0],
          harris.urls[0].replace("/2024/", "/2019/"),
        ],
        attempted_years: [2019, 2024],
        succeeded_years: [2024],
        failed_years: [2019],
      }),
    ).toBe(true);
  });

  it("is false on a complete one-year fetch", () => {
    expect(censusYearsIncomplete(harris)).toBe(false);
  });

  it("is false when every attempted year failed", () => {
    expect(
      censusYearsIncomplete({
        ...harris,
        rows: [],
        moe: [],
        succeeded_years: [],
        failed_years: [2024],
      }),
    ).toBe(false);
  });
});

describe("redactCensusUrl", () => {
  it("strips key= from a Census URL", () => {
    const raw = `${harris.urls[0]}&key=secret`;
    expect(redactCensusUrl(raw)).not.toContain("key=");
    expect(redactCensusUrl(raw)).toContain("get=NAME");
  });

  it("strips a first-parameter key and an uppercase KEY", () => {
    const first = "https://api.census.gov/data/2024/acs/acs5?key=secret&get=NAME";
    const upper = "https://api.census.gov/data/2024/acs/acs5?get=NAME&KEY=secret";
    expect(redactCensusUrl(first)).not.toMatch(/key=/i);
    expect(redactCensusUrl(first)).toContain("get=NAME");
    expect(redactCensusUrl(upper)).not.toMatch(/key=/i);
    expect(redactCensusUrl(upper)).toContain("get=NAME");
  });

  it("strips key= from a URL the parser rejects", () => {
    const raw = "not-a-url?key=secret&get=NAME";
    expect(redactCensusUrl(raw)).not.toMatch(/key=/i);
    expect(redactCensusUrl(raw)).toContain("get=NAME");
  });
});

describe("formatCensusValue", () => {
  it("renders Census missing sentinels as unavailable", () => {
    expect(formatCensusValue("-555555555")).toBe("—");
    expect(formatCensusValue("-999999999")).toBe("—");
    expect(formatCensusValue(null)).toBe("—");
    expect(formatCensusValue("4838303")).toBe("4838303");
  });

  it("keeps a published MOE of zero", () => {
    expect(formatCensusValue("0")).toBe("0");
  });
});

describe("estimatesByGeography", () => {
  it("keeps one geography on a single-row response", () => {
    expect(estimatesByGeography(harris)).toEqual([
      {
        geoid: "0500000US48201",
        name: "Harris County, Texas",
        year: "",
        dataset: "",
        period: "",
        tableId: "",
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

  it("surfaces dataset, period, and table on each point", () => {
    const series: AskResponse = {
      ...harris,
      rows: [
        {
          ...harris.rows[0],
          year: "2018",
          vintage: "2018",
          dataset: "acs5",
          period: "2014-2018",
          table_id: "B01003",
        },
        {
          ...harris.rows[0],
          year: "2022",
          vintage: "2022",
          dataset: "acs5",
          period: "2018-2022",
          table_id: "B01003",
        },
      ],
      moe: [harris.moe[0], harris.moe[0]],
    };
    expect(estimatesByGeography(series).map((area) => area.period)).toEqual([
      "2014-2018",
      "2018-2022",
    ]);
    expect(estimatesByGeography(series)[0]?.dataset).toBe("acs5");
    expect(estimatesByGeography(series)[0]?.tableId).toBe("B01003");
  });
});
