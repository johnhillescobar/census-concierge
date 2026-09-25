import { useEffect, useRef } from "react";
import type { ChartSpec } from "./ask";
import { chartView, EMBED_OPTIONS } from "./chart";
import type { DatasetRow } from "./display";

export function ResultChart({
  spec,
  rows,
  unavailable,
}: {
  spec?: ChartSpec | null;
  rows: DatasetRow[];
  unavailable: boolean;
}) {
  const view = chartView(spec, rows, unavailable);
  const node = useRef<HTMLDivElement>(null);
  const payload = view.kind === "spec" ? JSON.stringify(view.spec) : "";

  useEffect(() => {
    const el = node.current;
    if (!payload || !el) {
      return;
    }
    let drop = false;
    let stop = () => undefined as void;
    void import("vega-embed").then((mod) => {
      if (drop) {
        return;
      }
      return mod.default(el, JSON.parse(payload) as Record<string, unknown>, EMBED_OPTIONS).then((result) => {
        if (drop) {
          result.finalize();
          return;
        }
        stop = () => result.finalize();
      });
    });
    return () => {
      drop = true;
      stop();
      el.replaceChildren();
    };
  }, [payload]);

  if (view.kind === "empty") {
    return null;
  }
  if (view.kind !== "spec") {
    return (
      <p className="notice" role="status">
        {view.message}
      </p>
    );
  }
  return <div ref={node} className="chart" role="img" aria-label={view.title} />;
}
