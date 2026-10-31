export function MockBadge({ label = 'MOCK DATA' }: { label?: string }) {
  return (
    <span
      className="inline-flex items-center rounded border-2 border-dashed border-fuchsia-600 px-1.5 py-0.5 text-xs font-bold uppercase tracking-wide text-fuchsia-700 dark:border-fuchsia-400 dark:text-fuchsia-300"
      title="Fake data for UI development. Not from the dataset or the pipeline."
    >
      {label}
    </span>
  );
}
