import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

vi.mock("vega-embed", () => ({
  default: vi.fn(() => Promise.resolve({ finalize: vi.fn() })),
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
