import { useQuery } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { api } from '../api/client';
import type { SearchRequest } from '../types/api';

interface Props {
  value: SearchRequest;
  onChange: (v: SearchRequest) => void;
  onSubmit: () => void;
  busy: boolean;
}

const input = 'w-full rounded border border-slate-400 bg-white px-2 py-1.5 text-sm dark:border-slate-600 dark:bg-slate-950';
const labelCls = 'mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-700 dark:text-slate-300';

export function QueryForm({ value, onChange, onSubmit, busy }: Props) {
  const makes = useQuery({ queryKey: ['makes'], queryFn: api.makes });
  const make = value.make ?? '';
  const models = useQuery({ queryKey: ['models', make], queryFn: () => api.models(make), enabled: make !== '' });
  const set = (patch: Partial<SearchRequest>) => onChange({ ...value, ...patch });

  return (
    <form
      aria-label="Search proposed ADs"
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <div>
        <label htmlFor="q" className={labelCls}>Question</label>
        <textarea id="q" rows={4} className={input} value={value.query} onChange={(e) => set({ query: e.target.value })} placeholder="e.g. Which proposed ADs concern the radio management panels on our A330-243?" />
      </div>

      <fieldset className="space-y-3 rounded border border-slate-300 p-3 dark:border-slate-700">
        <legend className="px-1 text-sm font-semibold">Aircraft configuration</legend>
        <p className="text-xs text-slate-600 dark:text-slate-400">These fields override anything parsed from the question.</p>
        <div>
          <label htmlFor="make" className={labelCls}>Make</label>
          <select id="make" className={input} value={make} onChange={(e) => set({ make: e.target.value || null, model: null })}>
            <option value="">Any make</option>
            {makes.data?.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="model" className={labelCls}>Model</label>
          <input id="model" list="model-options" className={input} value={value.model ?? ''} onChange={(e) => set({ model: e.target.value || null })} placeholder={make ? 'Type or pick a model' : 'Choose a make first'} autoComplete="off" />
          <datalist id="model-options">
            {models.data?.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
        </div>
        <div>
          <label htmlFor="serial" className={labelCls}>Serial (MSN), optional</label>
          <input id="serial" className={input} value={value.serial ?? ''} onChange={(e) => set({ serial: e.target.value || null })} placeholder="e.g. 1234" />
        </div>
      </fieldset>

      <div>
        <label htmlFor="asof" className={labelCls}>As of</label>
        <input id="asof" type="date" className={input} value={value.as_of ?? ''} onChange={(e) => set({ as_of: e.target.value || null })} />
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">Drives comment-period OPEN/CLOSED status.</p>
      </div>

      <button type="submit" disabled={busy} className="inline-flex w-full items-center justify-center gap-2 rounded bg-slate-900 px-3 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-60 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300">
        <Search aria-hidden className="h-4 w-4" /> {busy ? 'Searching…' : 'Search'}
      </button>
    </form>
  );
}
