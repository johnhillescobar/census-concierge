import type { AskResponse, GeoSpec, ResultPlan } from "./ask";

export type PlanDraft = {
  tableId: string;
  dataset: string;
  requestedYears: string;
  geoids: string[];
  allowOverlapping: boolean;
};

export function formatYearList(years: number[]): string {
  return years.join(", ");
}

export function parseYearList(text: string): number[] | null {
  const trimmed = text.trim();
  if (!trimmed) {
    return null;
  }
  const years: number[] = [];
  for (const part of trimmed.split(/[\s,]+/).filter(Boolean)) {
    const range = /^(\d{4})-(\d{4})$/.exec(part);
    if (range) {
      const start = Number(range[1]);
      const end = Number(range[2]);
      const lo = Math.min(start, end);
      const hi = Math.max(start, end);
      for (let year = lo; year <= hi; year += 1) {
        years.push(year);
      }
      continue;
    }
    if (!/^\d{4}$/.test(part)) {
      return null;
    }
    years.push(Number(part));
  }
  return [...new Set(years)].sort((a, b) => a - b);
}

export function draftFromPlan(result: AskResponse): PlanDraft {
  return {
    tableId: result.plan.table_id,
    dataset: result.plan.dataset || "acs5",
    requestedYears: formatYearList(result.plan.requested_years ?? []),
    geoids: (result.plan.geographies ?? []).map((geo) => geo.geoid).filter(Boolean),
    allowOverlapping: result.plan.allow_overlapping_acs5,
  };
}

export function geographyChoices(result: AskResponse): GeoSpec[] {
  const seen = new Set<string>();
  const out: GeoSpec[] = [];
  const add = (geo: GeoSpec | undefined) => {
    if (!geo?.geoid || seen.has(geo.geoid)) {
      return;
    }
    seen.add(geo.geoid);
    out.push(geo);
  };
  for (const geo of result.plan.geographies ?? []) {
    add(geo);
  }
  for (const warning of result.warnings) {
    for (const geo of warning.candidates ?? []) {
      add(geo);
    }
  }
  return out;
}

export function omittedYears(result: AskResponse): number[] {
  if (result.omitted_years.length) {
    return result.omitted_years;
  }
  const effective = new Set(result.plan.years ?? []);
  return (result.plan.requested_years ?? []).filter((year) => !effective.has(year));
}

export function tableOverride(plan: ResultPlan, tableId: string): ResultPlan {
  return {
    ...plan,
    table_id: tableId,
    variables: (plan.variables ?? []).filter((item) => item.startsWith(`${tableId}_`)),
  };
}

export function planFromDraft(result: AskResponse, draft: PlanDraft, requested: number[]): ResultPlan {
  const tableId = draft.tableId.trim();
  const selected = new Set(draft.geoids);
  return tableOverride(
    {
      ...result.plan,
      table_id: tableId,
      dataset: draft.dataset,
      requested_years: requested,
      years: requested,
      geographies: geographyChoices(result).filter((geo) => selected.has(geo.geoid)),
      allow_overlapping_acs5: draft.allowOverlapping,
    },
    tableId,
  );
}

export function labelGeography(geo: GeoSpec): string {
  return geo.name && geo.geoid ? `${geo.name} (${geo.geoid})` : geo.name || geo.geoid;
}
