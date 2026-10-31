export interface DrawerTarget {
  evidenceId: string;
  spanStart?: number | null;
  spanEnd?: number | null;
  /** Verified quote behind a claim citation (used by "Copy citation"). */
  quote?: string | null;
}

interface Props {
  n: number | string;
  target: DrawerTarget;
  active: boolean;
  onOpen: (t: DrawerTarget) => void;
}

export function CitationChip({ n, target, active, onOpen }: Props) {
  return (
    <button
      type="button"
      onClick={() => onOpen(target)}
      aria-label={`Open source ${n}: ${target.evidenceId}`}
      aria-pressed={active}
      title={target.evidenceId}
      className={`mx-0.5 inline-flex min-w-6 items-center justify-center rounded border px-1 align-baseline font-mono text-xs font-semibold ${
        active
          ? 'border-blue-700 bg-blue-700 text-white dark:border-blue-400 dark:bg-blue-400 dark:text-slate-950'
          : 'border-blue-700 bg-white text-blue-800 hover:bg-blue-50 dark:border-blue-400 dark:bg-slate-900 dark:text-blue-300 dark:hover:bg-slate-800'
      }`}
    >
      {n}
    </button>
  );
}
