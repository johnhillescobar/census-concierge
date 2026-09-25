import { describe, expect, it } from "vitest";
import type { AskResponse, GeoSpec } from "./ask";
import {
  draftFromPlan,
  geographyChoices,
  omittedYears,
  parseYearList,
  planFromDraft,
  tableOverride,
} from "./plan";

function place(name: string, geoid: string, forSpec: string, inSpec: string): GeoSpec {
  return {
    level: "place",
    name,
    geoid,
    for_spec: forSpec,
    in_spec: inSpec,
    dataset: "acs5",
    vintage: 2024,
    codes: {},
  };
}

const springfieldMo = place(
  "Springfield city, Missouri",
  "1600000US2970000",
  "place:70000",
  "state:29",
);
const springfieldIl = place(
  "Springfield city, Illinois",
  "1600000US1772000",
  "place:72000",
  "state:17",
);

const result: AskResponse = {
  answer: "Springfield, Missouri has people.",
  urls: [
    "https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B01003_001E,B01003_001M&for=place:70000&in=state:29",
  ],
  requested_years: [2017, 2018, 2019, 2020, 2021, 2022, 2023],
  attempted_years: [2017, 2022],
  succeeded_years: [2017, 2022],
  failed_years: [],
  omitted_years: [2018, 2019, 2020, 2021, 2023],
  omission_reasons: [],
  legs: [],
  rows: [],
  moe: [],
  geoid: springfieldMo.geoid,
  universe: "Total population",
  table_id: "B01003",
  alternatives: [
    {
      table_id: "B01001",
      title: "Sex by Age",
      universe: "Total population",
      reason: "age breakdown of the same universe",
    },
  ],
  warnings: [
    {
      code: "ambiguous_place",
      detail: "several Springfields",
      candidates: [springfieldMo, springfieldIl],
    },
  ],
  comparisons: [],
  plan: {
    table_id: "B01003",
    variables: ["B01003_001E"],
    dataset: "acs5",
    years: [2017, 2022],
    requested_years: [2017, 2018, 2019, 2020, 2021, 2022, 2023],
    geographies: [springfieldMo],
    allow_overlapping_acs5: false,
  },
  chart_unavailable: false,
};

describe("parseYearList", () => {
  it("accepts comma lists and expands a closed range", () => {
    expect(parseYearList("2019, 2024")).toEqual([2019, 2024]);
    expect(parseYearList("2017-2019")).toEqual([2017, 2018, 2019]);
  });

  it("rejects tokens that are not years", () => {
    expect(parseYearList("2024 and later")).toBeNull();
  });

  it("rejects a blank years field", () => {
    expect(parseYearList("")).toBeNull();
    expect(parseYearList("  ")).toBeNull();
  });
});

describe("plan draft", () => {
  it("initializes requested years from the plan, not the destaggered fetch", () => {
    const draft = draftFromPlan(result);
    expect(draft.requestedYears).toBe("2017, 2018, 2019, 2020, 2021, 2022, 2023");
    expect(draft.geoids).toEqual([springfieldMo.geoid]);
    expect(omittedYears(result)).toEqual([2018, 2019, 2020, 2021, 2023]);
  });

  it("offers returned geos plus warning candidates, keyed by GEOID", () => {
    const choices = geographyChoices(result);
    expect(choices.map((geo) => geo.geoid)).toEqual([springfieldMo.geoid, springfieldIl.geoid]);
  });

  it("builds an override from selected GEOIDs, never from typed for/in", () => {
    const plan = planFromDraft(
      result,
      {
        tableId: "B19013",
        dataset: "acs5",
        requestedYears: "2019, 2024",
        geoids: [springfieldIl.geoid],
        allowOverlapping: true,
      },
      [2019, 2024],
    );
    expect(plan.table_id).toBe("B19013");
    expect(plan.variables).toEqual([]);
    expect(plan.requested_years).toEqual([2019, 2024]);
    expect(plan.years).toEqual([2019, 2024]);
    expect(plan.allow_overlapping_acs5).toBe(true);
    expect(plan.geographies).toEqual([springfieldIl]);
    expect(plan.geographies?.[0]?.for_spec).toBe("place:72000");
  });

  it("drops estimate IDs that belong to a previous table", () => {
    const plan = tableOverride(result.plan, "B01001");
    expect(plan.table_id).toBe("B01001");
    expect(plan.variables).toEqual([]);
    expect(plan.geographies).toEqual([springfieldMo]);
  });
});
