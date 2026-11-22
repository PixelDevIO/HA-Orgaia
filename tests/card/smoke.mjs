// Draws every view of the Orgaia card in a real browser, from a board the integration's tests wrote,
// and taps a few buttons. Run: node tests/card/smoke.mjs (needs Playwright with Chromium).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const here = dirname(fileURLToPath(import.meta.url));
const card = readFileSync(join(here, '../../custom_components/orgaia/www/orgaia-card.js'), 'utf8');
const board = JSON.parse(readFileSync(join(here, 'board.json'), 'utf8'));

const page = await (await chromium.launch()).newPage();
const errors = [];
page.on('pageerror', (err) => errors.push(String(err)));
page.on('console', (msg) => msg.type() === 'error' && errors.push(msg.text()));
await page.setContent('<!doctype html><html><body></body></html>');
await page.evaluate((board) => {
  window.calls = [];
  window.board = { ...board, can_write: true };
  window.makeHass = (language) => ({
    language,
    connection: {
      subscribeMessage: (cb) => {
        setTimeout(() => cb(window.board), 0);
        return Promise.resolve(() => undefined);
      },
    },
    callService: async (domain, service, data) => {
      window.calls.push({ domain, service, data });
    },
  });
}, board);
await page.addScriptTag({ content: card });

async function show(config, language = 'de') {
  return page.evaluate(
    async ({ config, language }) => {
      document.body.innerHTML = '';
      const el = document.createElement('orgaia-card');
      el.setConfig(config);
      document.body.appendChild(el);
      el.hass = window.makeHass(language);
      await new Promise((r) => setTimeout(r, 30));
      window.card = el;
      return el.shadowRoot.textContent;
    },
    { config, language },
  );
}

function expect(ok, what) {
  if (!ok) {
    console.error('FAILED:', what);
    process.exitCode = 1;
  } else console.log('ok', what);
}

const lists = await show({ view: 'lists' });
expect(lists.includes('Haushalt') && lists.includes('Einkauf'), 'lists view shows both lists');
expect(lists.includes('Brot & Backwaren') || lists.includes('Bakery'), 'shopping grouped by aisle');
expect(lists.includes('Wocheneinkauf'), 'fixed purchase offered');
expect(lists.includes('nicht bekommen'), 'article not got is marked');

// Nothing in nobody's name: first a person, then + on the bread.
await page.evaluate(() => window.card.shadowRoot.querySelector('[data-act="step"][data-step="1"]').click());
await page.waitForTimeout(30);
expect((await page.evaluate(() => window.calls.length)) === 0, 'nothing is written in nobody\'s name');
const asked = await page.evaluate(() => window.card.shadowRoot.textContent);
expect(asked.includes('Wer war’s?') && !(await page.evaluate(() => !!window.card.shadowRoot.querySelector('.error'))), 'asks who it was, without an error');
// The name finishes the tap that was waiting.
await page.evaluate(() => window.card.shadowRoot.querySelector('[data-act="who"]').click());
await page.waitForTimeout(30);
expect((await page.evaluate(() => window.calls.map((c) => c.service).join())) === 'set_quantity', 'the waiting tap is done once a name is tapped');
await page.evaluate(() => window.card.shadowRoot.querySelector('[data-act="set"]').click());
await page.waitForTimeout(30);
const calls = await page.evaluate(() => window.calls.map((c) => c.service));
expect(calls.join() === 'set_quantity,add_fixed_purchase', 'plus and fixed purchase call the services');

// A new card shows today; Tinte is one choice; the ready-made dashboard is built from the same card.
expect((await page.evaluate(() => customElements.get('orgaia-card').getStubConfig())).view === 'today', 'a new card starts with today');
await show({ view: 'today', style: 'tinte' });
expect(await page.evaluate(() => getComputedStyle(window.card.shadowRoot.querySelector('ha-card')).borderRadius === '0px'), 'Tinte has no round corners');
const dash = await page.evaluate(() => customElements.get('ll-strategy-dashboard-orgaia').generate({ entry: 'abc' }, window.makeHass('de')));
expect(dash.views[0].sections.length === 3 && dash.views[0].sections.every((s) => s.cards[1].type === 'custom:orgaia-card' && s.cards[1].entry === 'abc' && s.cards[1].style === 'tinte'), 'dashboard strategy: today, shopping, week');

const today = await show({ view: 'today', show_tomorrow: true });
expect(today.includes('Heute') && today.includes('Morgen') && today.includes('Training'), 'today view shows today and tomorrow');
expect(today.includes('noch offen'), 'today view says a drive is still open');

const agenda = await show({ view: 'agenda' });
expect(agenda.includes('Ich fahre hin'), 'agenda offers to take a drive');
await page.evaluate(() => window.card.shadowRoot.querySelector('[data-act="who"]').click());
await page.evaluate(() => window.card.shadowRoot.querySelector('[data-act="drive"]').click());
await page.waitForTimeout(30);
const drive = await page.evaluate(() => window.calls.at(-1));
expect(drive.service === 'take_drive' && drive.data.which === 'to' && drive.data.item === 'e2', 'take_drive is called');

for (const view of ['shopping', 'tasks', 'timetable', 'roster']) {
  const text = await show({ view }, 'en');
  expect(text.length > 0, `${view} view draws`);
}

await page.evaluate(() => (window.board = { ...window.board, version: '0.0.1' }));
// Another group, so the card asks the integration afresh instead of using what it already knows.
const old = await show({ view: 'lists', entry: 'other' });
expect(old.includes('Lade die Seite neu'), 'an outdated card asks to reload');

expect(!errors.length, 'no errors in the browser' + (errors.length ? ': ' + errors.join(' | ') : ''));
process.exit(process.exitCode || 0);
