import { describe, expect, it, vi } from "vitest";
import type { DatasetRow } from "./display";
import { CSV_HEADERS, csvFilename, downloadCsv, rowsToCsv } from "./csv";

function row(partial: Partial<DatasetRow>): DatasetRow {
  return {
    dataset: "acs5", year: "2022", period: "2018-2022", tableId: "B17001",
    variable: "B17001_002E", geoid: "1400000US26163518300",
    name: 'Añasco, Tract "5"\nline two, cont.',
    estimate: "123456", moe: null, universe: "Population for whom poverty status is determined",
    ...partial,
  };
}

describe("rowsToCsv", () => {
  it("writes required headers, then one RFC 4180 row per DatasetRow, verbatim", () => {
    expect(CSV_HEADERS.join(",")).toBe(
      "dataset,vintage,period,table_id,variable,GEO_ID,NAME,estimate,moe,universe",
    );
    expect(rowsToCsv([row({})])).toBe(
      `${CSV_HEADERS.join(",")}\r\n` +
        'acs5,2022,2018-2022,B17001,B17001_002E,1400000US26163518300,"Añasco, Tract ""5""\n' +
        'line two, cont.",123456,,Population for whom poverty status is determined\r\n',
    );
  });

  it("leaves formula-like text unescaped and preserves identifiers with leading zeros, unformatted", () => {
    expect(rowsToCsv([row({ name: "=1+1" })])).toContain(",=1+1,");
    const csv = rowsToCsv([row({ geoid: "0400000US01", variable: "B01001_001E" })]);
    expect(csv).toContain(",0400000US01,");
    expect(csv).toContain(",B01001_001E,");
  });
});

describe("csvFilename", () => {
  it("joins table/dataset/vintage, strips unsafe characters, falls back on empty fields", () => {
    expect(csvFilename("B17001", "acs5", "2022")).toBe("B17001-acs5-2022.csv");
    expect(csvFilename("../../etc/passwd", "acs5", "")).toBe("etc-passwd-acs5-export.csv");
  });
});

describe("downloadCsv", () => {
  it("attaches the filenamed anchor to the DOM before clicking, prepends a UTF-8 BOM, cleans up, and revokes the URL", () => {
    const anchor = document.createElement("a");
    let attachedAtClick = false;
    const clickSpy = vi.spyOn(anchor, "click").mockImplementation(() => (attachedAtClick = document.body.contains(anchor)));
    vi.spyOn(document, "createElement").mockReturnValue(anchor);
    const BlobSpy = vi.fn((parts: unknown[]) => ({ parts }));
    vi.stubGlobal("Blob", BlobSpy);
    downloadCsv("B17001-acs5-2022.csv", "a,b\r\n1,2\r\n");
    vi.unstubAllGlobals();
    expect(anchor.download).toBe("B17001-acs5-2022.csv");
    expect(BlobSpy.mock.calls[0]?.[0]).toEqual(["\ufeff", "a,b\r\n1,2\r\n"]);
    expect(attachedAtClick).toBe(true);
    expect(clickSpy).toHaveBeenCalledOnce();
    expect(document.body.contains(anchor)).toBe(false);
    expect(URL.revokeObjectURL).toHaveBeenCalled();
  });
});
