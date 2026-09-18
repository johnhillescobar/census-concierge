import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { AskResponse } from "./ask";

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
};

const rentFailure: AskResponse = {
  answer: "Census returned HTTP 400.",
  urls: [
    "https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B25064_001E,B25064_001M&for=place:99999&in=state:48",
  ],
  requested_years: [2024],
  attempted_years: [2024],
  succeeded_years: [],
  failed_years: [2024],
  omitted_years: [],
  omission_reasons: [],
  legs: [],
  rows: [],
  moe: [],
  geoid: "1600000US4805000",
  universe: "Renter-occupied housing units paying cash rent",
  table_id: "B25064",
  alternatives: [{ table_id: "B25063", reason: "distribution versus median" }],
  warnings: [{ code: "geography_unsupported", detail: "not published at this level" }],
};

function pane(): HTMLElement {
  return document.querySelector(".pane") as HTMLElement;
}

describe("App pane states", () => {
  it("starts idle, with no Census URL", () => {
    render(<App askFn={() => Promise.resolve(harris)} />);
    expect(pane().dataset.state).toBe("idle");
    expect(document.querySelector(".census-url")).toBeNull();
    expect(screen.queryByRole("button", { name: "Copy URL" })).toBeNull();
    expect(screen.getByText(/type a question/i)).toBeTruthy();
  });

  it("shows a loading state distinct from idle while the request is in flight", async () => {
    const user = userEvent.setup({ delay: null });
    let finish: (value: AskResponse) => void = () => undefined;
    const pending = new Promise<AskResponse>((resolve) => {
      finish = resolve;
    });
    render(<App askFn={() => pending} />);
    await user.type(screen.getByLabelText("Question"), "population of Harris County");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(pane().dataset.state).toBe("loading");
    expect(screen.getByText(/looking up tables/i)).toBeTruthy();
    expect(document.querySelector(".census-url")).toBeNull();
    finish(harris);
    await waitFor(() => expect(pane().dataset.state).toBe("result"));
  });

  it("shows an error state distinct from idle when the API is unreachable", async () => {
    const user = userEvent.setup({ delay: null });
    render(<App askFn={() => Promise.reject(new Error("network down"))} />);
    await user.type(screen.getByLabelText("Question"), "population of Harris County");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(pane().dataset.state).toBe("error"));
    expect(screen.getByText("network down")).toBeTruthy();
    expect(screen.queryByText(/could not reach/i)).toBeNull();
    expect(document.querySelector(".census-url")).toBeNull();
    expect(screen.queryByText(/type a question/i)).toBeNull();
  });
});

