"use client";

import { useState } from "react";
import { ApiError, createScan, type ScanResponse } from "@/lib/api";
import ScanForm from "./components/ScanForm";
import ResultsDashboard from "./components/ResultsDashboard";

export default function Home() {
  const [scan, setScan] = useState<ScanResponse | null>(null);
  const [isLoading, setLoading] = useState(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  async function handleScan(url: string) {
    setLoading(true);
    setErrMsg(null);
    setScan(null);
    try {
      const result = await createScan(url);
      setScan(result);
    } catch (e) {
      if (e instanceof ApiError) {
        setErrMsg(`${e.code}: ${e.message}`);
      } else {
        setErrMsg(e instanceof Error ? e.message : "Unknown error");
      }
    } finally {
      setLoading(false);
    }
  }

  function handleExport() {
    if (!scan) return;
    const blob = new Blob([JSON.stringify(scan, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `accessibility-scan-${scan.scanId}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="min-h-full flex-1 px-4 sm:px-6 lg:px-10 py-10 bg-slate-50 dark:bg-slate-950">
      <ScanForm onSubmit={handleScan} isLoading={isLoading} />
      {errMsg && (
        <p
          role="alert"
          className="mt-6 max-w-3xl mx-auto rounded-md border border-red-300 dark:border-red-800
                     bg-red-50 dark:bg-red-950/40 px-4 py-3 text-red-800 dark:text-red-200"
        >
          {errMsg}
        </p>
      )}
      {scan && <ResultsDashboard scan={scan} onExport={handleExport} />}
    </main>
  );
}
