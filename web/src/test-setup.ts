import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

vi.mock("vega-embed", () => ({
  default: vi.fn(() => Promise.resolve({ finalize: vi.fn() })),
}));

if (!URL.createObjectURL) {
  Object.assign(URL, { createObjectURL: vi.fn(() => "blob:mock"), revokeObjectURL: vi.fn() });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
