"use client";

import type { AiFix, Violation } from "@/lib/api";

const SEVERITY_TONE: Record<string, { chip: string }> = {
  critical: { chip: "bg-red-100 text-red-900 border-red-300" },
  serious: { chip: "bg-orange-100 text-orange-900 border-orange-300" },
  moderate: { chip: "bg-amber-100 text-amber-900 border-amber-300" },
  minor: { chip: "bg-slate-100 text-slate-900 border-slate-300" },
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

export default function DiffViewer({ violation }: { violation: Violation }) {
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
