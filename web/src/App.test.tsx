import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { App } from "./App";
import type { AskResponse } from "./ask";

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

const rentFailure: AskResponse = {
  answer: "Census returned HTTP 400.",
  url: "https://api.census.gov/data/2024/acs/acs5?get=NAME,GEO_ID,B25064_001E,B25064_001M&for=place:99999&in=state:48",
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
    expect(screen.getByText(/could not reach the api: network down/i)).toBeTruthy();
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
    expect(screen.getByText(/B01003_001E: 4838303 ± 123/)).toBeTruthy();
    expect(screen.getByText("0500000US48201")).toBeTruthy();
    expect(screen.getByText("Total population")).toBeTruthy();
    expect(screen.getByText(/B01001 — related table/)).toBeTruthy();
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
    expect(screen.getByText("B25064")).toBeTruthy();
    expect(screen.getByText("Renter-occupied housing units paying cash rent")).toBeTruthy();
    expect(screen.getByText("1600000US4805000")).toBeTruthy();
    expect(screen.getByText(/B25063 — distribution versus median/)).toBeTruthy();
  });
});
