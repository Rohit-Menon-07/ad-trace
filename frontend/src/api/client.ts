// Single data-access layer: typed fetch wrappers for the FastAPI backend (SPEC §7).
// Requests go to /api/*, which Vite proxies to http://localhost:8000 in dev.
// Payloads carry `mock: false` from the real pipeline; `mock: true` (test fixtures only) shows a MOCK tag.

import type {
  EvalResults,
  FeedbackRequest,
  FeedbackResponse,
  HealthResponse,
  MetaResponse,
  RecordDetail,
  SearchRequest,
  SearchResponse,
} from '../types/api';

export class ApiError extends Error {
  readonly status: number;
  constructor(path: string, status: number, detail: string) {
    super(`${path} failed: HTTP ${status}${detail ? ` (${detail})` : ''}`);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError(path, 0, 'backend unreachable; is `make dev` running?');
  }
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new ApiError(path, res.status, body.slice(0, 200));
  }
  return (await res.json()) as T;
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
}

export const api = {
  health: () => request<HealthResponse>('/api/health'),
  meta: () => request<MetaResponse>('/api/meta'),
  makes: () => request<string[]>('/api/vocab/makes'),
  models: (make: string) => request<string[]>(`/api/vocab/models?make=${encodeURIComponent(make)}`),
  search: (req: SearchRequest) => post<SearchResponse>('/api/search', req),
  record: (recordId: string) => request<RecordDetail>(`/api/records/${encodeURIComponent(recordId)}`),
  evalLatest: () => request<EvalResults>('/api/eval/latest'),
  feedback: (body: FeedbackRequest) => post<FeedbackResponse>('/api/feedback', body),
};
