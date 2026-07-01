export type AiFix = {
  type: "contrast" | "alt_text" | "aria" | "manual" | string;
  original: string | null;
  fixed: string | null;
  explanation: string;
  confidence: number;
  needs_manual_review?: boolean;
  error_kind?: string;
  grounded_in_apg?: boolean;
};

export type Violation = {
  ruleId: string;
  severity: "critical" | "serious" | "moderate" | "minor" | string;
  wcagRef: string[];
  domSnippet: string;
  ai_fix: AiFix | null;
};

export type ScanResponse = {
  scanId: string;
  url: string;
  scoreBefore: number;
  scoreAfter: number;
  status: string;
  scannedAt?: string;
  violations: Violation[];
};

export type ApiErrorBody = {
  error: { code: string; message: string; detail?: unknown };
};

export class ApiError extends Error {
  status: number;
  code: string;
  detail?: unknown;
  constructor(status: number, body: ApiErrorBody) {
    super(body.error?.message ?? `HTTP ${status}`);
    this.status = status;
    this.code = body.error?.code ?? String(status);
    this.detail = body.error?.detail;
  }
}

function apiBase(): string {
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!raw || raw.trim() === "") {
    return "http://127.0.0.1:8000";
  }
  return raw.replace(/\/+$/, "");
}

async function readError(resp: Response): Promise<ApiError> {
  let body: ApiErrorBody = { error: { code: String(resp.status), message: resp.statusText } };
  try {
    body = (await resp.json()) as ApiErrorBody;
  } catch {
    /* keep the fallback */
  }
  return new ApiError(resp.status, body);
}

export async function createScan(url: string, signal?: AbortSignal): Promise<ScanResponse> {
  const resp = await fetch(`${apiBase()}/api/scans`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
    signal,
  });
  if (!resp.ok) throw await readError(resp);
  return (await resp.json()) as ScanResponse;
}

export async function getScan(scanId: string): Promise<ScanResponse> {
  const resp = await fetch(`${apiBase()}/api/scans/${encodeURIComponent(scanId)}`);
  if (!resp.ok) throw await readError(resp);
  return (await resp.json()) as ScanResponse;
}
