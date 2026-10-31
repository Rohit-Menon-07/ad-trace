import { useEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';
import { USE_MOCK } from './api/client';
import { MockBadge } from './components/MockBadge';
import { CoveragePage } from './pages/CoveragePage';
import { EvaluationPage } from './pages/EvaluationPage';
import { SearchPage } from './pages/SearchPage';

type Page = 'search' | 'coverage' | 'evaluation';
const PAGES: { id: Page; label: string }[] = [
  { id: 'search', label: 'Search' },
  { id: 'coverage', label: 'Coverage' },
  { id: 'evaluation', label: 'Evaluation' },
];

export default function App() {
  const [page, setPage] = useState<Page>('search');
  const [dark, setDark] = useState(() => window.matchMedia('(prefers-color-scheme: dark)').matches);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
  }, [dark]);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <header className="border-b border-slate-300 bg-white dark:border-slate-700 dark:bg-slate-900">
        <div className="mx-auto flex max-w-[1500px] flex-wrap items-center gap-4 px-4 py-3">
          <h1 className="text-lg font-bold tracking-tight">AD Trace</h1>
          <span className="text-xs text-slate-600 dark:text-slate-400">FAA AD proposals: find, check applicability, cite</span>
          {USE_MOCK && <MockBadge label="MOCK MODE: no backend" />}
          <nav aria-label="Pages" className="ml-auto flex gap-1">
            {PAGES.map((p) => (
              <button
                key={p.id}
                type="button"
                aria-current={page === p.id ? 'page' : undefined}
                onClick={() => setPage(p.id)}
                className={`rounded px-3 py-1 text-sm ${page === p.id ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900' : 'hover:bg-slate-100 dark:hover:bg-slate-800'}`}
              >
                {p.label}
              </button>
            ))}
          </nav>
          <button
            type="button"
            onClick={() => setDark((d) => !d)}
            aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}
            className="rounded p-1.5 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            {dark ? <Sun aria-hidden className="h-4 w-4" /> : <Moon aria-hidden className="h-4 w-4" />}
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-[1500px] p-4">
        {page === 'search' && <SearchPage />}
        {page === 'coverage' && <CoveragePage />}
        {page === 'evaluation' && <EvaluationPage />}
      </main>
    </div>
  );
}
