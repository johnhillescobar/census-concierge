import { FormEvent, useEffect, useRef, useState } from "react";
import { ask, type AskResponse } from "./ask";
import {
  censusFetchFailed,
  censusUrls,
  censusYearsIncomplete,
  formatCensusNumber,
  normalizeActiveDataset,
  type DatasetRow,
  type PaneState,
} from "./display";

type AppProps = {
  askFn?: (question: string) => Promise<AskResponse>;
};

const TABLE_HEADERS = [
  "GEOID",
  "Name",
  "Dataset",
  "Year",
  "Period",
  "Table",
  "Variable",
  "Estimate",
  "MOE",
] as const;

function EstimatesTable({ rows }: { rows: DatasetRow[] }) {
  return (
    <>
      <h2>Estimates</h2>
      <div className="table-scroll" tabIndex={0} aria-label="Estimates">
        <table className="geo-table">
          <thead>
            <tr>
              {TABLE_HEADERS.map((header) => (
                <th key={header} scope="col">
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={TABLE_HEADERS.length}>No estimates returned.</td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={`${row.year}:${row.period}:${row.geoid}:${row.name}:${row.variable}`}>
                  <td>{row.geoid || "—"}</td>
                  <td>{row.name || "—"}</td>
                  <td>{row.dataset || "—"}</td>
                  <td>{row.year || "—"}</td>
                  <td>{row.period || "—"}</td>
                  <td>{row.tableId || "—"}</td>
                  <td>{row.variable || "—"}</td>
                  <td>{formatCensusNumber(row.estimate)}</td>
                  <td>{formatCensusNumber(row.moe)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

function ActiveDataset({
  result,
  copied,
  onCopyUrl,
}: {
  result: AskResponse;
  copied: boolean;
  onCopyUrl: () => void;
}) {
  const dataset = normalizeActiveDataset(result);
  const urls = censusUrls(result);
  const failed = censusFetchFailed(result);
  const incomplete = censusYearsIncomplete(result);
  const geoids = [...new Set(dataset.map((row) => row.geoid).filter(Boolean))];
  const geoidLabel =
    result.geoid || (geoids.length > 1 ? `${geoids.length} areas` : geoids[0] || "—");
  const datasetLabel = dataset.find((row) => row.dataset)?.dataset;

  return (
    <>
      {failed ? (
        <p className="notice" role="status">
          Census fetch failed. The URL and table metadata are still shown.
        </p>
      ) : null}
      {incomplete ? (
        <p className="notice" role="status">
          Some requested years were not fetched. Every attempted URL is still shown.
        </p>
      ) : null}
      <dl className="meta">
        <dt>Table</dt>
        <dd>{result.table_id || "—"}</dd>
        <dt>Universe</dt>
        <dd>{result.universe || "—"}</dd>
        <dt>GEOID</dt>
        <dd>{geoidLabel}</dd>
        {datasetLabel ? (
          <>
            <dt>Dataset</dt>
            <dd>{datasetLabel}</dd>
          </>
        ) : null}
      </dl>
      <EstimatesTable rows={dataset} />
      <h2>Census API URL</h2>
      {urls.length > 0 ? (
        <div className="url-row">
          <div className="census-urls">
            {urls.map((item) => (
              <pre key={item} className="census-url">
                {item}
              </pre>
            ))}
          </div>
          <button type="button" onClick={() => void onCopyUrl()}>
            {copied ? "Copied" : urls.length > 1 ? "Copy URLs" : "Copy URL"}
          </button>
        </div>
      ) : (
        <p className="notice" role="status">
          No Census URL was built.
        </p>
      )}
      <h2>Alternatives</h2>
      {result.alternatives.length > 0 ? (
        <ul className="alts">
          {result.alternatives.map((alt) => (
            <li key={`${alt.table_id}:${alt.reason}`}>
              {alt.table_id} — {alt.reason}
            </li>
          ))}
        </ul>
      ) : (
        <p>None in this response.</p>
      )}
      {result.warnings.length > 0 ? (
        <>
          <h2>Warnings</h2>
          <ul className="warnings">
            {result.warnings.map((warning) => (
              <li key={warning.code}>
                {warning.code}: {warning.detail}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </>
  );
}

export function App({ askFn = ask }: AppProps) {
  const [question, setQuestion] = useState("");
  const [state, setState] = useState<PaneState>("idle");
  const [error, setError] = useState("");
  const [result, setResult] = useState<AskResponse | null>(null);
  const [activeQuestion, setActiveQuestion] = useState("");
  const [copied, setCopied] = useState(false);
  const loadingRef = useRef<HTMLParagraphElement>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (state === "loading") {
      loadingRef.current?.focus();
    }
  }, [state]);

  useEffect(() => {
    if (error) {
      errorRef.current?.focus();
    }
  }, [error]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || state === "loading") {
      return;
    }
    const keepResult = result !== null;
    setState("loading");
    setError("");
    setCopied(false);
    try {
      const response = await askFn(text);
      setResult(response);
      setActiveQuestion(text);
      setState("result");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "ask failed");
      setState(keepResult ? "result" : "error");
    }
  }

  async function onCopyUrl() {
    const urlText = result ? censusUrls(result).join("\n") : "";
    if (!urlText) {
      return;
    }
    try {
      await navigator.clipboard.writeText(urlText);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <main className="workspace">
      <section className="chat" aria-labelledby="chat-heading">
        <h1 id="chat-heading">census-concierge</h1>
        <p className="lede">
          Ask a Census question. The table, URL, and related tables come back together.
        </p>
        <form onSubmit={onSubmit}>
          <input
            aria-label="Question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="population of Harris County, Texas"
          />
          <button type="submit" disabled={state === "loading"}>
            Ask
          </button>
        </form>
        {error ? (
          <p ref={errorRef} tabIndex={-1} role="alert">
            {error}
          </p>
        ) : null}
        {result?.answer ? <p className="answer">{result.answer}</p> : null}
      </section>
      <section
        className="pane"
        data-state={state}
        aria-labelledby="canvas-heading"
        aria-busy={state === "loading"}
      >
        <h2 id="canvas-heading">Working dataset</h2>
        {activeQuestion ? <p>Active question: {activeQuestion}</p> : null}
        {state === "idle" ? (
          <p>Type a question to see the selected table, its URL, and alternatives.</p>
        ) : null}
        {state === "loading" ? (
          <p ref={loadingRef} tabIndex={-1}>
            Looking up tables…
          </p>
        ) : null}
        {result ? <ActiveDataset result={result} copied={copied} onCopyUrl={onCopyUrl} /> : null}
      </section>
    </main>
  );
}
