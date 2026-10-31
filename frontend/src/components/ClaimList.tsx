import { ShieldCheck, ShieldAlert } from 'lucide-react';
import type { Claim } from '../types/api';
import { CitationChip, type DrawerTarget } from './CitationChip';

interface Props {
  claims: Claim[];
  numbering: Map<string, number>;
  activeId: string | null;
  onOpen: (t: DrawerTarget) => void;
}

export function ClaimList({ claims, numbering, activeId, onOpen }: Props) {
  if (claims.length === 0) return null;
  return (
    <section aria-labelledby="claims-h">
      <h3 id="claims-h" className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-400">
        What the records say
      </h3>
      <ol className="space-y-2">
        {claims.map((c, i) => (
          <li key={i} className="flex gap-2 text-sm leading-relaxed">
            {c.verification === 'verified' ? (
              <ShieldCheck aria-label="Verified against source" className="mt-0.5 h-4 w-4 shrink-0 text-green-700 dark:text-green-400" />
            ) : (
              <ShieldAlert aria-label="Partially verified" className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
            )}
            <span>
              {c.text}
              {c.verification === 'partial' && (
                <span className="ml-1 rounded border border-amber-600 px-1 text-xs font-semibold text-amber-800 dark:text-amber-300">PARTIALLY VERIFIED</span>
              )}
              {c.citations.map((cit) => (
                <CitationChip
                  key={cit.evidence_id}
                  n={numbering.get(cit.evidence_id) ?? '?'}
                  active={activeId === cit.evidence_id}
                  target={{ evidenceId: cit.evidence_id, spanStart: cit.span_start, spanEnd: cit.span_end }}
                  onOpen={onOpen}
                />
              ))}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
