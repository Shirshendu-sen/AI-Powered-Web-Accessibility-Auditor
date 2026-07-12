"use client";

import type { Violation } from "@/lib/api";
import DiffViewer from "./DiffViewer";

const SEVERITY_ORDER = ["critical", "serious", "moderate", "minor"] as const;

type Props = {
  scan: import("@/lib/api").ScanResponse;
  onExport: () => void;
};

export default function ResultsDashboard({ scan, onExport }: Props) {
  const grouped = new Map<string, Violation[]>();
  for (const sev of SEVERITY_ORDER) grouped.set(sev, []);
  for (const v of scan.violations) {
    const key = SEVERITY_ORDER.includes(v.severity as typeof SEVERITY_ORDER[number])
      ? v.severity
      : "minor";
    (grouped.get(key) ?? grouped.get("minor")!).push(v);
  }

  const delta = scan.scoreBefore - scan.scoreAfter;
  const pct =
    scan.scoreBefore === 0
      ? 0
      : Math.round(((scan.scoreBefore - scan.scoreAfter) / scan.scoreBefore) * 100);

  return (
    <section className="w-full max-w-5xl mx-auto mt-8" aria-labelledby="results-heading">
      <header className="flex flex-wrap items-start justify-between gap-4 mb-6">
        <div className="min-w-0">
          <h2 id="results-heading" className="text-2xl font-semibold text-slate-900 dark:text-slate-100">
            Results
          </h2>
          <p className="text-sm text-slate-600 dark:text-slate-400 break-all">
            {scan.url}
          </p>
        </div>
        <button
          type="button"
          onClick={onExport}
          className="rounded-md border border-slate-300 dark:border-slate-700 px-4 py-2 text-sm font-medium
                     text-slate-800 dark:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-800
                     focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2 print:hidden"
        >
          Export JSON
        </button>
      </header>

      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        <div className="border rounded-md p-3 border-slate-200 dark:border-slate-700">
          <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Score before</dt>
          <dd className="text-2xl font-semibold mt-1 text-slate-900 dark:text-slate-100">{scan.scoreBefore}</dd>
        </div>
        <div className="border rounded-md p-3 border-slate-200 dark:border-slate-700">
          <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Projected after</dt>
          <dd className="text-2xl font-semibold mt-1 text-emerald-700 dark:text-emerald-400">{scan.scoreAfter}</dd>
        </div>
        <div className="border rounded-md p-3 border-slate-200 dark:border-slate-700">
          <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Improvement</dt>
          <dd className="text-2xl font-semibold mt-1 text-slate-900 dark:text-slate-100">
            {delta} <span className="text-sm text-slate-500 dark:text-slate-400">({pct}%)</span>
          </dd>
        </div>
        <div className="border rounded-md p-3 border-slate-200 dark:border-slate-700">
          <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Status</dt>
          <dd className="text-sm font-medium mt-1 text-slate-800 dark:text-slate-200">{scan.status}</dd>
        </div>
      </dl>

      {SEVERITY_ORDER.map((sev) => {
        const items = grouped.get(sev) ?? [];
        if (items.length === 0) return null;
        return (
          <section key={sev} className="mb-8" aria-labelledby={`sev-${sev}-heading`}>
            <h3
              id={`sev-${sev}-heading`}
              className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-3 capitalize"
            >
              {sev}{" "}
              <span className="text-sm font-normal text-slate-500 dark:text-slate-400">
                ({items.length})
              </span>
            </h3>
            <div className="space-y-4">
              {items.map((v, i) => (
                <DiffViewer key={`${v.ruleId}-${i}`} violation={v} />
              ))}
            </div>
          </section>
        );
      })}

      {scan.violations.length === 0 && (
        <p className="text-slate-600 dark:text-slate-400">
          No violations found. Nothing to fix.
        </p>
      )}
    </section>
  );
}
