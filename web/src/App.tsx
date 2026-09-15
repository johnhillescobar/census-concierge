import { FormEvent, useState } from "react";
import { ask, type AskResponse } from "./ask";
import {
  censusFetchFailed,
  censusUrls,
  censusYearsIncomplete,
  estimatesByGeography,
  formatCensusValue,
  type PaneState,
} from "./display";

type AppProps = {
  askFn?: (question: string) => Promise<AskResponse>;
};

export function App({ askFn = ask }: AppProps) {
  const [question, setQuestion] = useState("");
  const [state, setState] = useState<PaneState>("idle");
  const [error, setError] = useState("");
  const [result, setResult] = useState<AskResponse | null>(null);
  const [copied, setCopied] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || state === "loading") {
      return;
    }
    setState("loading");
    setError("");
    setResult(null);
    setCopied(false);
    try {
      const response = await askFn(text);
      setResult(response);
      setState("result");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "ask failed");
      setState("error");
    }
  }

  const areas = result ? estimatesByGeography(result) : [];
  const urls = result ? censusUrls(result) : [];
  const urlText = urls.join("\n");
  const failed = result ? censusFetchFailed(result) : false;
  const incomplete = result ? censusYearsIncomplete(result) : false;
  const geoidLabel =
    result?.geoid || (areas.length > 1 ? `${areas.length} areas` : "—");
  const series = (result?.attempted_years.length ?? 0) > 1;
  const showYear = series || new Set(areas.map((area) => area.year).filter(Boolean)).size > 1;
  const multi = areas.length > 1 || series;

  async function onCopyUrl() {
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
    <main>
      <h1>census-concierge</h1>
      <p className="lede">Ask a Census question. The table, URL, and related tables come back together.</p>
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
      <section className="pane" data-state={state}>
        {state === "idle" ? <p>Type a question to see the selected table, its URL, and alternatives.</p> : null}
        {state === "loading" ? <p>Looking up tables…</p> : null}
        {state === "error" ? <p>{error}</p> : null}
        {state === "result" && result ? (
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
            {result.answer ? <p className="answer">{result.answer}</p> : null}
            <dl className="meta">
              <dt>Table</dt>
              <dd>{result.table_id || "—"}</dd>
              <dt>Universe</dt>
              <dd>{result.universe || "—"}</dd>
              <dt>GEOID</dt>
              <dd>{geoidLabel}</dd>
            </dl>
            {areas.length === 1 && areas[0].pairs.length > 0 && !multi ? (
              <>
                <h2>Estimates</h2>
                <ul className="estimates">
                  {areas[0].pairs.map((pair) => (
                    <li key={pair.variable}>
                      {pair.variable}: {formatCensusValue(pair.estimate)} ± {formatCensusValue(pair.moe)}
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
            {multi && areas.length > 0 ? (
              <>
                <h2>Estimates</h2>
                <table className="geo-table">
                  <thead>
                    <tr>
                      {showYear ? <th>Year</th> : null}
                      <th>GEOID</th>
                      <th>Name</th>
                      <th>Variable</th>
                      <th>Estimate</th>
                      <th>MOE</th>
                    </tr>
                  </thead>
                  <tbody>
                    {areas.flatMap((area) => {
                      const pairs = area.pairs.length > 0 ? area.pairs : [{ variable: "", estimate: null, moe: null }];
                      return pairs.map((pair) => (
                        <tr key={`${area.year}:${area.geoid}:${area.name}:${pair.variable}`}>
                          {showYear ? <td>{area.year || "—"}</td> : null}
                          <td>{area.geoid || "—"}</td>
                          <td>{area.name || "—"}</td>
                          <td>{pair.variable || "—"}</td>
                          <td>{formatCensusValue(pair.estimate)}</td>
                          <td>{formatCensusValue(pair.moe)}</td>
                        </tr>
                      ));
                    })}
                  </tbody>
                </table>
              </>
            ) : null}
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
        ) : null}
      </section>
    </main>
  );
}
