/*
 * Orgaia card: the lists of a group on a dashboard, to tick off and to add to.
 *
 * A dashboard on the wall belongs to nobody, so the card first asks who you are: tap your name, then
 * tick off. The app shows that name with the note "via Home Assistant". After a while without a tap
 * the card forgets who it was, so the next one at the display does not tick off in somebody else's name.
 *
 * It comes with the Orgaia integration; no build step, no dependencies.
 */

const TEXT = {
  en: {
    who: 'Who are you?',
    whoFirst: 'First tap who you are.',
    readOnly: 'Display only. An admin can allow ticking off and adding in the Orgaia app under Manage › Home Assistant.',
    notLoaded: 'The group is not connected right now.',
    offline: 'Orgaia is not reachable. This is the last state.',
    empty: 'Nothing open.',
    emptyShop: 'Nothing on the list.',
    addArticle: 'Add an article',
    addTask: 'Add a task',
    qty: 'Quantity',
    add: 'Add',
    draft: 'Being written',
    ready: 'Released',
    readyBy: 'Released by {name}',
    going: '{name} is shopping',
    until: 'by {date}',
    release: 'Release',
    withdraw: 'Take back',
    take: "I'll do it",
    drop: 'Not after all',
    finish: 'Shopping done',
    isNew: 'new',
    overdue: 'overdue',
    today: 'today',
    tomorrow: 'tomorrow',
    doneBy: 'done by {name}',
    bought: 'Bought',
    done: 'Done',
    failed: 'That did not work.',
    notYou: 'Not you? Tap your name.',
    title: 'Title',
    entry: 'Group',
    showDone: 'Show done tasks',
    addTasks: 'Allow adding tasks',
    forget: 'Forget who it was after (seconds)',
  },
  de: {
    who: 'Wer bist du?',
    whoFirst: 'Tippe zuerst an, wer du bist.',
    readOnly: 'Nur Anzeige. Ein Admin kann Abhaken und Eintragen in der Orgaia-App unter Verwalten › Home Assistant erlauben.',
    notLoaded: 'Die Gruppe ist gerade nicht verbunden.',
    offline: 'Orgaia ist nicht erreichbar. Das ist der letzte Stand.',
    empty: 'Nichts offen.',
    emptyShop: 'Nichts auf der Liste.',
    addArticle: 'Artikel hinzufügen',
    addTask: 'Aufgabe hinzufügen',
    qty: 'Menge',
    add: 'Hinzufügen',
    draft: 'Wird geschrieben',
    ready: 'Freigegeben',
    readyBy: 'Freigegeben von {name}',
    going: '{name} kauft ein',
    until: 'bis {date}',
    release: 'Freigeben',
    withdraw: 'Zurücknehmen',
    take: 'Mache ich',
    drop: 'Doch nicht',
    finish: 'Einkauf fertig',
    isNew: 'neu',
    overdue: 'überfällig',
    today: 'heute',
    tomorrow: 'morgen',
    doneBy: 'erledigt von {name}',
    bought: 'Gekauft',
    done: 'Erledigt',
    failed: 'Das hat nicht geklappt.',
    notYou: 'Nicht du? Tippe deinen Namen an.',
    title: 'Titel',
    entry: 'Gruppe',
    showDone: 'Erledigte Aufgaben zeigen',
    addTasks: 'Aufgaben anlegen erlauben',
    forget: 'Vergessen, wer es war, nach (Sekunden)',
  },
};

// The people's colours of the app. All carry white text.
const COLORS = ['#2F5FD0', '#B4500B', '#7B3FB5', '#0B6F6A', '#B02C63', '#56681A', '#8A5A00', '#3F4B8C'];
const colorOf = (i) => COLORS[(((i || 0) % COLORS.length) + COLORS.length) % COLORS.length];

const esc = (s) =>
  String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