describe("App result", () => {
  it("renders URL, estimate with MOE, GEOID, universe, and an alternative", async () => {
    const user = userEvent.setup({ delay: null });
    render(<App askFn={() => Promise.resolve(harris)} />);
    await user.type(screen.getByLabelText("Question"), "population of Harris County");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(pane().dataset.state).toBe("result"));
    expect(document.querySelector(".census-url")?.textContent).toContain(
      "https://api.census.gov/data/2024/acs/acs5",
    );
    expect(screen.getByRole("button", { name: "Copy URL" })).toBeTruthy();
    expect(screen.getByText(/B01003_001E: 4838303 ± 123/)).toBeTruthy();
    expect(screen.getByText("0500000US48201")).toBeTruthy();
    expect(screen.getByText("Total population")).toBeTruthy();
    expect(screen.getByText(/B01001 — related table/)).toBeTruthy();
  });

  it("copies the visible Census URL without a key parameter", async () => {
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
    const user = userEvent.setup({ delay: null });
    render(
      <App
        askFn={() =>
          Promise.resolve({
            ...harris,
            urls: [`${harris.urls[0]}&key=secret`],
          })
        }
      />,
    );
    await user.type(screen.getByLabelText("Question"), "population of Harris County");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(pane().dataset.state).toBe("result"));
    await user.click(screen.getByRole("button", { name: "Copy URL" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const copied = writeText.mock.calls[0][0] as string;
    expect(copied).toContain("https://api.census.gov/data/2024/acs/acs5");
    expect(copied).toContain("B01003_001E");
    expect(copied).not.toMatch(/key=/i);
    expect(screen.getByRole("button", { name: "Copied" })).toBeTruthy();
  });

  it("keeps the copy control when clipboard write is denied", async () => {
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));
    const user = userEvent.setup({ delay: null });
    render(<App askFn={() => Promise.resolve(harris)} />);
    await user.type(screen.getByLabelText("Question"), "population of Harris County");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(pane().dataset.state).toBe("result"));
    await user.click(screen.getByRole("button", { name: "Copy URL" }));
    expect(pane().dataset.state).toBe("result");
    await waitFor(() => expect(screen.getByRole("button", { name: "Copy URL" })).toBeTruthy());
  });

  it("keeps URL and table metadata on Census fetch failure, with a visible notice", async () => {
    const user = userEvent.setup({ delay: null });
    render(<App askFn={() => Promise.resolve(rentFailure)} />);
    await user.type(screen.getByLabelText("Question"), "median rent in nowhere");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(pane().dataset.state).toBe("result"));
    expect(pane().dataset.state).not.toBe("error");
    expect(screen.getByRole("status").textContent).toMatch(/census fetch failed/i);
    expect(document.querySelector(".census-url")?.textContent).toContain("B25064_001E");
    expect(screen.getByRole("button", { name: "Copy URL" })).toBeTruthy();
    expect(screen.getByText("B25064")).toBeTruthy();
    expect(screen.getByText("Renter-occupied housing units paying cash rent")).toBeTruthy();
    expect(screen.getByText("1600000US4805000")).toBeTruthy();
    expect(screen.getByText(/B25063 — distribution versus median/)).toBeTruthy();
  });

  it("labels every geography instead of presenting the first row as the answer", async () => {
    const user = userEvent.setup({ delay: null });
    const oregon: AskResponse = {
      ...harris,
      answer: "Population for Oregon counties.",
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
    render(<App askFn={() => Promise.resolve(oregon)} />);
    await user.type(screen.getByLabelText("Question"), "population of every county in Oregon");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(pane().dataset.state).toBe("result"));
    expect(screen.getByText("2 areas")).toBeTruthy();
    expect(screen.queryByText(/B01003_001E: 16668 ± 24/)).toBeNull();
    expect(screen.getByText("0500000US41001")).toBeTruthy();
    expect(screen.getByText("0500000US41003")).toBeTruthy();
    expect(screen.getByText("16668")).toBeTruthy();
    expect(screen.getByText("95184")).toBeTruthy();
    expect(screen.getAllByText("B01003_001E")).toHaveLength(2);
  });

  it("renders every estimate variable for every geography", async () => {
    const user = userEvent.setup({ delay: null });
    const mixed: AskResponse = {
      ...harris,
      answer: "Sex by age for two counties.",
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
    render(<App askFn={() => Promise.resolve(mixed)} />);
    await user.type(screen.getByLabelText("Question"), "sex by age in Oregon counties");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(pane().dataset.state).toBe("result"));
    expect(screen.getAllByText("B01001_001E")).toHaveLength(2);
    expect(screen.getAllByText("B01001_002E")).toHaveLength(2);
    expect(screen.getByText("8401")).toBeTruthy();
    expect(screen.getByText("47012")).toBeTruthy();
  });

  it("does not present a Census missing sentinel as a numeric MOE", async () => {
    const user = userEvent.setup({ delay: null });
    render(
      <App
        askFn={() =>
          Promise.resolve({
            ...harris,
            moe: [{ GEO_ID: "0500000US48201", NAME: "Harris County, Texas", B01003_001M: "-555555555" }],
            rows: [{ ...harris.rows[0], B01003_001M: "-555555555" }],
          })
        }
      />,
    );
    await user.type(screen.getByLabelText("Question"), "population of Harris County");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(pane().dataset.state).toBe("result"));
    expect(screen.getByText(/B01003_001E: 4838303 ± —/)).toBeTruthy();
    expect(screen.queryByText(/-555555555/)).toBeNull();
  });

  it("does not treat an empty URL as a successful Census URL", async () => {
    const user = userEvent.setup({ delay: null });
    render(
      <App
        askFn={() =>
          Promise.resolve({
            ...harris,
            urls: [],
            rows: [],
            moe: [],
            answer: "stopped before build_url",
          })
        }
      />,
    );
    await user.type(screen.getByLabelText("Question"), "population of Harris County");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(pane().dataset.state).toBe("result"));
    expect(document.querySelector(".census-url")).toBeNull();
    expect(screen.queryByRole("button", { name: "Copy URL" })).toBeNull();
    expect(screen.getByRole("status").textContent).toMatch(/no census url was built/i);
  });

  it("shows every attempted URL and copies them without a key", async () => {
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
    const user = userEvent.setup({ delay: null });
    const first = harris.urls[0];
    const second = first.replace("/2024/", "/2019/");
    render(
      <App
        askFn={() =>
          Promise.resolve({
            ...harris,
            urls: [`${first}&key=secret`, `${second}&key=secret`],
            requested_years: [2019, 2024],
            attempted_years: [2019, 2024],
            succeeded_years: [2019, 2024],
          })
        }
      />,
    );
    await user.type(screen.getByLabelText("Question"), "population since 2019");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(pane().dataset.state).toBe("result"));
    const shown = [...document.querySelectorAll(".census-url")].map((node) => node.textContent || "");
    expect(shown).toHaveLength(2);
    expect(shown.some((text) => text.includes("/2019/"))).toBe(true);
    expect(shown.some((text) => text.includes("/2024/"))).toBe(true);
    expect(shown.every((text) => !/key=/i.test(text))).toBe(true);
    await user.click(screen.getByRole("button", { name: "Copy URLs" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const copied = writeText.mock.calls[0][0] as string;
    expect(copied).toContain("/2019/");
    expect(copied).toContain("/2024/");
    expect(copied).not.toMatch(/key=/i);
  });

  it("labels the year when more than one vintage was attempted", async () => {
    const user = userEvent.setup({ delay: null });
    const first = harris.urls[0];
    const second = first.replace("/2024/", "/2019/");
    render(
      <App
        askFn={() =>
          Promise.resolve({
            ...harris,
            urls: [first, second],
            requested_years: [2019, 2024],
            attempted_years: [2019, 2024],
            succeeded_years: [2024],
            failed_years: [2019],
            rows: [{ ...harris.rows[0], year: "2024" }],
          })
        }
      />,
    );
    await user.type(screen.getByLabelText("Question"), "population since 2019");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(pane().dataset.state).toBe("result"));
    expect(screen.getByRole("columnheader", { name: "Year" })).toBeTruthy();
    expect(screen.getByRole("cell", { name: "2024" })).toBeTruthy();
  });

  it("notices when some requested years were not fetched", async () => {
    const user = userEvent.setup({ delay: null });
    const first = harris.urls[0];
    const second = first.replace("/2024/", "/2019/");
    render(
      <App
        askFn={() =>
          Promise.resolve({
            ...harris,
            urls: [first, second],
            requested_years: [2019, 2024],
            attempted_years: [2019, 2024],
            succeeded_years: [2024],
            failed_years: [2019],
            rows: [{ ...harris.rows[0], year: "2024" }],
          })
        }
      />,
    );
    await user.type(screen.getByLabelText("Question"), "population since 2019");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(pane().dataset.state).toBe("result"));
    expect(screen.getByRole("status").textContent).toMatch(/some requested years were not fetched/i);
    expect(screen.queryByText(/census fetch failed/i)).toBeNull();
  });

  it("shows dataset and period on a series point", async () => {
    const user = userEvent.setup({ delay: null });
    render(
      <App
        askFn={() =>
          Promise.resolve({
            ...harris,
            attempted_years: [2018, 2022],
            rows: [
              {
                ...harris.rows[0],
                year: "2018",
                dataset: "acs5",
                period: "2014-2018",
                table_id: "B01003",
              },
              {
                ...harris.rows[0],
                GEO_ID: "0500000US48201",
                year: "2022",
                dataset: "acs5",
                period: "2018-2022",
                table_id: "B01003",
              },
            ],
            moe: [harris.moe[0], harris.moe[0]],
          })
        }
      />,
    );
    await user.type(screen.getByLabelText("Question"), "population since 2018");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(pane().dataset.state).toBe("result"));
    expect(screen.getByText("acs5")).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Period" })).toBeTruthy();
    expect(screen.getByRole("cell", { name: "2014-2018" })).toBeTruthy();
    expect(screen.getByRole("cell", { name: "2018-2022" })).toBeTruthy();
  });

  it("does not label an HTTP failure as unreachable", async () => {
    const user = userEvent.setup({ delay: null });
    render(<App askFn={() => Promise.reject(new Error("ask failed (500)"))} />);
    await user.type(screen.getByLabelText("Question"), "population of Harris County");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(pane().dataset.state).toBe("error"));
    expect(screen.getByText("ask failed (500)")).toBeTruthy();
    expect(screen.queryByText(/could not reach/i)).toBeNull();
  });
});
