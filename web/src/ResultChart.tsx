import { useEffect, useRef, useState } from "react";
import type { ChartSpec } from "./ask";
import { CHART_FAIL, chartView, EMBED_OPTIONS } from "./chart";
import type { DatasetRow } from "./display";

export function ResultChart({ spec, rows, unavailable }: { spec?: ChartSpec | null; rows: DatasetRow[]; unavailable: boolean }) {
  const view = chartView(spec, rows, unavailable);
  const node = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  const payload = view.kind === "spec" ? JSON.stringify(view.spec) : "";

  useEffect(() => {
    const el = node.current;
    setFailed(false);
    if (!payload || !el) return;
    let drop = false;
    let stop = () => undefined as void;
    void import("vega-embed")
      .then((mod) =>
        drop
          ? undefined
          : mod.default(el, JSON.parse(payload) as Record<string, unknown>, EMBED_OPTIONS).then((result) => {
              if (drop) result.finalize();
              else stop = () => result.finalize();
            }),
      )
      .catch(() => {
        if (!drop) setFailed(true);
      });
    return () => {
      drop = true;
      stop();
      el.replaceChildren();
    };
  }, [payload]);

  if (view.kind === "empty") return null;
  if (view.kind !== "spec" || failed) {
    return (
      <p className="notice" role="status">
        {view.kind === "spec" ? CHART_FAIL : view.message}
      </p>
    );
  }
  return <div ref={node} className="chart" role="img" aria-label={view.title} />;
}
