import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Flag } from 'lucide-react';
import { api } from '../api/client';

/** H13: the user can always flag an answer as wrong; it is logged with the request id. */
export function FeedbackButton({ requestId }: { requestId: string }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  const m = useMutation({ mutationFn: () => api.feedback({ request_id: requestId, reason }) });

  if (m.isSuccess) return <p className="text-sm" role="status">Thanks. Flag recorded for {requestId}.</p>;
  if (!open)
    return (
      <button type="button" onClick={() => setOpen(true)} className="inline-flex items-center gap-1 rounded border border-slate-400 px-2 py-1 text-sm hover:bg-slate-100 dark:hover:bg-slate-800">
        <Flag aria-hidden className="h-4 w-4" /> Flag as wrong
      </button>
    );
  return (
    <form
      className="flex flex-wrap items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        m.mutate();
      }}
    >
      <label htmlFor="flag-reason" className="text-sm">What is wrong?</label>
      <input id="flag-reason" value={reason} onChange={(e) => setReason(e.target.value)} required className="min-w-48 flex-1 rounded border border-slate-400 bg-transparent px-2 py-1 text-sm" />
      <button type="submit" disabled={m.isPending} className="rounded border border-slate-700 px-2 py-1 text-sm">Send</button>
      <button type="button" onClick={() => setOpen(false)} className="px-2 py-1 text-sm underline">Cancel</button>
      {m.isError && <p role="alert" className="w-full text-sm">Flag not recorded: {m.error.message}. Note the request id {requestId} instead.</p>}
    </form>
  );
}
