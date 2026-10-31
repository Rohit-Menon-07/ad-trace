/** Static placeholder blocks while data loads (pulse only when the user allows motion). */
export function Skeleton({ lines = 3, label }: { lines?: number; label: string }) {
  return (
    <div role="status" aria-label={label} className="space-y-2 motion-safe:animate-pulse">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="h-3 rounded bg-slate-200 dark:bg-slate-800" style={{ width: `${95 - ((i * 17) % 40)}%` }} />
      ))}
      <span className="sr-only">{label}</span>
    </div>
  );
}

export function ResultSkeleton() {
  return (
    <div className="rounded border border-slate-300 bg-white dark:border-slate-700 dark:bg-slate-900">
      <div className="h-14 rounded-t border-b-2 border-amber-500 bg-amber-50 dark:bg-amber-950/40" />
      <div className="space-y-6 p-4">
        <Skeleton lines={2} label="Searching the records" />
        <Skeleton lines={4} label="" />
        <Skeleton lines={3} label="" />
      </div>
    </div>
  );
}
