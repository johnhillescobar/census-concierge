import { describe, expect, it } from "vitest";
import type { AskResponse } from "./ask";
import {
  censusFetchFailed,
  censusRaw,
  censusYearsIncomplete,
  formatCensusNumber,
  formatCensusValue,
  matchingMoe,
  normalizeActiveDataset,
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
      dataset: "acs5",
      year: "2024",
      vintage: "2024",
      period: "2020-2024",
      table_id: "B01003",
    },
  ],
  moe: [{ GEO_ID: "0500000US48201", NAME: "Harris County, Texas", B01003_001M: "123" }],
  geoid: "0500000US48201",
  universe: "Total population",
  table_id: "B01003",
  alternatives: [{ table_id: "B01001", reason: "related table" }],
  warnings: [],
  comparisons: [],
  chart_unavailable: false,
};

describe("matchingMoe", () => {
  it("pairs an estimate with its exact 90% M suffix on the same margins object", () => {
    expect(matchingMoe("B01003_001E", harris.moe[0])).toBe("123");
  });

  it("keeps an estimate when the matching MOE key is absent", () => {
    expect(matchingMoe("B19013_001E", { GEO_ID: "x" })).toBeNull();
  });

  it("treats a Census sentinel MOE as missing, not as a number", () => {
    expect(matchingMoe("B01003_001E", { B01003_001M: "-555555555" })).toBeNull();
  });

  it("does not borrow an M value from a different variable", () => {
    expect(
      matchingMoe("B19013_002E", { B19013_001M: "9", B19013_002M: "-666666666" }),
    ).toBeNull();
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
        urls: [harris.urls[0], harris.urls[0].replace("/2024/", "/2019/")],
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
        urls: [harris.urls[0], harris.urls[0].replace("/2024/", "/2019/")],
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

describe("formatCensusNumber", () => {
  it("groups digits for display without changing the stored raw value", () => {
    expect(formatCensusNumber("4838303")).toBe("4,838,303");
    expect(censusRaw("4838303")).toBe("4838303");
  });

  it("renders sentinels as unavailable, not as large negatives or zero", () => {
    expect(formatCensusNumber("-555555555")).toBe("—");
    expect(formatCensusNumber(null)).toBe("—");
    expect(formatCensusNumber("0")).toBe("0");
  });
});

describe("normalizeActiveDataset", () => {
  it("emits one table row for a one-row scalar using the same model as a series", () => {
    expect(normalizeActiveDataset(harris)).toEqual([
      {
        dataset: "acs5",
        year: "2024",
        period: "2020-2024",
        tableId: "B01003",
        variable: "B01003_001E",
        geoid: "0500000US48201",
        name: "Harris County, Texas",
        estimate: "4838303",
        moe: "123",
        universe: "Total population",
      },
    ]);
  });

  it("does not collapse several geographies onto the first Census row", () => {
    const oregon: AskResponse = {
      ...harris,
      geoid: "",
      universe: "Households",
      table_id: "B19013",
      rows: [
        {
          NAME: "Baker County, Oregon",
          GEO_ID: "0500000US41001",
          B19013_001E: "52000",
          dataset: "acs5",
          year: "2024",
          vintage: "2024",
          period: "2020-2024",
          table_id: "B19013",
        },
        {
          NAME: "Benton County, Oregon",
          GEO_ID: "0500000US41003",
          B19013_001E: "71000",
          dataset: "acs5",
          year: "2024",
          vintage: "2024",
          period: "2020-2024",
          table_id: "B19013",
        },
      ],
      moe: [
        { GEO_ID: "0500000US41001", B19013_001M: "2400" },
        { GEO_ID: "0500000US41003", B19013_001M: "3100" },
      ],
    };
    const rows = normalizeActiveDataset(oregon);
    expect(rows).toHaveLength(2);
    expect(rows.map((row) => row.geoid)).toEqual(["0500000US41001", "0500000US41003"]);
    expect(rows.map((row) => row.estimate)).toEqual(["52000", "71000"]);
    expect(rows.map((row) => row.moe)).toEqual(["2400", "3100"]);
    expect(rows.map((row) => row.variable)).toEqual(["B19013_001E", "B19013_001E"]);
  });

  it("emits a row for every estimate variable on every geography", () => {
    const mixed: AskResponse = {
      ...harris,
      geoid: "",
      rows: [
        {
          NAME: "Baker County, Oregon",
          GEO_ID: "0500000US41001",
          B01001_001E: "16668",
          B01001_002E: "8401",
        },
        {
          NAME: "Benton County, Oregon",
          GEO_ID: "0500000US41003",
          B01001_001E: "95184",
          B01001_002E: "47012",
        },
      ],
      moe: [
        { B01001_001M: "24", B01001_002M: "18" },
        { B01001_001M: "51", B01001_002M: "33" },
      ],
    };
    const rows = normalizeActiveDataset(mixed);
    expect(rows.map((row) => `${row.geoid}:${row.variable}:${row.estimate}`)).toEqual([
      "0500000US41001:B01001_001E:16668",
      "0500000US41001:B01001_002E:8401",
      "0500000US41003:B01001_001E:95184",
      "0500000US41003:B01001_002E:47012",
    ]);
  });

  it("keeps dataset, period, and table on each series point from that row", () => {
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
    expect(normalizeActiveDataset(series).map((row) => row.period)).toEqual([
      "2014-2018",
      "2018-2022",
    ]);
    expect(normalizeActiveDataset(series).map((row) => row.year)).toEqual(["2018", "2022"]);
    expect(normalizeActiveDataset(series)[0]?.dataset).toBe("acs5");
    expect(normalizeActiveDataset(series)[0]?.tableId).toBe("B01003");
  });

  it("keeps ACS1 period labels as the year, distinct from ACS5 windows", () => {
    const acs1: AskResponse = {
      ...harris,
      rows: [
        { ...harris.rows[0], dataset: "acs1", year: "2023", vintage: "2023", period: "2023" },
      ],
    };
    expect(normalizeActiveDataset(acs1)[0]).toMatchObject({
      dataset: "acs1",
      year: "2023",
      period: "2023",
    });
  });

  it("does not infer year, dataset, or period from a URL when the row omits them", () => {
    const bare: AskResponse = {
      ...harris,
      rows: [
        {
          NAME: "Harris County, Texas",
          GEO_ID: "0500000US48201",
          B01003_001E: "4838303",
        },
      ],
    };
    expect(normalizeActiveDataset(bare)[0]).toMatchObject({
      dataset: "",
      year: "",
      period: "",
      estimate: "4838303",
    });
  });

  it("does not borrow a missing MOE from another row", () => {
    const shortMoe: AskResponse = {
      ...harris,
      geoid: "",
      rows: [
        { NAME: "Baker County, Oregon", GEO_ID: "0500000US41001", B19013_001E: "52000" },
        { NAME: "Benton County, Oregon", GEO_ID: "0500000US41003", B19013_001E: "71000" },
      ],
      moe: [{ GEO_ID: "0500000US41001", B19013_001M: "2400" }],
    };
    const rows = normalizeActiveDataset(shortMoe);
    expect(rows[0]?.moe).toBe("2400");
    expect(formatCensusNumber(rows[0]?.moe)).toBe("2,400");
    expect(rows[1]?.moe).toBeNull();
    expect(formatCensusNumber(rows[1]?.moe)).toBe("—");
    expect(formatCensusNumber(rows[1]?.moe)).not.toBe("0");
    expect(rows[1]?.estimate).toBe("71000");
  });

  it("stores Census sentinels as null so they are not chart points or zeroes", () => {
    const sentinels: AskResponse = {
      ...harris,
      rows: [
        {
          ...harris.rows[0],
          B01003_001E: "-999999999",
        },
      ],
      moe: [{ GEO_ID: "0500000US48201", B01003_001M: "-555555555" }],
    };
    expect(normalizeActiveDataset(sentinels)[0]).toMatchObject({
      estimate: null,
      moe: null,
    });
  });

  it("returns no dataset rows when the fetch is empty", () => {
    expect(normalizeActiveDataset({ ...harris, rows: [], moe: [] })).toEqual([]);
  });
});
