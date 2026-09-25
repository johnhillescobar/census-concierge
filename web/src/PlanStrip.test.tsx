import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { AskResponse, GeoSpec } from "./ask";
import { PlanStrip } from "./PlanStrip";

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
  answer: "Prose that names B99999 in Alaska.",
  urls: ["https://api.census.gov/data/2024/acs/acs5"],
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
    { code: "ambiguous_place", detail: "several Springfields", candidates: [springfieldMo, springfieldIl] },
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

describe("PlanStrip", () => {
  it("renders the returned plan, not answer prose", () => {
    render(
      <PlanStrip result={result} busy={false} error="" field="" onApply={async () => true} onClearError={() => undefined} />,
    );
    expect(screen.getByRole("heading", { name: "Plan" })).toBeTruthy();
    expect(screen.getByText("acs5")).toBeTruthy();
    expect(screen.getByText(/requested 2017, 2018, 2019, 2020, 2021, 2022, 2023/)).toBeTruthy();
    expect(screen.getByText(/fetched 2017, 2022/)).toBeTruthy();
    expect(screen.getByText(/omitted 2018, 2019, 2020, 2021, 2023/)).toBeTruthy();
    expect(screen.getByText("B01003")).toBeTruthy();
    expect(screen.getByText(/Springfield city, Missouri \(1600000US2970000\)/)).toBeTruthy();
    expect(screen.getByText("not allowed")).toBeTruthy();
    expect(screen.queryByText(/B99999|Alaska/)).toBeNull();
    expect(screen.getByRole("button", { name: "B01001" })).toBeTruthy();
    expect(screen.getByText("Sex by Age")).toBeTruthy();
    expect(screen.getByText("age breakdown of the same universe")).toBeTruthy();
  });

  it("enters edit mode, restores the draft on cancel, and returns focus to the strip", async () => {
    const user = userEvent.setup({ delay: null });
    const onApply = vi.fn(async () => true);
    render(
      <PlanStrip result={result} busy={false} error="" field="" onApply={onApply} onClearError={() => undefined} />,
    );
    await user.click(screen.getByRole("button", { name: "Edit plan" }));
    expect(document.activeElement).toBe(screen.getByLabelText("Table"));
    await user.clear(screen.getByLabelText("Table"));
    await user.type(screen.getByLabelText("Table"), "NOPE");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onApply).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Table")).toBeNull();
    expect(screen.getByText("B01003")).toBeTruthy();
    await waitFor(() => expect(document.activeElement).toBe(document.querySelector(".plan-strip")));
  });

  it("does not offer a for/in text box", async () => {
    const user = userEvent.setup({ delay: null });
    render(
      <PlanStrip result={result} busy={false} error="" field="" onApply={async () => true} onClearError={() => undefined} />,
    );
    await user.click(screen.getByRole("button", { name: "Edit plan" }));
    expect(screen.queryByLabelText(/for=/i)).toBeNull();
    expect(screen.queryByRole("textbox", { name: /for|in clause/i })).toBeNull();
    expect(screen.getByLabelText(/Springfield city, Illinois/)).toBeTruthy();
  });
});
