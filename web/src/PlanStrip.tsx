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
  id,
  name,
  field,
  message,
}: {
  id: string;
  name: string;
  field: string;
  message: string;
}) {
  if (!message || field !== name) {
    return null;
  }
  return (
    <p id={id} className="plan-field-error" role="alert">
      {message}
    </p>
  );
}

function alternativeName(tableId: string, title: string, universe: string): string {
  return [tableId, title, universe].filter(Boolean).join(" — ");
}

export function PlanStrip({ result, busy, error, field, onApply, onClearError }: PlanStripProps) {
  const stripRef = useRef<HTMLElement>(null);
  const tableRef = useRef<HTMLInputElement>(null);
  const datasetRef = useRef<HTMLSelectElement>(null);
  const yearsRef = useRef<HTMLInputElement>(null);
  const geoRef = useRef<HTMLFieldSetElement>(null);
  const catchAllRef = useRef<HTMLParagraphElement>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<PlanDraft>(() => draftFromPlan(result));
  const [localError, setLocalError] = useState("");
  const [localField, setLocalField] = useState("");

  useEffect(() => {
    setDraft(draftFromPlan(result));
    setEditing(false);
    setLocalError("");
    setLocalField("");
  }, [result]);

  useEffect(() => {
    if (editing && !error && !localError) {
      tableRef.current?.focus();
    }
  }, [editing, error, localError]);

  const choices = geographyChoices(result);
  const omitted = omittedYears(result);
  const stripField = localError ? localField : field;
  const stripMessage = localError || error;
  const yearsInvalid = stripField === "years" && Boolean(stripMessage);
  const geoInvalid = stripField === "geographies" && Boolean(stripMessage);

  useEffect(() => {
    const active = localError ? localField : field;
    if (!localError && !error) {
      return;
    }
    if (active === "table_id") {
      tableRef.current?.focus();
    } else if (active === "dataset") {
      datasetRef.current?.focus();
    } else if (active === "years") {
      yearsRef.current?.focus();
    } else if (active === "geographies") {
      geoRef.current?.focus();
    } else {
      catchAllRef.current?.focus();
    }
  }, [error, field, localError, localField]);

  function startEdit() {
    setDraft(draftFromPlan(result));
    setLocalError("");
    setLocalField("");
    onClearError();
    setEditing(true);
  }

  function cancel() {
    setDraft(draftFromPlan(result));
    setLocalError("");
    setLocalField("");
    onClearError();
    setEditing(false);
    stripRef.current?.focus();
  }

  async function applyPlan(plan: ResultPlan) {
    setLocalError("");
    setLocalField("");
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
    if (!draft.tableId.trim()) {
      setLocalField("table_id");
      setLocalError("Enter a table ID");
      return;
    }
    const requested = parseYearList(draft.requestedYears);
    if (requested === null) {
      setLocalField("years");
      setLocalError("Enter years as 2024 or 2017-2023");
      return;
    }
    if (choices.length > 0 && draft.geoids.length === 0) {
      setLocalField("geographies");
      setLocalError("Select at least one geography");
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
              aria-invalid={stripField === "table_id"}
              aria-describedby={stripField === "table_id" ? "plan-error-table" : undefined}
              value={draft.tableId}
              disabled={busy}
              onChange={(event) => setDraft({ ...draft, tableId: event.target.value })}
            />
          </label>
          <FieldNote id="plan-error-table" name="table_id" field={stripField} message={stripMessage} />
          <label>
            Dataset
            <select
              ref={datasetRef}
              aria-label="Dataset"
              aria-invalid={stripField === "dataset"}
              aria-describedby={stripField === "dataset" ? "plan-error-dataset" : undefined}
              value={draft.dataset}
              disabled={busy}
              onChange={(event) => setDraft({ ...draft, dataset: event.target.value })}
            >
              <option value="acs5">acs5</option>
              <option value="acs1">acs1</option>
            </select>
          </label>
          <FieldNote id="plan-error-dataset" name="dataset" field={stripField} message={stripMessage} />
          <label>
            Requested years
            <input
              ref={yearsRef}
              aria-label="Requested years"
              aria-invalid={yearsInvalid}
              aria-describedby={yearsInvalid ? "plan-error-years" : undefined}
              value={draft.requestedYears}
              disabled={busy}
              onChange={(event) => setDraft({ ...draft, requestedYears: event.target.value })}
            />
          </label>
          <p className="plan-note">
            Fetched {(result.plan.years ?? []).join(", ") || "—"}; omitted {omitted.join(", ") || "none"}
          </p>
          <FieldNote
            id="plan-error-years"
            name="years"
            field={stripField}
            message={stripMessage}
          />
          <fieldset
            ref={geoRef}
            tabIndex={-1}
            className="plan-geos"
            aria-invalid={geoInvalid}
            aria-describedby={geoInvalid ? "plan-error-geographies" : undefined}
          >
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
          <FieldNote id="plan-error-geographies" name="geographies" field={stripField} message={stripMessage} />
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
        <p ref={catchAllRef} tabIndex={-1} className="plan-field-error" role="alert">
          {stripMessage}
        </p>
      ) : null}
      {editing && stripMessage && (stripField === "" || stripField === "plan") ? (
        <p ref={catchAllRef} tabIndex={-1} className="plan-field-error" role="alert">
          {stripMessage}
        </p>
      ) : null}
      <h2>Related tables</h2>
      {result.alternatives.length > 0 ? (
        <ul className="alts">
          {result.alternatives.map((alt) => (
            <li key={`${alt.table_id}:${alt.reason}`}>
              <button
                type="button"
                disabled={busy}
                aria-label={alternativeName(alt.table_id, alt.title, alt.universe)}
                onClick={() => void applyPlan(tableOverride(result.plan, alt.table_id))}
              >
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
