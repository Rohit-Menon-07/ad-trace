import { AlertTriangle } from 'lucide-react';

/** H13 + SPEC §2: shown on every result state, including refusals. */
export function ProposedBanner({ disclaimer }: { disclaimer: string }) {
  return (
    <div role="note" className="flex gap-3 rounded-t border-b-2 border-amber-500 bg-amber-50 px-4 py-3 text-amber-950 dark:bg-amber-950/40 dark:text-amber-100">
      <AlertTriangle aria-hidden className="mt-0.5 h-5 w-5 shrink-0" />
      <div>
        <p className="text-sm font-bold uppercase tracking-wide">Proposed rulemaking, not in force</p>
        <p className="text-sm">{disclaimer}</p>
      </div>
    </div>
  );
}
