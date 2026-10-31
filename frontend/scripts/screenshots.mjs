// Playwright screenshots of the four result states into docs/screens/ (run by `python scripts/tasks.py screens`).
// Drives the real UI through the form; fails on any console error or page error.
//
//   node scripts/screenshots.mjs <base-url> <state>...   states: answered refused needs_clarification partial coverage evaluation
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const OUT = resolve(dirname(fileURLToPath(import.meta.url)), '../../docs/screens');
const [base, ...states] = process.argv.slice(2);

const A330 = { query: 'Which proposed ADs concern the radio management panels on our A330-243?', make: 'Airbus SAS', model: 'A330-243' };
const SCENARIOS = {
  answered: { ...A330, expect: 'ANSWERED', openCitation: true },
  partial: { ...A330, expect: 'PARTIAL', expandDropped: true },
  refused: { query: 'What torque should I apply to the RMP mounting screws on our A330-243?', make: 'Airbus SAS', model: 'A330-243', expect: 'CANNOT COMPLETE' },
  needs_clarification: { query: 'What proposed ADs affect the A330?', make: 'Airbus SAS', model: 'A330', expect: 'NEEDS CLARIFICATION' },
};

async function shoot(browser, state, { width, height, dark, suffix = '' }) {
  const s = SCENARIOS[state];
  const page = await browser.newPage({ viewport: { width, height }, colorScheme: dark ? 'dark' : 'light' });
  const errors = [];
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.addInitScript((d) => window.localStorage.setItem('adtrace-theme', d ? 'dark' : 'light'), dark);
  await page.goto(base);
  if (state === 'coverage' || state === 'evaluation') {
    await page.getByRole('navigation', { name: 'Pages' }).getByRole('button', { name: state === 'coverage' ? 'Coverage' : 'Evaluation' }).click();
    await page.getByRole('heading', { level: 2 }).first().waitFor();
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: `${OUT}/${state}${suffix}.png`, fullPage: true });
    await page.close();
    if (errors.length) throw new Error(`${state}: console errors:\n${errors.join('\n')}`);
    console.log(`wrote ${OUT}/${state}${suffix}.png`);
    return;
  }
  await page.locator('#q').fill(s.query);
  await page.locator('#make').selectOption(s.make);
  await page.locator('#model').fill(s.model);
  await page.getByRole('form', { name: 'Search proposed ADs' }).getByRole('button', { name: 'Search' }).click();
  const result = page.getByRole('article', { name: 'Result' });
  await result.waitFor({ timeout: 60000 });
  const pill = await result.locator('header').innerText();
  if (!pill.includes(s.expect)) throw new Error(`${state}: expected status ${s.expect}, got header "${pill}"`);
  if (s.openCitation) {
    await result.getByRole('button', { name: /^Open source 1:/ }).first().click();
    await page.getByRole('heading', { name: /^Source / }).waitFor();
    await page.getByRole('button', { name: 'Copy citation' }).waitFor();
  }
  if (s.expandDropped) await result.getByText('Show what was removed and why').click();
  await page.waitForLoadState('networkidle');
  const file = `${OUT}/${state}${suffix}.png`;
  await page.screenshot({ path: file, fullPage: false });
  await page.close();
  if (errors.length) throw new Error(`${state}: console errors:\n${errors.join('\n')}`);
  console.log(`wrote ${file}`);
}

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
try {
  for (const state of states) {
    await shoot(browser, state, { width: 1440, height: 900, dark: false });
    if (state === 'answered') await shoot(browser, state, { width: 1280, height: 720, dark: true, suffix: '_1280_dark' });
  }
} finally {
  await browser.close();
}
