"use client";

import type { AiFix, Violation } from "@/lib/api";

const SEVERITY_ORDER = ["critical", "serious", "moderate", "minor"] as const;

const SEVERITY_TONE: Record<string, { chip: string; ring: string }> = {
  critical: { chip: "bg-red-100 text-red-900 border-red-300", ring: "focus:ring-red-600" },
  serious: { chip: "bg-orange-100 text-orange-900 border-orange-300", ring: "focus:ring-orange-600" },
  moderate: { chip: "bg-amber-100 text-amber-900 border-amber-300", ring: "focus:ring-amber-600" },
  minor: { chip: "bg-slate-100 text-slate-900 border-slate-300", ring: "focus:ring-slate-600" },
};

function severityTone(sev: string) {
  return SEVERITY_TONE[sev] ?? SEVERITY_TONE.minor;
}

function needsManualReview(f: AiFix | null | undefined): boolean {
  if (!f) return true;
  return Boolean(f.needs_manual_review);
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  const tone =
    value >= 0.8 ? "bg-emerald-600" : value >= 0.5 ? "bg-amber-500" : "bg-slate-400";
  return (
    <div
      className="w-24 h-2 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden"
      role="img"
      aria-label={`Confidence ${(value * 100).toFixed(0)} percent`}
    >
      <div className={`${tone} h-full`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function DiffViewer({ violation }: { violation: Violation }) {
  const fix = violation.ai_fix;
  const manual = needsManualReview(fix);

  return (
    <article className="border border-slate-200 dark:border-slate-700 rounded-md bg-white dark:bg-slate-900 overflow-hidden">
      <header className="flex flex-wrap items-center gap-3 px-4 py-3 border-b border-slate-200 dark:border-slate-700">
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded-full border text-xs font-medium ${
            severityTone(violation.severity).chip
          }`}
        >
          {violation.severity}
        </span>
        <span className="font-mono text-sm text-slate-700 dark:text-slate-300">
          {violation.ruleId}
        </span>
        {violation.wcagRef.length > 0 && (
          <span className="text-xs text-slate-500 dark:text-slate-400">
            WCAG: {violation.wcagRef.join(", ")}
          </span>
        )}
        {manual && (
          <span className="ml-auto inline-flex items-center px-2 py-0.5 rounded-md bg-purple-100 text-purple-900 border border-purple-300 text-xs font-medium">
            needs manual review
          </span>
        )}
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-0 border-b border-slate-200 dark:border-slate-700">
        <section className="p-4 md:border-r border-slate-200 dark:border-slate-700">
          <h3 className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">
            Original
          </h3>
          <pre className="text-xs leading-relaxed whitespace-pre-wrap break-all font-mono
                          bg-slate-50 dark:bg-slate-950 rounded p-2 overflow-x-auto max-h-48
                          text-slate-800 dark:text-slate-200"
               aria-label="Original DOM snippet">
            {violation.domSnippet || "(no snippet)"}
          </pre>
          {fix?.type === "contrast" && fix.original && (
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              Foreground: <code className="font-mono">{fix.original}</code>
            </p>
          )}
          {fix?.type === "alt_text" && fix.original && (
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400 break-all">
              Image: <code className="font-mono">{fix.original}</code>
            </p>
          )}
        </section>

        <section className="p-4">
          <h3 className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">
            Fixed
          </h3>
          {manual ? (
            <div className="bg-purple-50 dark:bg-purple-950/40 border border-purple-200 dark:border-purple-800
                            rounded p-3 text-sm text-purple-900 dark:text-purple-200">
              <p className="font-medium">This fix needs a human reviewer.</p>
              {fix?.error_kind && (
                <p className="mt-1 text-xs">
                  Reason: <code className="font-mono">{fix.error_kind}</code>
                </p>
              )}
            </div>
          ) : (
            <pre className="text-xs leading-relaxed whitespace-pre-wrap break-all font-mono
                            bg-emerald-50 dark:bg-emerald-950/40 rounded p-2 overflow-x-auto max-h-48
                            text-emerald-900 dark:text-emerald-200"
                 aria-label="Suggested fix">
              {fix?.fixed ?? "(no fix)"}
            </pre>
          )}
          {fix?.type === "contrast" && fix.fixed && (
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              Foreground: <code className="font-mono">{fix.fixed}</code>
            </p>
          )}
        </section>
      </div>

      <footer className="px-4 py-3 flex flex-wrap items-center gap-4 text-sm">
        <p className="flex-1 text-slate-700 dark:text-slate-300 min-w-0">
          {fix?.explanation ?? "No explanation available."}
        </p>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-xs text-slate-500 dark:text-slate-400">Confidence</span>
          <ConfidenceBar value={fix?.confidence ?? 0} />
        </div>
      </footer>
    </article>
  );
}

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
