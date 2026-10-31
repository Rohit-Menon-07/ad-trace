import { CheckCircle2, CircleHelp, MinusCircle, CircleDashed } from 'lucide-react';
import type { Verdict } from '../types/api';

const STYLE: Record<Verdict, { label: string; cls: string; Icon: typeof CheckCircle2 }> = {
  APPLICABLE: { label: 'APPLICABLE', cls: 'border-green-700 bg-green-50 text-green-900 dark:bg-green-950 dark:text-green-200', Icon: CheckCircle2 },
  NOT_APPLICABLE: { label: 'NOT APPLICABLE', cls: 'border-slate-500 bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200', Icon: MinusCircle },
  UNDETERMINED: { label: 'UNDETERMINED', cls: 'border-amber-600 bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-200', Icon: CircleHelp },
  NOT_CHECKED: { label: 'NOT CHECKED', cls: 'border-blue-700 bg-blue-50 text-blue-900 dark:bg-blue-950 dark:text-blue-200', Icon: CircleDashed },
};

/** Badge carries an icon and text; colour is never the only signal. */
export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const { label, cls, Icon } = STYLE[verdict];
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded border px-2 py-0.5 text-xs font-semibold ${cls}`}>
      <Icon aria-hidden className="h-3.5 w-3.5" />
      {label}
    </span>
  );
}
