import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { AskError, type AskResponse, type GeoSpec, type ResultPlan } from "./ask";

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

const springfield: AskResponse = {
  answer: "Springfield, Missouri has 169,176 people.",
  urls: [
    "https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B01003_001E,B01003_001M&for=place:70000&in=state:29",
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
      NAME: "Springfield city, Missouri",
      GEO_ID: springfieldMo.geoid,
      B01003_001E: "169176",
      B01003_001M: "88",
    },
  ],
  moe: [{ GEO_ID: springfieldMo.geoid, B01003_001M: "88" }],
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
    years: [2024],
    requested_years: [2024],
    geographies: [springfieldMo],
    allow_overlapping_acs5: false,
  },
  chart_unavailable: false,
};

function withPlan(plan: Partial<ResultPlan>, extra: Partial<AskResponse> = {}): AskResponse {
  return {
    ...springfield,
    ...extra,
    plan: { ...springfield.plan, ...plan },
  };
}

async function askFirst(askFn: (question: string, plan?: ResultPlan) => Promise<AskResponse>) {
  const user = userEvent.setup({ delay: null });
  render(<App askFn={askFn} />);
  await user.type(screen.getByLabelText("Question"), "Population of Springfield");
  await user.click(screen.getByRole("button", { name: "Ask" }));
  await waitFor(() => expect(screen.getByRole("heading", { name: "Plan" })).toBeTruthy());
  return user;
}

