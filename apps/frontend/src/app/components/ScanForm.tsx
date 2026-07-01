"use client";

import { useState } from "react";

type Props = {
  onSubmit: (url: string) => void;
  isLoading: boolean;
};

export default function ScanForm({ onSubmit, isLoading }: Props) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const trimmed = url.trim();
    if (!trimmed) {
      setError("Enter a URL to scan.");
      return;
    }
    try {
      const parsed = new URL(trimmed);
      if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
        setError("Only http and https URLs are allowed.");
        return;
      }
    } catch {
      setError("That doesn't look like a valid URL.");
      return;
    }
    onSubmit(trimmed);
  }

  return (
    <form
      onSubmit={handleSubmit}
      aria-labelledby="scan-form-heading"
      className="w-full max-w-3xl mx-auto"
    >
      <h1
        id="scan-form-heading"
        className="text-3xl font-semibold mb-2 text-slate-900 dark:text-slate-100"
      >
        Accessibility Auditor
      </h1>
      <p className="text-slate-600 dark:text-slate-400 mb-6">
        Paste a public URL. We&apos;ll scan for WCAG violations and generate before/after fixes.
      </p>
      <div className="flex flex-col sm:flex-row gap-3">
        <label htmlFor="scan-url-input" className="sr-only">
          URL to scan
        </label>
        <input
          id="scan-url-input"
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com"
          className="flex-1 rounded-md border border-slate-300 dark:border-slate-700 px-4 py-3 text-base
                     bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100
                     focus:outline-none focus:ring-2 focus:ring-blue-600"
          disabled={isLoading}
          aria-invalid={error !== null}
          aria-describedby={error ? "scan-url-error" : undefined}
          required
        />
        <button
          type="submit"
          disabled={isLoading}
          className="rounded-md bg-blue-700 hover:bg-blue-800 focus:bg-blue-800 text-white
                     px-6 py-3 font-medium disabled:opacity-50 disabled:cursor-not-allowed
                     focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
        >
          {isLoading ? "Scanning…" : "Scan"}
        </button>
      </div>
      {error && (
        <p id="scan-url-error" role="alert" className="mt-2 text-sm text-red-700 dark:text-red-400">
          {error}
        </p>
      )}
      {isLoading && (
        <p role="status" aria-live="polite" className="mt-4 text-slate-600 dark:text-slate-400">
          Running scanner, generating fixes, computing score… this can take 10–20 seconds.
        </p>
      )}
    </form>
  );
}