const STYLE = `
  :host { display: block; }
  ha-card { padding: 12px 16px 16px; }
  h1 { font-size: 1.25rem; font-weight: 500; margin: 4px 0 12px; }
  h2 { font-size: 1rem; font-weight: 500; margin: 0; flex: 1; min-width: 0; overflow-wrap: anywhere; }
  .hint { color: var(--secondary-text-color); font-size: 0.875rem; margin: 0 0 8px; }
  .warn { color: var(--error-color); }
  .who { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 4px; }
  .who.ask .chip { animation: ask 0.35s ease-in-out 2; }
  @keyframes ask { 50% { transform: scale(1.08); } }
  .chip {
    font: inherit; cursor: pointer; min-height: 44px; padding: 0 16px; border-radius: 22px;
    border: 2px solid var(--c); background: transparent; color: var(--primary-text-color);
  }
  .chip[aria-pressed="true"] { background: var(--c); color: #fff; font-weight: 500; }
  .list { border-top: 1px solid var(--divider-color); padding-top: 12px; margin-top: 12px; }
  .head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 4px; }
  .state { color: var(--secondary-text-color); font-size: 0.875rem; margin: 0 0 4px; }
  .row { display: flex; align-items: flex-start; gap: 4px; min-height: 44px; }
  .row.busy { opacity: 0.5; }
  .tick {
    flex: none; width: 44px; height: 44px; padding: 0; border: 0; background: none; cursor: pointer;
    display: grid; place-items: center; color: var(--primary-text-color);
  }
  .tick[disabled] { cursor: default; }
  .box {
    width: 22px; height: 22px; border-radius: 6px; border: 2px solid var(--secondary-text-color);
    display: grid; place-items: center; box-sizing: border-box;
  }
  .tick[aria-checked="true"] .box { background: var(--primary-color); border-color: var(--primary-color); }
  .box svg { width: 16px; height: 16px; fill: none; stroke: var(--text-primary-color, #fff); stroke-width: 3; visibility: hidden; }
  .tick[aria-checked="true"] .box svg { visibility: visible; }
  .text { flex: 1; min-width: 0; padding: 11px 0; overflow-wrap: anywhere; }
  .row.done .name { text-decoration: line-through; color: var(--secondary-text-color); }
  .sub { color: var(--secondary-text-color); font-size: 0.8125rem; }
  .sub .late { color: var(--error-color); }
  .tag {
    display: inline-block; font-size: 0.75rem; padding: 0 6px; border-radius: 8px; margin-left: 6px;
    background: var(--primary-color); color: var(--text-primary-color, #fff);
  }
  .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: var(--c); margin-right: 4px; }
  .btn {
    font: inherit; cursor: pointer; min-height: 40px; padding: 0 14px; border-radius: 20px;
    border: 1px solid var(--primary-color); background: transparent; color: var(--primary-color);
  }
  .btn.main { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .btn[disabled] { opacity: 0.5; cursor: default; }
  form { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
  input {
    font: inherit; min-height: 40px; box-sizing: border-box; padding: 0 12px; border-radius: 8px; min-width: 0;
    border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color);
  }
  input.title { flex: 3 1 140px; }
  input.qty { flex: 1 1 70px; }
  details { margin-top: 4px; }
  summary { cursor: pointer; color: var(--secondary-text-color); font-size: 0.875rem; min-height: 32px; }
  .error { color: var(--error-color); font-size: 0.875rem; margin: 8px 0 0; scroll-margin: 80px; }
  @media (prefers-reduced-motion: reduce) { .who.ask .chip { animation: none; } }
`;

const CHECK = '<span class="box"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></span>';

class OrgaiaCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = {};
    this._data = null;
    this._who = null;
    this._chosen = false;
    this._busy = new Set();
    this._drafts = {};
    this._error = '';
    this._unsub = null;
    this._timer = null;
    this.shadowRoot.addEventListener('click', (ev) => this._onClick(ev));
    this.shadowRoot.addEventListener('submit', (ev) => this._onSubmit(ev));
    this.shadowRoot.addEventListener('input', (ev) => {
      const el = ev.target;
      if (el && el.dataset && el.dataset.draft) this._drafts[el.dataset.draft] = el.value;
      this._touch();
    });
  }

  static getStubConfig() {
    return {};
  }

  static getConfigForm() {
    return {
      schema: [
        { name: 'entry', selector: { config_entry: { integration: 'orgaia' } } },
        { name: 'title', selector: { text: {} } },
        { name: 'show_done', selector: { boolean: {} } },
        { name: 'add_tasks', selector: { boolean: {} } },
        { name: 'forget_after', selector: { number: { min: 0, max: 3600, mode: 'box' } } },
      ],
      computeLabel: (schema, hass) => {
        const t = TEXT[(hass && hass.language || 'en').slice(0, 2)] || TEXT.en;
        return { entry: t.entry, title: t.title, show_done: t.showDone, add_tasks: t.addTasks, forget_after: t.forget }[schema.name];
      },
    };
  }

  setConfig(config) {
    const before = this._config.entry;
    this._config = config || {};
    if (before !== this._config.entry && this._unsub) {
      this._unsubscribe();
      this._subscribe();
    }
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._subscribe();
      this._render();
    }
  }

  connectedCallback() {
    this._subscribe();
  }

  disconnectedCallback() {
    this._unsubscribe();
    clearTimeout(this._timer);
  }

  getCardSize() {
    return 6;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, min_rows: 3 };
  }

  get _t() {
    return TEXT[((this._hass && this._hass.language) || 'en').slice(0, 2)] || TEXT.en;
  }

  _say(key, vars) {
    return (this._t[key] || key).replace(/\{(\w+)\}/g, (_, k) => (vars && vars[k] != null ? vars[k] : ''));
  }

  _subscribe() {
    if (this._unsub || !this._hass || !this.isConnected) return;
    const msg = { type: 'orgaia/board/subscribe' };
    if (this._config.entry) msg.entry_id = this._config.entry;
    const pending = this._hass.connection.subscribeMessage((data) => this._onData(data), msg);
    this._unsub = pending;
    pending.catch(() => {
      if (this._unsub === pending) this._unsub = null;
      this._data = { status: 'not_loaded' };
      this._render();
    });
  }

  _unsubscribe() {
    const pending = this._unsub;
    this._unsub = null;
    if (pending) pending.then((off) => off()).catch(() => undefined);
  }

  _onData(data) {
    // A group that is being loaded again is back in a moment: keep what is on screen.
    if (data.status === 'not_loaded' && this._data && this._data.lists) return;
    this._data = data;
    this._busy.clear();
    const persons = data.persons || [];
    if (this._who && !persons.some((p) => p.id === this._who)) this._who = null;
    // On a personal device Home Assistant knows who is signed in; on a shared display it does not.
    if (!this._who && !this._chosen && data.me && this._config.ask !== 'always') this._who = data.me;
    this._render();
  }

  /** Every tap keeps the chosen person a little longer; without one the card forgets them. */
  _touch() {
    clearTimeout(this._timer);
    const after = this._config.forget_after == null ? 60 : Number(this._config.forget_after);
    if (!this._who || !(after > 0)) return;
    const me = this._data && this._data.me;
    if (me && me === this._who && this._config.ask !== 'always') return;
    this._timer = setTimeout(() => {
      this._who = null;
      this._chosen = false;
      this._render();
    }, after * 1000);
  }

  _person(id) {
    return ((this._data && this._data.persons) || []).find((p) => p.id === id);
  }

  _name(id) {
    const p = this._person(id);
    return p ? p.name : '';
  }

  _date(ymd) {
    const day = ymd.slice(0, 10);
    const today = (this._data && this._data.today) || '';
    let text;
    if (day === today) text = this._t.today;
    else {
      const d = new Date(day + 'T12:00:00');
      const next = new Date(today + 'T12:00:00');
      next.setDate(next.getDate() + 1);
      text =
        today && d.toDateString() === next.toDateString()
          ? this._t.tomorrow
          : d.toLocaleDateString((this._hass && this._hass.language) || undefined, { weekday: 'short', day: 'numeric', month: 'numeric' });
    }
    return ymd.length > 10 ? `${text}, ${ymd.slice(11, 16)}` : text;
  }

  _lists() {
    const all = (this._data && this._data.lists) || [];
    const only = this._config.lists;
    if (!Array.isArray(only) || !only.length) return all;
    const wanted = only.map((x) => String(x).trim().toLowerCase());
    return all.filter((l) => wanted.includes(l.id.toLowerCase()) || wanted.includes(l.name.trim().toLowerCase()));
  }

  _checked(e) {
    // "Each for themselves": the tick shows the chosen person's own part.
    if (Array.isArray(e.each) && this._who && !e.done) return e.each.includes(this._who);
    return !!e.done;
  }

  _row(list, e) {
    const t = this._t;
    const can = this._data.can_write;
    const mine = !Array.isArray(e.each) || !this._who || (e.assignees || []).includes(this._who);
    const checked = this._checked(e);
    const sub = [];
    if (e.qty) sub.push(esc(e.qty));
    if (e.due && !e.done) sub.push(`<span class="${e.overdue ? 'late' : ''}">${esc(this._date(e.due))}${e.overdue ? ', ' + esc(t.overdue) : ''}</span>`);
    if (list.type !== 'shopping' && (e.assignees || []).length) {
      sub.push((e.assignees || []).map((id) => { const p = this._person(id); return p ? `<span class="dot" style="--c:${colorOf(p.color)}"></span>${esc(p.name)}` : ''; }).filter(Boolean).join(' '));
    }
    if (e.done && e.done_by) sub.push(esc(this._say('doneBy', { name: this._name(e.done_by) })));
    return `<div class="row${e.done ? ' done' : ''}${this._busy.has(e.uid) ? ' busy' : ''}">
      <button class="tick" role="checkbox" aria-checked="${checked}" aria-label="${esc(e.title)}" data-act="tick" data-uid="${esc(e.uid)}" data-done="${checked ? '0' : '1'}"${can && mine ? '' : ' disabled'}>${CHECK}</button>
      <div class="text"><span class="name">${esc(e.title)}</span>${e.late ? `<span class="tag">${esc(t.isNew)}</span>` : ''}${sub.length ? `<div class="sub">${sub.join(' · ')}</div>` : ''}</div>
    </div>`;
  }

  _trip(list) {
    const t = this._t;
    const trip = list.trip;
    if (!trip || trip.state === 'off') return '';
    const can = this._data.can_write;
    const until = trip.due ? ', ' + this._say('until', { date: this._date(trip.due) }) : '';
    let state = t.draft;
    const buttons = [];
    const btn = (act, label, main) => `<button class="btn${main ? ' main' : ''}" data-act="${act}" data-list="${esc(list.id)}">${esc(label)}</button>`;
    if (trip.state === 'draft') {
      if (can && trip.open) buttons.push(btn('release_shopping_list', t.release, false));
    } else if (trip.state === 'ready') {
      state = (trip.by ? this._say('readyBy', { name: this._name(trip.by) }) : t.ready) + until;
      if (can) {
        buttons.push(btn('take_shopping', t.take, true));
        buttons.push(btn('withdraw_shopping_list', t.withdraw, false));
      }
    } else {
      state = this._say('going', { name: this._name(trip.shopper) }) + until;
      if (can && (!this._who || this._who === trip.shopper)) {
        buttons.push(btn('finish_shopping', t.finish, true));
        buttons.push(btn('drop_shopping', t.drop, false));
      }
    }
    const note = trip.note ? ` · ${esc(trip.note)}` : '';
    return { state: `<p class="state${trip.overdue ? ' warn' : ''}">${esc(state)}${trip.overdue ? ', ' + esc(t.overdue) : ''}${note}</p>`, buttons: buttons.join('') };
  }

  _list(list) {
    const t = this._t;
    const shop = list.type === 'shopping';
    const open = list.entries.filter((e) => !e.done);
    const done = list.entries.filter((e) => e.done);
    const trip = this._trip(list) || { state: '', buttons: '' };
    let body = open.map((e) => this._row(list, e)).join('');
    if (!open.length) body = `<p class="hint">${esc(shop ? (done.length ? '' : t.emptyShop) : t.empty)}</p>`;
    let rest = '';
    if (done.length && (shop || this._config.show_done)) {
      rest = `<details${shop ? ' open' : ''}><summary>${esc(shop ? t.bought : t.done)} (${done.length})</summary>${done.map((e) => this._row(list, e)).join('')}</details>`;
    }
    let form = '';
    if (this._data.can_write && (shop || (list.type === 'tasks' && this._config.add_tasks))) {
      const key = list.id;
      form = `<form data-list="${esc(list.id)}" data-kind="${shop ? 'article' : 'task'}">
        <input class="title" data-draft="${esc(key)}" aria-label="${esc(shop ? t.addArticle : t.addTask)}" placeholder="${esc(shop ? t.addArticle : t.addTask)}" maxlength="200" enterkeyhint="done" autocomplete="off">
        ${shop ? `<input class="qty" data-draft="${esc(key)}#qty" aria-label="${esc(t.qty)}" placeholder="${esc(t.qty)}" maxlength="40" autocomplete="off">` : ''}
        <button class="btn" type="submit">${esc(t.add)}</button>
      </form>`;
    }
    return `<section class="list"><div class="head"><h2>${esc(list.name)}</h2>${trip.buttons}</div>${trip.state}${body}${rest}${form}</section>`;
  }

  _render() {
    if (!this._hass) return;
    const t = this._t;
    const root = this.shadowRoot;
    // Keep what is being typed, and where.
    const active = root.activeElement;
    const focus = active && active.dataset ? active.dataset.draft : null;
    const data = this._data;
    const title = this._config.title != null ? this._config.title : data && data.title;
    let html = `<style>${STYLE}</style><ha-card>${title ? `<h1>${esc(title)}</h1>` : ''}`;
    if (!data || !data.lists) {
      html += `<p class="hint">${esc(data ? t.notLoaded : '…')}</p>`;
    } else {
      if (data.status === 'offline') html += `<p class="hint warn">${esc(t.offline)}</p>`;
      if (!data.can_write) {
        html += `<p class="hint">${esc(t.readOnly)}</p>`;
      } else {
        const chips = data.persons.map((p) => `<button class="chip" style="--c:${colorOf(p.color)}" aria-pressed="${p.id === this._who}" data-act="who" data-person="${esc(p.id)}">${esc(p.name)}</button>`).join('');
        html += `<p class="hint" id="ask">${esc(this._who ? t.notYou : t.who)}</p><div class="who" role="group" aria-labelledby="ask">${chips}</div>`;
      }
      // Right under the names: that is where the eye is after a tap that did not work.
      if (this._error) html += `<p class="error" role="alert">${esc(this._error)}</p>`;
      html += this._lists().map((l) => this._list(l)).join('');
    }
    html += '</ha-card>';
    root.innerHTML = html;
    root.querySelectorAll('input[data-draft]').forEach((el) => {
      const v = this._drafts[el.dataset.draft];
      if (v) el.value = v;
      if (focus && el.dataset.draft === focus) {
        el.focus();
        el.setSelectionRange(el.value.length, el.value.length);
      }
    });
  }

  /** Nothing is done in nobody's name: without a chosen person the names are pointed at. */
  _needWho() {
    if (this._who) return true;
    this._error = this._t.whoFirst;
    this._render();
    const who = this.shadowRoot.querySelector('.who');
    if (who) {
      who.classList.add('ask');
      who.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
    return false;
  }

  async _call(service, data, busy) {
    if (!this._needWho()) return false;
    this._error = '';
    if (busy) this._busy.add(busy);
    this._touch();
    this._render();
    try {
      await this._hass.callService('orgaia', service, { config_entry_id: this._data.entry_id, person: this._who, ...data });
      return true;
    } catch (err) {
      this._error = (err && err.message) || this._t.failed;
      return false;
    } finally {
      if (busy) this._busy.delete(busy);
      this._render();
      const shown = this._error && this.shadowRoot.querySelector('.error');
      if (shown) shown.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }

  _onClick(ev) {
    const el = ev.target.closest ? ev.target.closest('[data-act]') : null;
    if (!el || el.disabled) return;
    const act = el.dataset.act;
    if (act === 'who') {
      this._who = this._who === el.dataset.person ? null : el.dataset.person;
      this._chosen = true;
      this._error = '';
      this._touch();
      this._render();
    } else if (act === 'tick') {
      if (this._busy.has(el.dataset.uid)) return;
      this._call('set_done', { item: el.dataset.uid, done: el.dataset.done === '1' }, el.dataset.uid);
    } else {
      this._call(act, { list: el.dataset.list });
    }
  }

  async _onSubmit(ev) {
    ev.preventDefault();
    const form = ev.target;
    const list = form.dataset.list;
    const title = (this._drafts[list] || '').trim();
    if (!title) return;
    const qty = (this._drafts[list + '#qty'] || '').trim();
    const ok =
      form.dataset.kind === 'article'
        ? await this._call('add_article', { list, title, ...(qty ? { quantity: qty } : {}) })
        : await this._call('add_task', { list, title });
    if (ok) {
      delete this._drafts[list];
      delete this._drafts[list + '#qty'];
      this._render();
      const input = this.shadowRoot.querySelector(`form[data-list="${CSS.escape(list)}"] input.title`);
      if (input) input.focus();
    }
  }
}

if (!customElements.get('orgaia-card')) {
  customElements.define('orgaia-card', OrgaiaCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: 'orgaia-card',
    name: 'Orgaia',
    description: 'Lists of an Orgaia group: tap who you are, then tick off, add articles and take over the shopping.',
    preview: false,
    documentationURL: 'https://github.com/PixelDevIO/HA-Orgaia#orgaia-card',
  });
}