describe("plan refinement", () => {
  it("posts a table edit with the original question, not rewritten prompt text", async () => {
    const updated = withPlan({ table_id: "B19013", variables: ["B19013_001E"] }, { table_id: "B19013" });
    const askFn = vi
      .fn<(question: string, plan?: ResultPlan) => Promise<AskResponse>>()
      .mockResolvedValueOnce(springfield)
      .mockResolvedValueOnce(updated);
    const user = await askFirst(askFn);
    await user.click(screen.getByRole("button", { name: "Edit plan" }));
    const table = screen.getByLabelText("Table");
    await user.clear(table);
    await user.type(table, "B19013");
    await user.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(askFn).toHaveBeenCalledTimes(2));
    expect(askFn.mock.calls[1]?.[0]).toBe("Population of Springfield");
    expect(askFn.mock.calls[1]?.[1]).toEqual(
      expect.objectContaining({ table_id: "B19013", requested_years: [2024] }),
    );
    expect(document.querySelector(".plan-summary")?.textContent).toContain("B19013");
  });

  it("posts a geography pick from returned candidates", async () => {
    const updated = withPlan({ geographies: [springfieldIl] }, { geoid: springfieldIl.geoid });
    const askFn = vi
      .fn<(question: string, plan?: ResultPlan) => Promise<AskResponse>>()
      .mockResolvedValueOnce(springfield)
      .mockResolvedValueOnce(updated);
    const user = await askFirst(askFn);
    await user.click(screen.getByRole("button", { name: "Edit plan" }));
    await user.click(screen.getByLabelText(/Springfield city, Missouri/));
    await user.click(screen.getByLabelText(/Springfield city, Illinois/));
    await user.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(askFn).toHaveBeenCalledTimes(2));
    const plan = askFn.mock.calls[1]?.[1];
    expect(plan?.geographies?.map((geo) => geo.geoid)).toEqual([springfieldIl.geoid]);
  });

  it("posts dataset, year list, and overlapping-ACS5 together", async () => {
    const updated = withPlan(
      {
        dataset: "acs1",
        years: [2017, 2018, 2019],
        requested_years: [2017, 2018, 2019],
        allow_overlapping_acs5: true,
      },
      { warnings: [{ code: "overlapping_vintage", detail: "ACS5 periods share sample years" }] },
    );
    const askFn = vi
      .fn<(question: string, plan?: ResultPlan) => Promise<AskResponse>>()
      .mockResolvedValueOnce(springfield)
      .mockResolvedValueOnce(updated);
    const user = await askFirst(askFn);
    await user.click(screen.getByRole("button", { name: "Edit plan" }));
    await user.selectOptions(screen.getByLabelText("Dataset"), "acs1");
    const years = screen.getByLabelText("Requested years");
    await user.clear(years);
    await user.type(years, "2017-2019");
    await user.click(screen.getByLabelText("Allow consecutive ACS 5-year periods"));
    await user.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(askFn).toHaveBeenCalledTimes(2));
    expect(askFn.mock.calls[1]?.[1]).toEqual(
      expect.objectContaining({
        dataset: "acs1",
        requested_years: [2017, 2018, 2019],
        allow_overlapping_acs5: true,
      }),
    );
    expect(screen.getByText("acs1")).toBeTruthy();
    expect(screen.getByText(/overlapping_vintage/)).toBeTruthy();
  });

  it("selecting an alternative overrides table_id without retyping", async () => {
    const updated = withPlan({ table_id: "B01001", variables: ["B01001_001E"] }, { table_id: "B01001" });
    const askFn = vi
      .fn<(question: string, plan?: ResultPlan) => Promise<AskResponse>>()
      .mockResolvedValueOnce(springfield)
      .mockResolvedValueOnce(updated);
    const user = await askFirst(askFn);
    await user.click(screen.getByRole("button", { name: /^B01001/ }));
    await waitFor(() => expect(askFn).toHaveBeenCalledTimes(2));
    expect(askFn.mock.calls[1]?.[0]).toBe("Population of Springfield");
    expect(askFn.mock.calls[1]?.[1]).toEqual(expect.objectContaining({ table_id: "B01001", variables: [] }));
    expect(document.querySelector(".plan-summary")?.textContent).toContain("B01001");
  });

  it("keeps the prior table visible while a refinement is in flight", async () => {
    let finish: (value: AskResponse) => void = () => undefined;
    const askFn = vi
      .fn<(question: string, plan?: ResultPlan) => Promise<AskResponse>>()
      .mockResolvedValueOnce(springfield)
      .mockImplementationOnce(
        () =>
          new Promise<AskResponse>((resolve) => {
            finish = resolve;
          }),
      );
    const user = await askFirst(askFn);
    await user.click(screen.getByRole("button", { name: /^B01001/ }));
    expect(document.querySelector(".pane")?.getAttribute("data-state")).toBe("loading");
    expect(document.querySelector(".census-url")?.textContent).toContain("B01003_001E");
    expect(screen.getByRole("cell", { name: "169,176" })).toBeTruthy();
    expect(screen.getByText(/several Springfields/)).toBeTruthy();
    finish(withPlan({ table_id: "B01001" }, { table_id: "B01001" }));
    await waitFor(() => expect(document.querySelector(".plan-summary")?.textContent).toContain("B01001"));
  });

  it("keeps the prior result when the override is rejected and shows the field error", async () => {
    const askFn = vi
      .fn<(question: string, plan?: ResultPlan) => Promise<AskResponse>>()
      .mockResolvedValueOnce(springfield)
      .mockRejectedValueOnce(new AskError("invalid table_id override", 422, "table_id"));
    const user = await askFirst(askFn);
    await user.click(screen.getByRole("button", { name: "Edit plan" }));
    await user.clear(screen.getByLabelText("Table"));
    await user.type(screen.getByLabelText("Table"), "NOPE");
    await user.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("invalid table_id override"));
    expect(screen.getByLabelText("Table").getAttribute("aria-invalid")).toBe("true");
    expect(document.activeElement).toBe(screen.getByLabelText("Table"));
    expect(document.querySelector(".census-url")?.textContent).toContain("B01003_001E");
    expect(screen.getByRole("cell", { name: "169,176" })).toBeTruthy();
    expect(screen.getByLabelText("Table")).toBeTruthy();
  });

  it("keeps the prior result when the refinement cannot reach the API", async () => {
    const askFn = vi
      .fn<(question: string, plan?: ResultPlan) => Promise<AskResponse>>()
      .mockResolvedValueOnce(springfield)
      .mockRejectedValueOnce(new AskError("Could not reach the API"));
    const user = await askFirst(askFn);
    await user.click(screen.getByRole("button", { name: /^B01001/ }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("Could not reach the API"));
    expect(document.querySelector(".census-url")?.textContent).toContain("B01003_001E");
    expect(screen.getByRole("cell", { name: "169,176" })).toBeTruthy();
  });

  it("does not send a plan when the editor is cancelled", async () => {
    const askFn = vi
      .fn<(question: string, plan?: ResultPlan) => Promise<AskResponse>>()
      .mockResolvedValue(springfield);
    const user = await askFirst(askFn);
    await user.click(screen.getByRole("button", { name: "Edit plan" }));
    await user.clear(screen.getByLabelText("Table"));
    await user.type(screen.getByLabelText("Table"), "NOPE");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(askFn).toHaveBeenCalledTimes(1);
    expect(document.querySelector(".plan-summary")?.textContent).toContain("B01003");
  });

  it("uses the original question even if the chat input changed", async () => {
    const askFn = vi
      .fn<(question: string, plan?: ResultPlan) => Promise<AskResponse>>()
      .mockResolvedValueOnce(springfield)
      .mockResolvedValueOnce(springfield);
    const user = await askFirst(askFn);
    await user.clear(screen.getByLabelText("Question"));
    await user.type(screen.getByLabelText("Question"), "please ignore this rewrite");
    await user.click(screen.getByRole("button", { name: /^B01001/ }));
    await waitFor(() => expect(askFn).toHaveBeenCalledTimes(2));
    expect(askFn.mock.calls[1]?.[0]).toBe("Population of Springfield");
    expect(askFn.mock.calls[1]?.[0]).not.toMatch(/rewrite/i);
  });

  it("clears a chat error after a successful plan apply", async () => {
    const askFn = vi
      .fn<(question: string, plan?: ResultPlan) => Promise<AskResponse>>()
      .mockResolvedValueOnce(springfield)
      .mockRejectedValueOnce(new Error("network down"))
      .mockResolvedValueOnce(springfield);
    const user = await askFirst(askFn);
    await user.clear(screen.getByLabelText("Question"));
    await user.type(screen.getByLabelText("Question"), "median rent in Houston");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("network down"));
    await user.click(screen.getByRole("button", { name: /^B01001/ }));
    await waitFor(() => expect(askFn).toHaveBeenCalledTimes(3));
    expect(screen.queryByText("network down")).toBeNull();
  });
});
