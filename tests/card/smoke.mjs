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
// The server speaks English; the aisles follow whoever looks at the card.
expect(lists.includes('Brot & Backwaren') && !lists.includes('Bakery'), 'shopping grouped by aisle, in the viewer\'s language');
expect(lists.includes('Wocheneinkauf'), 'fixed purchase offered');
expect(lists.includes('nicht da'), 'article not there is marked');
expect(lists.includes('In Bearbeitung') && !lists.includes('Wird geschrieben'), 'the list speaks as the app does');
expect(lists.includes('Wer bist du?'), 'a card of its own still asks who you are, as before');
// One field for the article: "2 Brot" is understood as it is.
expect((await page.evaluate(() => window.card.shadowRoot.querySelectorAll('form input').length)) === 1, 'no quantity field beside the article');
expect((await show({ view: 'shopping' }, 'en')).includes('Bakery'), 'aisles in English for an English user');
await show({ view: 'lists' });

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
await page.evaluate(async () => {
  const input = window.card.shadowRoot.querySelector('form input.title');
  input.value = '2 Brot';
  input.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
  window.card.shadowRoot.querySelector('form').requestSubmit();
  await new Promise((r) => setTimeout(r, 30));
});
const article = await page.evaluate(() => window.calls.at(-1));
expect(article.service === 'add_article' && article.data.title === '2 Brot' && !('quantity' in article.data), 'an article is added as typed');

// A new card shows today; Tinte is one choice; the ready-made dashboard is built from the same card.
expect((await page.evaluate(() => customElements.get('orgaia-card').getStubConfig())).view === 'today', 'a new card starts with today');
await show({ view: 'today', style: 'tinte' });
expect(await page.evaluate(() => getComputedStyle(window.card.shadowRoot.querySelector('ha-card')).borderRadius === '0px'), 'Tinte has no round corners');
const dash = await page.evaluate(() => customElements.get('ll-strategy-dashboard-orgaia').generate({ entry: 'abc' }, window.makeHass('de')));
expect(dash.views[0].sections.length === 3 && dash.views[0].sections.every((s) => s.cards[1].type === 'custom:orgaia-card' && s.cards[1].entry === 'abc' && s.cards[1].style === 'tinte'), 'dashboard strategy: today, shopping, week');
expect(dash.views[0].sections.every((s) => s.cards[1].ask === 'tap' && s.cards[1].share_person === true) && dash.views[0].sections[0].cards[1].show_today_word === false, 'dashboard: one name for the page, asked after a tap, no second "Heute"');
// The settings choose the look and the parts; each timetable gets a place of its own, the order is fixed.
const picked = await page.evaluate(async () => {
  const saved = window.board.timetables;
  window.board.timetables = [{ id: 't1', name: 'Lena' }, { id: 't2', name: 'Tom' }];
  const out = await customElements.get('ll-strategy-dashboard-orgaia').generate({ entry: 'xyz', style: 'ha', sections: ['roster', 'timetable', 'agenda', 'bogus'] }, window.makeHass('de'));
  window.board.timetables = saved;
  return out.views[0].sections.map((s) => [s.cards[0].heading, s.cards[1].view, s.cards[1].plan || '', 'style' in s.cards[1], s.column_span || 1]);
});
expect(JSON.stringify(picked) === JSON.stringify([['Demnächst', 'agenda', '', false, 2], ['Lena', 'timetable', 't1', false, 1], ['Tom', 'timetable', 't2', false, 1], ['Dienstplan', 'roster', '', false, 2]]), `dashboard: chosen parts in the Home Assistant look (${JSON.stringify(picked)})`);

// The ready-made dashboard: several cards of one group, as the strategy makes them.
await page.evaluate(async (dash) => {
  window.calls = [];
  document.body.innerHTML = '';
  window.cards = dash.views[0].sections.map((s) => {
    const el = document.createElement('orgaia-card');
    el.setConfig({ ...s.cards[1], entry: undefined });
    document.body.appendChild(el);
    el.hass = window.makeHass('de');
    return el;
  });
  await new Promise((r) => setTimeout(r, 30));
}, dash);
const texts = () => page.evaluate(() => window.cards.map((c) => c.shadowRoot.textContent));
let [dToday, dShop, dWeek] = await texts();
expect(![dToday, dShop, dWeek].some((t) => t.includes('Wer bist du?')), 'dashboard: nobody is asked ahead');
expect(!/Heute\s*·/.test(dToday) && dToday.includes('Morgen ·'), 'dashboard: today without a second "Heute"');
await page.evaluate(() => window.cards[1].shadowRoot.querySelector('[data-act="tick"]').click());
await page.waitForTimeout(30);
[dToday, dShop, dWeek] = await texts();
expect(dShop.includes('Wer war’s?') && !dWeek.includes('Wer war’s?'), 'dashboard: "who was it?" only after the tap, where it was');
await page.evaluate(() => window.cards[1].shadowRoot.querySelector('[data-act="who"]').click());
await page.waitForTimeout(30);
[dToday, dShop, dWeek] = await texts();
expect((await page.evaluate(() => window.calls.map((c) => c.service).join())) === 'set_done', 'dashboard: the name finishes the tick');
expect(dShop.includes('Abhaken als Anna') && dWeek.includes('Abhaken als Anna'), 'dashboard: the name counts for the other cards too');
await page.evaluate(() => window.cards[2].shadowRoot.querySelector('[data-act="drive"]').click());
await page.waitForTimeout(30);
const shared = await page.evaluate(() => window.calls.at(-1));
expect(shared.service === 'take_drive' && shared.data.person === board.persons[0].id, 'dashboard: the week takes a drive without asking again');
expect(!(await texts())[2].includes('Wer war’s?'), 'dashboard: no second question');
await page.evaluate(() => window.cards[2].shadowRoot.querySelector('[data-act="notme"]').click());
await page.waitForTimeout(30);
expect(!(await texts()).some((t) => t.includes('Abhaken als')), '"not you?" forgets the name on all cards');

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
