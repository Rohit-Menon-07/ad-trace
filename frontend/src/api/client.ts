// Single data-access layer. In this build every call is served from src/mocks (MOCK).
// When the FastAPI backend exists, set USE_MOCK = false and the same functions hit /api/*.

import type { EvalResults, MetaResponse, RecordDetail, SearchRequest, SearchResponse } from '../types/api';
import { MOCK_EVAL, MOCK_MAKES, MOCK_META, MOCK_MODELS } from '../mocks/meta';
import { MOCK_RECORDS } from '../mocks/records';
import { MOCK_SCENARIOS, type ScenarioKey } from '../mocks/scenarios';

export const USE_MOCK = true;

const MOCK_DELAY_MS = 250;

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(structuredClone(value)), MOCK_DELAY_MS));
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path} failed: HTTP ${res.status}`);
  return (await res.json()) as T;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!res.ok) throw new Error(`${path} failed: HTTP ${res.status}`);
  return (await res.json()) as T;
}

/** `scenario` is only used in MOCK mode, where it picks the canned response. */
export function search(req: SearchRequest, scenario: ScenarioKey): Promise<SearchResponse> {
  if (USE_MOCK) return delay(MOCK_SCENARIOS[scenario].response);
  return postJson<SearchResponse>('/api/search', req);
}

export function getRecord(recordId: string): Promise<RecordDetail> {
  if (USE_MOCK) {
    const rec = MOCK_RECORDS[recordId];
    return rec ? delay(rec) : Promise.reject(new Error(`MOCK record ${recordId} not found`));
  }
  return getJson<RecordDetail>(`/api/records/${encodeURIComponent(recordId)}`);
}

export function getMeta(): Promise<MetaResponse> {
  return USE_MOCK ? delay(MOCK_META) : getJson<MetaResponse>('/api/meta');
}

export function getMakes(): Promise<string[]> {
  return USE_MOCK ? delay(MOCK_MAKES) : getJson<string[]>('/api/vocab/makes');
}

export function getModels(make: string): Promise<string[]> {
  if (USE_MOCK) return delay(MOCK_MODELS[make] ?? []);
  return getJson<string[]>(`/api/vocab/models?make=${encodeURIComponent(make)}`);
}

export function getEval(): Promise<EvalResults> {
  return USE_MOCK ? delay(MOCK_EVAL) : getJson<EvalResults>('/api/eval/latest');
}

export function sendFeedback(requestId: string, reason: string): Promise<{ ok: boolean }> {
  if (USE_MOCK) {
    console.info('MOCK feedback (not persisted)', { requestId, reason });
    return delay({ ok: true });
  }
  return postJson<{ ok: boolean }>('/api/feedback', { request_id: requestId, reason });
}
