import { FormEvent, useEffect, useRef, useState } from "react";
import type { AskResponse, ResultPlan } from "./ask";
import {
  draftFromPlan,
  geographyChoices,
  labelGeography,
  omittedYears,
  parseYearList,
  planFromDraft,
  tableOverride,
  type PlanDraft,
} from "./plan";

type PlanStripProps = {
  result: AskResponse;
  busy: boolean;
  error: string;
  field: string;
  onApply: (plan: ResultPlan) => Promise<boolean>;
  onClearError: () => void;
};

function FieldNote({
  name,
  field,
  message,
}: {
  name: string;
  field: string;
  message: string;
}) {
  if (!message || field !== name) {
    return null;
  }
  return (
    <p className="plan-field-error" role="alert">
      {message}
    </p>
  );
}

export function PlanStrip({ result, busy, error, field, onApply, onClearError }: PlanStripProps) {
  const stripRef = useRef<HTMLElement>(null);
  const tableRef = useRef<HTMLInputElement>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<PlanDraft>(() => draftFromPlan(result));
  const [localError, setLocalError] = useState("");

  useEffect(() => {
    setDraft(draftFromPlan(result));
    setEditing(false);
    setLocalError("");
  }, [result]);

  useEffect(() => {
    if (editing) {
      tableRef.current?.focus();
    }
  }, [editing]);

  const choices = geographyChoices(result);
  const omitted = omittedYears(result);
  const yearsMessage = localError || (field === "years" ? error : "");
  const stripMessage = localError ? "" : error;
  const stripField = localError ? "" : field;

  function startEdit() {
    setDraft(draftFromPlan(result));
    setLocalError("");
    onClearError();
    setEditing(true);
  }

  function cancel() {
    setDraft(draftFromPlan(result));
    setLocalError("");
    onClearError();
    setEditing(false);
    stripRef.current?.focus();
  }

  async function applyPlan(plan: ResultPlan) {
    setLocalError("");
    const ok = await onApply(plan);
    if (ok) {
      setEditing(false);
      stripRef.current?.focus();
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (busy) {
      return;
    }
    const requested = parseYearList(draft.requestedYears);
    if (requested === null) {
      setLocalError("Enter years as 2024 or 2017-2023");
      return;
    }
    await applyPlan(planFromDraft(result, draft, requested));
  }

  function toggleGeo(geoid: string) {
    setDraft((current) => ({
      ...current,
      geoids: current.geoids.includes(geoid)
        ? current.geoids.filter((id) => id !== geoid)
        : [...current.geoids, geoid],
    }));
  }

  const geos = result.plan.geographies ?? [];

  return (
    <section className="plan-strip" aria-labelledby="plan-heading" ref={stripRef} tabIndex={-1}>
      <h2 id="plan-heading">Plan</h2>
      {editing ? (
        <form className="plan-form" aria-label="Edit plan" onSubmit={(event) => void onSubmit(event)}>
          <label>
            Table
            <input
              ref={tableRef}
              aria-label="Table"
              value={draft.tableId}
              disabled={busy}
              onChange={(event) => setDraft({ ...draft, tableId: event.target.value })}
            />
          </label>
          <FieldNote name="table_id" field={stripField} message={stripMessage} />
          <label>
            Dataset
            <select
              aria-label="Dataset"
              value={draft.dataset}
              disabled={busy}
              onChange={(event) => setDraft({ ...draft, dataset: event.target.value })}
            >
              <option value="acs5">acs5</option>
              <option value="acs1">acs1</option>
            </select>
          </label>
          <FieldNote name="dataset" field={stripField} message={stripMessage} />
          <label>
            Requested years
            <input
              aria-label="Requested years"
              value={draft.requestedYears}
              disabled={busy}
              onChange={(event) => setDraft({ ...draft, requestedYears: event.target.value })}
            />
          </label>
          <p className="plan-note">
            Fetched {(result.plan.years ?? []).join(", ") || "—"}; omitted {omitted.join(", ") || "none"}
          </p>
          <FieldNote name="years" field={localError ? "years" : stripField} message={yearsMessage} />
          <fieldset className="plan-geos">
            <legend>Geography</legend>
            {choices.length === 0 ? (
              <p>No executable geographies in this result.</p>
            ) : (
              choices.map((geo) => (
                <label key={geo.geoid}>
                  <input
                    type="checkbox"
                    checked={draft.geoids.includes(geo.geoid)}
                    disabled={busy}
                    onChange={() => toggleGeo(geo.geoid)}
                  />
                  {labelGeography(geo)}
                </label>
              ))
            )}
          </fieldset>
          <FieldNote name="geographies" field={stripField} message={stripMessage} />
          <label className="plan-overlap">
            <input
              type="checkbox"
              aria-label="Allow consecutive ACS 5-year periods"
              checked={draft.allowOverlapping}
              disabled={busy}
              onChange={(event) => setDraft({ ...draft, allowOverlapping: event.target.checked })}
            />
            Allow consecutive ACS 5-year periods
          </label>
          <div className="plan-actions">
            <button type="submit" disabled={busy}>
              Apply
            </button>
            <button type="button" disabled={busy} onClick={cancel}>
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <>
          <dl className="plan-summary">
            <dt>Dataset</dt>
            <dd>{result.plan.dataset || "—"}</dd>
            <dt>Years</dt>
            <dd>
              requested {(result.plan.requested_years ?? []).join(", ") || "—"}; fetched{" "}
              {(result.plan.years ?? []).join(", ") || "—"}
              {omitted.length ? `; omitted ${omitted.join(", ")}` : ""}
            </dd>
            <dt>Table</dt>
            <dd>{result.plan.table_id || "—"}</dd>
            <dt>Geography</dt>
            <dd>{geos.length ? geos.map(labelGeography).join("; ") : "—"}</dd>
            <dt>Consecutive ACS5</dt>
            <dd>{result.plan.allow_overlapping_acs5 ? "allowed" : "not allowed"}</dd>
          </dl>
          <button type="button" onClick={startEdit} disabled={busy}>
            Edit plan
          </button>
        </>
      )}
      {!editing && stripMessage ? (
        <p className="plan-field-error" role="alert">
          {stripMessage}
        </p>
      ) : null}
      {editing && stripMessage && (stripField === "" || stripField === "plan") ? (
        <p className="plan-field-error" role="alert">
          {stripMessage}
        </p>
      ) : null}
      <h2>Related tables</h2>
      {result.alternatives.length > 0 ? (
        <ul className="alts">
          {result.alternatives.map((alt) => (
            <li key={`${alt.table_id}:${alt.reason}`}>
              <button type="button" disabled={busy} onClick={() => void applyPlan(tableOverride(result.plan, alt.table_id))}>
                {alt.table_id}
              </button>
              <span>{alt.title || "—"}</span>
              <span>{alt.universe || "—"}</span>
              <span>{alt.reason}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p>None in this response.</p>
      )}
    </section>
  );
}
