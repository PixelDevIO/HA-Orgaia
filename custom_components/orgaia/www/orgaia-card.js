/*
 * Orgaia card: the lists of a group on a dashboard, to tick off and to add to.
 *
 * A dashboard on the wall belongs to nobody, so the card first asks who you are: tap your name, then
 * tick off. The app shows that name with the note "via Home Assistant". After a while without a tap
 * the card forgets who it was, so the next one at the display does not tick off in somebody else's name.
 *
 * One card, several views: all lists, only the shopping, only the tasks, today at a glance, a timetable as a week grid,
 * the rosters side by side, or what is coming up. The editor picks the view and where it reads from.
 *
 * It comes with the Orgaia integration; no build step, no dependencies.
 */

const TEXT = {
  en: {
    who: 'Who are you?',
    whoWas: 'Who was it? Tap your name and it is done.',
    readOnly: 'Display only. An admin can allow ticking off and adding in the Orgaia app under Group › Home Assistant.',
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
    view: 'View',
    viewLists: 'All lists',
    viewShopping: 'Shopping',
    viewTasks: 'Tasks',
    viewTimetable: 'Timetable',
    viewRoster: 'Roster',
    viewAgenda: 'Appointments',
    lists: 'Lists (empty: all)',
    person: 'Only of this person (empty: everybody)',
    plan: 'Timetable (empty: the first one)',
    plans: 'Rosters (empty: all)',
    layout: 'Layout',
    layoutWeek: 'Whole week',
    layoutDay: 'One day',
    showPack: 'Show what to pack',
    showRooms: 'Show rooms',
    days: 'Days ahead',
    startAt: 'Starts',
    startToday: 'Today',
    startWeek: 'On Monday',
    showPlans: 'Show school and work',
    showDeadlines: 'Show what is due',
    showPersons: 'Show who it is for',
    max: 'At most this many entries (0: all)',
    ask: 'Who are you?',
    askAuto: 'Take the signed-in user when known',
    askAlways: 'Always ask',
    thisWeek: 'This week',
    nextWeek: 'Next week',
    weekAB: 'Week {week}',
    noTimetable: 'No timetable in this group.',
    noRoster: 'No roster in this group.',
    noLessons: 'No lessons entered.',
    noSchool: 'No school',
    careVs: 'Reliable school',
    careOgs: 'After-school care',
    careShort: 'Care',
    careUntil: 'until {time}',
    holidays: 'Holidays',
    away: 'Away',
    free: 'off',
    packToday: 'Pack today',
    nothingAhead: 'Nothing in the next {n} days.',
    allDay: 'all day',
    due: 'due',
    shopping: 'Shopping',
    room: 'Room {room}',
    more: '{n} more',
    look: 'Appearance',
    style: 'Style',
    styleHa: 'Like Home Assistant',
    styleTinte: 'Tinte (like the Orgaia app)',
    accent: 'Accent colour (today, buttons, ticks)',
    background: 'Background colour',
    opacity: 'Background opacity (%)',
    textColor: 'Text colour',
    fill: 'Strength of the coloured fields (%)',
    subjectColors: 'Colours of the subjects',
    shiftColors: 'Colours of the shifts',
    kindColors: 'Colours by kind',
    colorBy: 'Coloured bar',
    colorNone: 'None',
    colorPerson: 'By person',
    colorKind: 'By kind',
    kindEvent: 'Appointment',
    kindTask: 'Task',
    kindSchool: 'School',
    kindWork: 'Work',
    kindDue: 'Due',
    kindShopping: 'Shopping',
    viewToday: 'Today',
    dashWeek: 'This week',
    showTomorrow: 'Show tomorrow too',
    nothingToday: 'Nothing planned.',
    overdueN: '{n} overdue',
    school: 'School',
    test: 'Test: {subject}',
    pack: 'Pack',
    onCall: 'On call',
    waitsShopping: 'waits for somebody to do the shopping',
    notGot: 'not got',
    notGotBy: 'not got ({name})',
    markNotGot: 'Not got',
    unmarkNotGot: 'Open again',
    oneMore: 'One more',
    oneLess: 'One less',
    fixed: 'Fixed purchases',
    byAisle: 'Sort the shopping by aisle',
    there: 'there: {name}',
    back: 'back: {name}',
    nobodyYet: 'nobody yet',
    takeThere: 'I take them there',
    takeBack: 'I pick them up',
    dropDrive: 'Not me after all',
    showDrives: 'Buttons for drives',
    reload: 'Orgaia was updated. Reload this page to get the new card.',
    reloadNow: 'Reload',
  },
  de: {
    who: 'Wer bist du?',
    whoWas: 'Wer war’s? Tippe deinen Namen an, dann ist es erledigt.',
    readOnly: 'Nur Anzeige. Ein Admin kann Abhaken und Eintragen in der Orgaia-App unter Gruppe › Home Assistant erlauben.',
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
    view: 'Ansicht',
    viewLists: 'Alle Listen',
    viewShopping: 'Einkauf',
    viewTasks: 'Aufgaben',
    viewTimetable: 'Stundenplan',
    viewRoster: 'Dienstplan',
    viewAgenda: 'Termine',
    lists: 'Listen (leer: alle)',
    person: 'Nur von dieser Person (leer: alle)',
    plan: 'Stundenplan (leer: der erste)',
    plans: 'Dienstpläne (leer: alle)',
    layout: 'Darstellung',
    layoutWeek: 'Ganze Woche',
    layoutDay: 'Ein Tag',
    showPack: 'Zeigen, was einzupacken ist',
    showRooms: 'Räume zeigen',
    days: 'Tage im Voraus',
    startAt: 'Beginnt',
    startToday: 'Heute',
    startWeek: 'Am Montag',
    showPlans: 'Schule und Arbeit zeigen',
    showDeadlines: 'Fälliges zeigen',
    showPersons: 'Zeigen, für wen es ist',
    max: 'Höchstens so viele Einträge (0: alle)',
    ask: 'Wer bist du?',
    askAuto: 'Angemeldeten Nutzer nehmen, wenn bekannt',
    askAlways: 'Immer fragen',
    thisWeek: 'Diese Woche',
    nextWeek: 'Nächste Woche',
    weekAB: '{week}-Woche',
    noTimetable: 'In dieser Gruppe gibt es keinen Stundenplan.',
    noRoster: 'In dieser Gruppe gibt es keinen Dienstplan.',
    noLessons: 'Keine Stunden eingetragen.',
    noSchool: 'Keine Schule',
    careVs: 'Verlässliche Schule',
    careOgs: 'OGS',
    careShort: 'Betreuung',
    careUntil: 'bis {time}',
    holidays: 'Ferien',
    away: 'Weg',
    free: 'frei',
    packToday: 'Heute einpacken',
    nothingAhead: 'Nichts in den nächsten {n} Tagen.',
    allDay: 'ganztägig',
    due: 'fällig',
    shopping: 'Einkauf',
    room: 'Raum {room}',
    more: '{n} weitere',
    look: 'Aussehen',
    style: 'Stil',
    styleHa: 'Wie Home Assistant',
    styleTinte: 'Tinte (wie die Orgaia-App)',
    accent: 'Akzentfarbe (heute, Knöpfe, Haken)',
    background: 'Hintergrundfarbe',
    opacity: 'Deckkraft des Hintergrunds (%)',
    textColor: 'Textfarbe',
    fill: 'Farbstärke der Felder (%)',
    subjectColors: 'Farben der Fächer',
    shiftColors: 'Farben der Schichten',
    kindColors: 'Farben nach Art',
    colorBy: 'Farbstreifen',
    colorNone: 'Keiner',
    colorPerson: 'Nach Person',
    colorKind: 'Nach Art',
    kindEvent: 'Termin',
    kindTask: 'Aufgabe',
    kindSchool: 'Schule',
    kindWork: 'Arbeit',
    kindDue: 'Fällig',
    kindShopping: 'Einkauf',
    viewToday: 'Heute',
    dashWeek: 'Diese Woche',
    showTomorrow: 'Auch morgen zeigen',
    nothingToday: 'Nichts geplant.',
    overdueN: '{n} überfällig',
    school: 'Schule',
    test: 'Arbeit: {subject}',
    pack: 'Einpacken',
    onCall: 'Bereitschaft',
    waitsShopping: 'wartet auf jemanden, der einkauft',
    notGot: 'nicht bekommen',
    notGotBy: 'nicht bekommen ({name})',
    markNotGot: 'Nicht bekommen',
    unmarkNotGot: 'Wieder offen',
    oneMore: 'Eins mehr',
    oneLess: 'Eins weniger',
    fixed: 'Feste Einkäufe',
    byAisle: 'Einkauf nach Gängen sortieren',
    there: 'hin: {name}',
    back: 'zurück: {name}',
    nobodyYet: 'noch offen',
    takeThere: 'Ich fahre hin',
    takeBack: 'Ich hole ab',
    dropDrive: 'Doch nicht',
    showDrives: 'Knöpfe für Fahrten',
    reload: 'Orgaia wurde aktualisiert. Lade die Seite neu, um die neue Karte zu bekommen.',
    reloadNow: 'Neu laden',
  },
};

// The integration this card came with. A browser that still has an older card says so.
const CARD_VERSION = '0.11.0';

// The people's colours of the app. All carry white text.
const COLORS = ['#2F5FD0', '#B4500B', '#7B3FB5', '#0B6F6A', '#B02C63', '#56681A', '#8A5A00', '#3F4B8C'];
const colorOf = (i) => COLORS[(((i || 0) % COLORS.length) + COLORS.length) % COLORS.length];

const esc = (s) =>
  String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

const VIEWS = ['lists', 'shopping', 'tasks', 'today', 'timetable', 'roster', 'agenda'];
const viewOf = (config) => (VIEWS.includes(config && config.view) ? config.view : 'lists');
const textsFor = (hass) => TEXT[((hass && hass.language) || 'en').slice(0, 2)] || TEXT.en;
/** A choice from the editor: an id or a name, one or several, or a line separated by commas. */
const wanted = (x) =>
  (Array.isArray(x) ? x : typeof x === 'string' ? x.split(',') : []).map((v) => String(v).trim().toLowerCase()).filter(Boolean);
const among = (all, choice) => {
  const w = wanted(choice);
  return w.length ? all.filter((x) => w.includes(x.id.toLowerCase()) || w.includes(x.name.trim().toLowerCase())) : all;
};
const addDays = (ymd, n) => {
  const d = new Date(ymd + 'T12:00:00');
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};
/** A colour of its own for every subject or shift, the same one each time. */
const hueOf = (text) => {
  let h = 0;
  for (const ch of String(text)) h = (h * 31 + ch.codePointAt(0)) % 360;
  return h;
};

/**
 * A colour from the editor: one of Home Assistant's own (red, deep-purple, primary, …), which follow
 * the theme, or any CSS colour written by hand. Nothing that could carry more than a colour.
 */
const cssColor = (value) => {
  if (Array.isArray(value) && value.length === 3 && value.every((n) => Number.isFinite(Number(n)))) return `rgb(${value.map((n) => Math.round(Number(n))).join(' ')})`;
  const v = typeof value === 'string' ? value.trim() : '';
  if (!v || v === 'none' || v === 'default') return '';
  if (/^[a-z]+(-[a-z]+)*$/.test(v)) return `var(--${v}-color, ${v})`;
  return /^[#\w\s(),.%/-]+$/.test(v) ? v : '';
};
/** The colour chosen for one name (a subject, a shift, a kind), whatever its capitals. */
const chosenColor = (map, name) => {
  if (!map || typeof map !== 'object') return '';
  const key = Object.keys(map).find((k) => k.trim().toLowerCase() === String(name).trim().toLowerCase());
  return key ? cssColor(map[key]) : '';
};
const KINDS = { event: 'primary', task: 'green', school: 'blue', work: 'orange', due: 'red', shopping: 'teal' };

/*
 * One connection per group, however many cards show it. What came last is kept, so a card that is
 * put on the dashboard shows something at once, and the editor knows the lists and plans to offer.
 */
const GROUPS = new Map();

function watch(hass, entry, listener) {
  const key = entry || '';
  let group = GROUPS.get(key);
  if (!group) {
    group = { data: null, listeners: new Set(), pending: null };
    GROUPS.set(key, group);
  }
  group.listeners.add(listener);
  if (group.data) listener(group.data);
  if (!group.pending) {
    const msg = { type: 'orgaia/board/subscribe' };
    if (entry) msg.entry_id = entry;
    const pending = hass.connection.subscribeMessage((data) => {
      // A group that is being loaded again is back in a moment: keep what is known.
      if (data.status === 'not_loaded' && group.data && group.data.lists) return;
      group.data = data;
      group.listeners.forEach((f) => f(data));
    }, msg);
    group.pending = pending;
    pending.catch(() => {
      if (group.pending === pending) group.pending = null;
      group.listeners.forEach((f) => f({ status: 'not_loaded' }));
    });
  }
  return () => {
    group.listeners.delete(listener);
    // A dashboard that draws again takes its cards off and puts them back: do not hang up for that.
    setTimeout(() => {
      if (group.listeners.size || !group.pending) return;
      const pending = group.pending;
      group.pending = null;
      pending.then((off) => off()).catch(() => undefined);
    }, 2000);
  };
}

/** What is known of a group right now, asking for it when nothing is: the editor needs it for its choices. */
function known(hass, entry) {
  const group = GROUPS.get(entry || '');
  if (group && group.data && group.data.lists) return Promise.resolve(group.data);
  return new Promise((resolve) => {
    let off = null;
    const done = (data) => {
      clearTimeout(timer);
      if (off) off();
      else setTimeout(() => off && off(), 0);
      resolve(data && data.lists ? data : null);
    };
    const timer = setTimeout(() => done(null), 3000);
    off = watch(hass, entry, done);
  });
}

const STYLE = `
  :host { display: block; container-type: inline-size; }
  ha-card { padding: 12px 16px 16px; color: var(--primary-text-color); }
  h1 { font-size: 1.25rem; font-weight: 500; margin: 4px 0 12px; }
  /* The name keeps its words: when it and the buttons beside it do not fit on one line, the buttons move to the next. */
  h2 { font-size: 1rem; font-weight: 500; margin: 0; flex: 1 1 auto; min-width: 0; overflow-wrap: break-word; }
  .hint { color: var(--secondary-text-color); font-size: 0.875rem; margin: 0 0 8px; }
  .warn { color: var(--error-color); }
  .hint.asking { color: var(--primary-text-color); font-weight: 500; }
  /* Tinte, the look of the app: paper and ink, fine lines, no round corners. */
  ha-card.tinte {
    --primary-color: #111; --text-primary-color: #fff; --primary-text-color: #111; --secondary-text-color: #555;
    --divider-color: #d6d6d6; --card-background-color: #fff;
    background: #fff; border: 1px solid #111; border-radius: 0; box-shadow: none;
  }
  ha-card.tinte.dark {
    --primary-color: #f2f2f2; --text-primary-color: #111; --primary-text-color: #f2f2f2; --secondary-text-color: #a8a8a8;
    --divider-color: #3a3a3a; --card-background-color: #111;
    background: #111; border-color: #f2f2f2;
  }
  ha-card.tinte * { border-radius: 0 !important; }
  ha-card.tinte .dot { border-radius: 50% !important; }
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
  .btn.small { min-height: 32px; padding: 0 10px; font-size: 0.8125rem; }
  .weeks { display: flex; gap: 6px; flex-wrap: wrap; }
  .tt, .rs { display: grid; gap: 4px; align-items: stretch; }
  .dayhead { text-align: center; font-weight: 500; padding: 4px 2px; border-radius: 8px; min-width: 0; overflow-wrap: anywhere; }
  .dayhead .sub, .when .sub { display: block; font-weight: 400; }
  .dayhead.today, .when.today { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .dayhead.today .sub, .when.today .sub { color: inherit; opacity: 0.85; }
  .tt .when, .rs .when { grid-column: 1; padding: 4px 6px 4px 2px; font-variant-numeric: tabular-nums; border-radius: 8px; }
  .rs .when { padding: 6px 8px; align-self: stretch; }
  .rs .monday { margin-top: 10px; }
  .cell { min-width: 0; min-height: 40px; border-radius: 8px; display: flex; }
  .tt .cell.today { background: color-mix(in srgb, var(--primary-color) 8%, transparent); }
  .lesson, .shift {
    flex: 1; min-width: 0; box-sizing: border-box; padding: 4px 6px; border-radius: 8px; overflow-wrap: anywhere; hyphens: auto;
    --c: hsl(var(--h) 55% 45%);
    background: color-mix(in srgb, var(--c) var(--fill, 16%), transparent); border-left: 3px solid var(--c);
    display: flex; flex-direction: column; justify-content: center; font-size: 0.875rem; line-height: 1.2;
  }
  .lesson.care { --c: var(--secondary-text-color); --fill: 8%; border-left-style: dashed; color: var(--secondary-text-color); }
  .lesson.live, .shift.live, .ev.live .when { outline: 2px solid var(--primary-color); outline-offset: 1px; }
  .shift { flex-direction: row; flex-wrap: wrap; align-items: center; justify-content: flex-start; gap: 2px 6px; }
  .code { font-weight: 700; min-width: 1.5em; text-align: center; }
  .shift .sub { flex-basis: 100%; }
  .cell.free { align-items: center; padding: 0 8px; color: var(--secondary-text-color); font-size: 0.875rem; }
  .off {
    border-radius: 8px; display: grid; place-items: center; text-align: center; padding: 4px; min-width: 0; overflow-wrap: anywhere;
    color: var(--secondary-text-color); font-size: 0.875rem;
    background: repeating-linear-gradient(135deg, transparent 0 6px, color-mix(in srgb, var(--secondary-text-color) 12%, transparent) 6px 12px);
  }
  .slot { display: flex; gap: 8px; align-items: stretch; margin-top: 4px; }
  .slot .when { flex: none; width: 5.5rem; font-variant-numeric: tabular-nums; }
  .pack { margin: 12px 0 0; font-size: 0.875rem; }
  h3 { font-size: 0.875rem; font-weight: 500; margin: 14px 0 4px; color: var(--secondary-text-color); }
  h3:first-of-type { margin-top: 4px; }
  h3.today { color: var(--primary-color); }
  .ev { display: flex; gap: 10px; align-items: flex-start; min-height: 40px; }
  .ev .when { flex: none; width: 6.25rem; padding: 2px 4px; margin-top: 8px; border-radius: 6px; font-variant-numeric: tabular-nums; font-size: 0.875rem; color: var(--secondary-text-color); }
  .ev .text { padding: 9px 0; }
  .ev.bar { border-left: 3px solid var(--c, transparent); padding-left: 8px; margin-bottom: 2px; }
  .ev.school .name, .ev.work .name { color: var(--secondary-text-color); }
  .ev.done .name { text-decoration: line-through; color: var(--secondary-text-color); }
  .aisle { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--secondary-text-color); margin: 10px 0 0 48px; }
  .steps { display: flex; align-items: center; gap: 2px; flex: none; }
  .step { width: 36px; height: 36px; border-radius: 18px; border: 1px solid var(--divider-color); background: none; color: var(--primary-text-color); font: inherit; font-size: 1.1rem; cursor: pointer; }
  .step[disabled] { opacity: 0.4; cursor: default; }
  .row .btn.small { align-self: center; flex: none; }
  .missed .name { color: var(--secondary-text-color); }
  .sets { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 4px 0; }
  .drives { display: flex; flex-wrap: wrap; gap: 6px; margin: 2px 0 6px; }
  .late { color: var(--error-color); }
  .big h3 { font-size: 1rem; }
  .big .ev .text { font-size: 1.05rem; }
  @container (max-width: 520px) {
    .tt { gap: 3px; }
    .tt .when { padding: 4px 2px 4px 0; font-size: 0.875rem; }
    .tt .lesson { padding: 4px 3px 4px 4px; border-left-width: 2px; font-size: 0.75rem; overflow-wrap: normal; hyphens: none; }
    .tt .lesson span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .tt .dayhead { font-size: 0.875rem; }
    .ev .when { width: 5.5rem; }
  }
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
    this._week = null;
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

  /** Asking for the group first means the editor that opens next can offer its lists and plans. */
  static async getStubConfig(hass) {
    if (hass) await known(hass, undefined);
    // What the app promises, who does what today, is what a new card shows.
    return { view: 'today' };
  }

  static getConfigElement() {
    return document.createElement('orgaia-card-editor');
  }

  setConfig(config) {
    const before = this._config.entry;
    if (viewOf(config) !== viewOf(this._config)) this._week = null;
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
    return { columns: viewOf(this._config) === 'timetable' && this._config.layout !== 'day' ? 'full' : 12, min_columns: 6, min_rows: 2 };
  }

  get _t() {
    return TEXT[((this._hass && this._hass.language) || 'en').slice(0, 2)] || TEXT.en;
  }

  _say(key, vars) {
    return (this._t[key] || key).replace(/\{(\w+)\}/g, (_, k) => (vars && vars[k] != null ? vars[k] : ''));
  }

  _subscribe() {
    if (this._unsub || !this._hass || !this.isConnected) return;
    this._unsub = watch(this._hass, this._config.entry, (data) => this._onData(data));
    // The lesson or shift that is on right now moves with the clock.
    this._clock = setInterval(() => this._tick(), 60000);
  }

  _unsubscribe() {
    const off = this._unsub;
    this._unsub = null;
    clearInterval(this._clock);
    if (off) off();
  }

  _tick() {
    const view = viewOf(this._config);
    if (view === 'today' || view === 'timetable' || view === 'roster' || view === 'agenda') this._render();
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
    const view = viewOf(this._config);
    let all = (this._data && this._data.lists) || [];
    if (view === 'shopping') all = all.filter((l) => l.type === 'shopping');
    if (view === 'tasks') all = all.filter((l) => l.type !== 'shopping');
    return among(all, this._config.lists);
  }

  /** In the tasks view, optionally only what one person has to do. */
  _entries(list) {
    const only = wanted(this._config.person)[0];
    if (!only || list.type === 'shopping') return list.entries;
    const person = ((this._data && this._data.persons) || []).find((p) => p.id.toLowerCase() === only || p.name.trim().toLowerCase() === only);
    return person ? list.entries.filter((e) => (e.assignees || []).includes(person.id)) : list.entries;
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
    if (e.missed) sub.push(`<span class="late">${esc(typeof e.missed === 'string' ? this._say('notGotBy', { name: this._name(e.missed) }) : t.notGot)}</span>`);
    let extra = '';
    if (list.type === 'shopping' && can && !e.done) {
      const going = list.trip && list.trip.state === 'going';
      // While out shopping: "not got". Otherwise + and − on a quantity that counts.
      if (going) extra = `<button class="btn small" data-act="missed" data-uid="${esc(e.uid)}" data-list="${esc(list.id)}" data-missed="${e.missed ? '0' : '1'}">${esc(e.missed ? t.unmarkNotGot : t.markNotGot)}</button>`;
      else if (e.step) {
        const one = !e.qty || /^1(\s|$)/.test(e.qty);
        extra = `<span class="steps"><button class="step" data-act="step" data-step="-1" data-uid="${esc(e.uid)}" data-list="${esc(list.id)}" aria-label="${esc(t.oneLess)}: ${esc(e.title)}"${one ? ' disabled' : ''}>−</button><button class="step" data-act="step" data-step="1" data-uid="${esc(e.uid)}" data-list="${esc(list.id)}" aria-label="${esc(t.oneMore)}: ${esc(e.title)}">+</button></span>`;
      }
    }
    return `<div class="row${e.done ? ' done' : ''}${e.missed ? ' missed' : ''}${this._busy.has(e.uid) ? ' busy' : ''}">
      <button class="tick" role="checkbox" aria-checked="${checked}" aria-label="${esc(e.title)}" data-act="tick" data-uid="${esc(e.uid)}" data-done="${checked ? '0' : '1'}"${can && mine ? '' : ' disabled'}>${CHECK}</button>
      <div class="text"><span class="name">${esc(e.title)}</span>${e.late ? `<span class="tag">${esc(t.isNew)}</span>` : ''}${sub.length ? `<div class="sub">${sub.join(' · ')}</div>` : ''}</div>${extra}
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
    const entries = this._entries(list);
    const open = entries.filter((e) => !e.done);
    const done = entries.filter((e) => e.done);
    const trip = this._trip(list) || { state: '', buttons: '' };
    let body = open.map((e) => this._row(list, e)).join('');
    if (shop && open.length && this._config.by_aisle !== false) {
      // In the order one walks through the shop, as the app sorts it.
      const order = (this._data.aisles || []).map(([key]) => key);
      const names = Object.fromEntries(this._data.aisles || []);
      const groups = new Map();
      for (const e of open) {
        const key = order.includes(e.aisle) ? e.aisle : 'other';
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(e);
      }
      const keys = [...groups.keys()].sort((a, b) => order.indexOf(a) - order.indexOf(b));
      body = keys.length > 1 ? keys.map((k) => `<p class="aisle">${esc(names[k] || k)}</p>${groups.get(k).map((e) => this._row(list, e)).join('')}`).join('') : body;
    }
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
    let sets = '';
    if (shop && this._data.can_write && (list.sets || []).length && !(list.trip && list.trip.state === 'going')) {
      sets = `<div class="sets"><span class="sub">${esc(t.fixed)}:</span>${list.sets.map((x) => `<button class="btn small" data-act="set" data-list="${esc(list.id)}" data-set="${esc(x.id)}">+ ${esc(x.name)} (${x.count})</button>`).join('')}</div>`;
    }
    return `<section class="list"><div class="head"><h2>${esc(list.name)}</h2>${trip.buttons}</div>${trip.state}${body}${rest}${form}${sets}</section>`;
  }

  _day(ymd, long) {
    return new Date(ymd + 'T12:00:00').toLocaleDateString((this._hass && this._hass.language) || undefined, long ? { weekday: 'long', day: 'numeric', month: 'numeric' } : { weekday: 'short' });
  }

  _short(ymd) {
    return new Date(ymd + 'T12:00:00').toLocaleDateString((this._hass && this._hass.language) || undefined, { day: 'numeric', month: 'numeric' });
  }

  _now() {
    const d = new Date();
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  }

  _badge(id) {
    const p = this._person(id);
    return p ? `<span class="dot" style="--c:${colorOf(p.color)}"></span>${esc(p.name)}` : '';
  }

  /** A timetable: the week as a grid of periods and days, or one day as a list. */
  _timetable() {
    const t = this._t;
    const data = this._data;
    const plans = data.timetables || [];
    if (!plans.length) return `<p class="hint">${esc(t.noTimetable)}</p>`;
    const mine = plans.find((p) => p.person && p.person === data.me);
    const plan = (wanted(this._config.plan).length ? among(plans, this._config.plan)[0] : mine) || plans[0];
    const today = data.today;
    const now = this._now();
    const rooms = this._config.show_rooms !== false;
    const school = (d) => d.status === 'school';
    // Friday afternoon nobody wants to see the week that is over.
    const left = plan.weeks[0].days.some((d) => school(d) && (d.date > today || (d.date === today && d.end > now)));
    const auto = !left && plan.weeks[1] && plan.weeks[1].days.some(school) ? 1 : 0;
    const at = this._week == null ? auto : Math.min(this._week, plan.weeks.length - 1);
    const week = plan.weeks[at];
    const owner = plan.person ? this._badge(plan.person) : '';
    const ab = week.days.find((d) => d.week);
    let head = `<div class="head"><h2>${esc(plan.name)}${owner && this._name(plan.person) !== plan.name ? ` <span class="sub">${owner}</span>` : ''}</h2>`;
    const cell = (l, live) =>
      `<div class="lesson${live ? ' live' : ''}" style="--h:${hueOf(l.subject)}${chosenColor(this._config.subject_colors, l.subject) ? ';--c:' + chosenColor(this._config.subject_colors, l.subject) : ''}" title="${esc(l.subject)}${l.room ? ', ' + esc(l.room) : ''}"><span class="name">${esc(l.subject)}</span>${rooms && l.room ? `<span class="sub">${esc(l.room)}</span>` : ''}</div>`;
    const pack = week.days.find((d) => d.date === today);
    const foot = this._config.show_pack !== false && pack && pack.pack.length ? `<p class="pack"><b>${esc(t.packToday)}:</b> ${esc(pack.pack.join(', '))}</p>` : '';

    if (this._config.layout === 'day') {
      const all = plan.weeks.flatMap((w) => w.days);
      const day = all.find((d) => school(d) && (d.date > today || (d.date === today && d.end > now))) || all.find((d) => d.date === today);
      head += `<span class="sub">${esc(this._date(day.date))}${day.week ? ' · ' + esc(this._say('weekAB', { week: day.week })) : ''}</span></div>`;
      const rows = day.lessons
        .map((l) => {
          const live = day.date === today && l.start <= now && now < l.end;
          return `<div class="slot${live ? ' live' : ''}"><span class="when">${esc(l.period)}.<br><span class="sub">${esc(l.start)}–${esc(l.end)}</span></span>${cell(l, live)}</div>`;
        })
        .join('');
      const c = day.care;
      const careLive = c && day.date === today && c.start <= now && now < c.end;
      const care = c ? `<div class="slot${careLive ? ' live' : ''}"><span class="when"><span class="sub">${esc(c.start)}–${esc(c.end)}</span></span><div class="lesson care${careLive ? ' live' : ''}"><span class="name">${esc(c.kind === 'vs' ? t.careVs : t.careOgs)}</span></div></div>` : '';
      const none = day.status === 'holiday' ? day.holiday || t.holidays : day.status === 'away' ? day.away || t.away : t.noSchool;
      return head + (rows ? rows + care : `<p class="hint">${esc(none)}</p>`) + foot;
    }

    const used = plan.weeks.flatMap((w) => w.days);
    const last = Math.max(0, ...used.flatMap((d) => d.lessons.map((l) => l.period)));
    if (!last) return head + `</div><p class="hint">${esc(t.noLessons)}</p>`;
    const weekend = [5, 6].filter((i) => plan.weeks.some((w) => w.days[i].lessons.length));
    const cols = [0, 1, 2, 3, 4, ...weekend];
    head += `<span class="weeks" role="group">${plan.weeks
      .map((w, i) => `<button class="btn small${i === at ? ' main' : ''}" aria-pressed="${i === at}" data-act="week" data-week="${i}">${esc(i ? t.nextWeek : t.thisWeek)}</button>`)
      .join('')}</span></div>`;
    if (ab) head += `<p class="state">${esc(this._say('weekAB', { week: ab.week }))}</p>`;
    let grid = `<div class="tt" role="table" style="grid-template-columns: minmax(2.75rem, max-content) repeat(${cols.length}, minmax(0, 1fr))">`;
    grid += '<div class="corner"></div>';
    cols.forEach((i, c) => {
      const d = week.days[i];
      grid += `<div class="dayhead${d.date === today ? ' today' : ''}" style="grid-column:${c + 2}">${esc(this._day(d.date))}<span class="sub">${esc(this._short(d.date))}</span></div>`;
    });
    for (let n = 1; n <= last; n++) {
      const p = plan.periods[n - 1] || {};
      grid += `<div class="when" style="grid-row:${n + 1}">${n}.<span class="sub">${esc(p.start || '')}</span></div>`;
    }
    cols.forEach((i, c) => {
      const d = week.days[i];
      const col = `grid-column:${c + 2}`;
      if (d.status === 'holiday' || d.status === 'away') {
        grid += `<div class="off${d.date === today ? ' today' : ''}" style="${col};grid-row:2 / span ${last}"><span>${esc(d.status === 'away' ? d.away || t.away : d.holiday || t.holidays)}</span></div>`;
        return;
      }
      for (let n = 1; n <= last; n++) {
        const l = d.lessons.find((x) => x.period === n);
        const live = l && d.date === today && l.start <= now && now < l.end;
        grid += `<div class="cell${d.date === today ? ' today' : ''}" style="${col};grid-row:${n + 1}">${l ? cell(l, live) : ''}</div>`;
      }
    });
    // Care after school (reliable school or OGS) as one more row: until when, day by day.
    if (week.days.some((d) => d.care)) {
      const kind = week.days.find((d) => d.care).care.kind;
      grid += `<div class="when" style="grid-row:${last + 2}"><span class="sub">${esc(kind === 'vs' ? t.careVs : t.careOgs)}</span></div>`;
      cols.forEach((i, c) => {
        const d = week.days[i];
        const live = d.care && d.date === today && d.care.start <= now && now < d.care.end;
        grid += `<div class="cell${d.date === today ? ' today' : ''}" style="grid-column:${c + 2};grid-row:${last + 2}">${d.care ? `<div class="lesson care${live ? ' live' : ''}"><span class="name">${esc(this._say('careUntil', { time: d.care.end }))}</span></div>` : ''}</div>`;
      });
    }
    return head + grid + '</div>' + foot;
  }

  /** Rosters: the days down, the people across. */
  _roster() {
    const t = this._t;
    const data = this._data;
    const all = data.rosters || [];
    if (!all.length) return `<p class="hint">${esc(t.noRoster)}</p>`;
    const plans = among(all, this._config.plans);
    if (!plans.length) return `<p class="hint">${esc(t.noRoster)}</p>`;
    const count = Math.min(14, Math.max(1, Number(this._config.days) || 7));
    const first = this._config.start === 'week' ? plans[0].days[0].date : data.today;
    const dates = Array.from({ length: count }, (_, i) => addDays(first, i));
    const now = this._now();
    let grid = `<div class="rs" role="table" style="grid-template-columns: max-content repeat(${plans.length}, minmax(0, 1fr))">`;
    grid += '<div class="corner"></div>';
    plans.forEach((p, c) => {
      grid += `<div class="dayhead" style="grid-column:${c + 2}">${p.person ? this._badge(p.person) : esc(p.name)}</div>`;
    });
    dates.forEach((date, r) => {
      const today = date === data.today;
      const monday = new Date(date + 'T12:00:00').getDay() === 1 && r > 0;
      const cls = `${today ? ' today' : ''}${monday ? ' monday' : ''}`;
      grid += `<div class="when${cls}" style="grid-row:${r + 2}">${esc(this._day(date))}<span class="sub">${esc(this._short(date))}</span></div>`;
      plans.forEach((p, c) => {
        const d = p.days.find((x) => x.date === date);
        const place = `grid-column:${c + 2};grid-row:${r + 2}`;
        if (!d || !d.spans.length) {
          grid += `<div class="cell free${cls}" style="${place}">${esc(d && d.shift ? d.shift : t.free)}</div>`;
          return;
        }
        const live = today && d.spans.some((s) => s.start <= now && (s.overnight || now < s.end));
        const times = d.spans.map((s) => `${esc(s.start)}–${esc(s.end)}`).join(', ');
        const code = d.code ? `<span class="code">${esc(d.code)}</span>` : '';
        grid += `<div class="cell${cls}" style="${place}"><div class="shift${live ? ' live' : ''}" style="--h:${hueOf(d.shift || times)}${d.shift && chosenColor(this._config.shift_colors, d.shift) ? ';--c:' + chosenColor(this._config.shift_colors, d.shift) : ''}">${code}<span class="name">${esc(d.shift || times)}</span>${d.shift ? `<span class="sub">${times}</span>` : ''}</div></div>`;
      });
    });
    return grid + '</div>';
  }

  /** What is coming up, day by day. */
  _agenda() {
    const t = this._t;
    const data = this._data;
    const days = Math.min(31, Math.max(1, Number(this._config.days) || 7));
    const last = addDays(data.today, days - 1);
    const only = wanted(this._config.person)[0];
    const person = only ? data.persons.find((p) => p.id.toLowerCase() === only || p.name.trim().toLowerCase() === only) : null;
    const now = `${data.today}T${this._now()}`;
    let rows = (data.agenda || []).filter((r) => {
      if (r.start.slice(0, 10) > last) return false;
      if (this._config.show_plans === false && (r.kind === 'school' || r.kind === 'work')) return false;
      if (this._config.show_deadlines === false && (r.kind === 'due' || r.kind === 'shopping')) return false;
      if (person && !(r.persons || []).includes(person.id)) return false;
      // What is over today makes room for what is still to come.
      return r.all_day || (r.end || r.start) >= now || r.start.slice(0, 10) > data.today;
    });
    const max = Number(this._config.max) || 0;
    const hidden = max > 0 && rows.length > max ? rows.length - max : 0;
    if (hidden) rows = rows.slice(0, max);
    if (!rows.length) return `<p class="hint">${esc(this._say('nothingAhead', { n: days }))}</p>`;
    let html = '';
    let day = '';
    for (const r of rows) {
      // Something that began before today is shown under today.
      const date = r.start.slice(0, 10) < data.today ? data.today : r.start.slice(0, 10);
      if (date !== day) {
        day = date;
        const near = date === data.today ? t.today : date === addDays(data.today, 1) ? t.tomorrow : '';
        html += `<h3${date === data.today ? ' class="today"' : ''}>${near ? esc(near) + ' · ' : ''}${esc(this._day(date, true))}</h3>`;
      }
      const live = !r.all_day && r.start <= now && (r.end || r.start) > now;
      let when = r.all_day ? t.allDay : r.start.slice(11, 16);
      if (!r.all_day && r.end && r.kind !== 'due') when += `–${r.end.slice(11, 16)}`;
      if (r.all_day && r.end && r.end.slice(0, 10) > date) when = `${this._say('until', { date: this._short(r.end.slice(0, 10)) })}`;
      const sub = [];
      if (r.kind === 'due') sub.push(esc(t.due));
      if (r.kind === 'shopping') sub.push(esc(t.shopping));
      if (r.location) sub.push(esc(r.location));
      if (this._config.show_persons !== false && (r.persons || []).length) sub.push(r.persons.map((id) => this._badge(id)).filter(Boolean).join(' '));
      let drive = '';
      if (r.drive) {
        const sides = [['to', 'there', 'takeThere'], ['from', 'back', 'takeBack']].filter(([k]) => k in r.drive);
        sub.push('🚗 ' + sides.map(([k, label]) => `<span class="${r.drive[k] ? '' : 'late'}">${esc(this._say(label, { name: r.drive[k] ? this._name(r.drive[k]) : t.nobodyYet }))}</span>`).join(', '));
        if (data.can_write && this._config.show_drives !== false) {
          const btn = (which, label) => `<button class="btn small" data-act="drive" data-item="${esc(r.drive.item)}" data-date="${esc(r.drive.date)}" data-which="${which}" data-take="${label === 'dropDrive' ? '0' : '1'}">${esc(t[label])}</button>`;
          const buttons = sides.map(([k, , label]) => (!r.drive[k] ? btn(k, label) : this._who && r.drive[k] === this._who ? btn(k, 'dropDrive') : '')).filter(Boolean);
          if (buttons.length) drive = `<div class="drives">${buttons.join('')}</div>`;
        }
      }
      let bar = '';
      if (this._config.color_by === 'person') {
        const first = this._person((r.persons || [])[0]);
        bar = first ? colorOf(first.color) : 'transparent';
      } else if (this._config.color_by === 'kind') {
        bar = chosenColor(this._config.kind_colors, r.kind) || cssColor(KINDS[r.kind]);
      }
      html += `<div class="ev ${esc(r.kind)}${live ? ' live' : ''}${r.done ? ' done' : ''}${bar ? ' bar' : ''}"${bar ? ` style="--c:${bar}"` : ''}><span class="when">${esc(when)}</span><div class="text"><span class="name">${esc(r.title)}</span>${sub.length ? `<div class="sub">${sub.join(' · ')}</div>` : ''}${drive}</div></div>`;
    }
    // Taking a drive is done in somebody's name, as ticking off is.
    if (data.can_write && this._config.show_drives !== false && rows.some((r) => r.drive)) html = this._chips() + html;
    if (hidden) html += `<p class="hint">${esc(this._say('more', { n: hidden }))}</p>`;
    return html;
  }

  /** Today (and tomorrow) at a glance, for a display on the wall: appointments, school, work, what is due, the shopping. */
  _today() {
    const t = this._t;
    const data = this._data;
    const all = data.days || [];
    const shown = this._config.show_tomorrow ? all.slice(0, 2) : all.slice(0, 1);
    const only = wanted(this._config.person)[0];
    const person = only ? data.persons.find((p) => p.id.toLowerCase() === only || p.name.trim().toLowerCase() === only) : null;
    const name = person ? person.name : null;
    const forMe = (names) => !name || (names || []).includes(name);
    const row = (when, title, sub, cls) =>
      `<div class="ev${cls ? ' ' + cls : ''}"><span class="when">${esc(when)}</span><div class="text"><span class="name">${title}</span>${sub.length ? `<div class="sub">${sub.join(' · ')}</div>` : ''}</div></div>`;
    let html = '';
    shown.forEach((d, i) => {
      const rows = [];
      for (const a of d.appointments.filter((x) => forMe(x.persons))) {
        const sub = [];
        if (a.location) sub.push(esc(a.location));
        if (!name && a.persons.length) sub.push(esc(a.persons.join(', ')));
        if ((a.drive_missing || []).length) sub.push(`<span class="late">🚗 ${esc(t.nobodyYet)}</span>`);
        rows.push([a.all_day ? '' : a.start, row(a.all_day ? t.allDay : a.start + (a.end ? '–' + a.end : ''), esc(a.title), sub, 'event')]);
      }
      for (const s of d.school.filter((x) => !name || x.person === name)) {
        const sub = [];
        if (s.note) sub.push(esc(s.note));
        s.exams.forEach((x) => sub.push(`<b>${esc(this._say('test', { subject: x }))}</b>`));
        if (s.care) sub.push(`${esc(s.care.kind === 'vs' ? t.careVs : t.careOgs)} ${esc(this._say('careUntil', { time: s.care.end }))}`);
        if (s.pack.length) sub.push(`${esc(t.pack)}: ${esc(s.pack.join(', '))}`);
        const who = name ? t.school : `${s.person} · ${t.school}`;
        if (s.status === 'school') rows.push([s.start, row(`${s.start}–${s.end}`, esc(who), sub, 'school')]);
        else if (s.status === 'holiday') rows.push(['', row(t.allDay, esc(name ? t.holidays : `${s.person} · ${t.holidays}`), sub, 'school')]);
        else if (sub.length) rows.push(['', row('', esc(s.person), sub, 'school')]);
      }
      for (const w of d.work.filter((x) => !name || x.person === name)) {
        const label = [name ? '' : w.person, w.shift || '', w.standby ? t.onCall : ''].filter(Boolean).join(' · ');
        rows.push([w.spans[0].slice(0, 5), row(w.spans.join(', '), esc(label || t.kindWork), [], 'work')]);
      }
      rows.sort((a, b) => a[0].localeCompare(b[0]));
      const due = d.due.filter((x) => !x.done && forMe(x.persons));
      if (due.length) rows.push(['', row(t.due, esc(due.map((x) => x.title).join(', ')), [], 'due')]);
      if (!name && d.overdue.length) rows.push(['', row(this._say('overdueN', { n: d.overdue.length }), esc(d.overdue.join(', ')), [], 'due')]);
      if (i === 0) {
        for (const sh of d.shopping) {
          const text = sh.state === 'going' && sh.shopper ? this._say('going', { name: sh.shopper }) : t.waitsShopping;
          rows.push(['', row(t.shopping, `${esc(sh.list)}`, [esc(text)], 'shopping')]);
        }
      }
      const word = i === 0 ? t.today : t.tomorrow;
      const near = word.charAt(0).toUpperCase() + word.slice(1);
      html += `<h3${i === 0 ? ' class="today"' : ''}>${esc(near)} · ${esc(this._day(d.date, true))}</h3>`;
      html += rows.length ? rows.map((r) => r[1]).join('') : `<p class="hint">${esc(t.nothingToday)}</p>`;
    });
    return `<div class="big">${html}</div>`;
  }

  /** The names to tap before doing something in somebody's name. */
  _chips() {
    const t = this._t;
    const chips = this._data.persons.map((p) => `<button class="chip" style="--c:${colorOf(p.color)}" aria-pressed="${p.id === this._who}" data-act="who" data-person="${esc(p.id)}">${esc(p.name)}</button>`).join('');
    const error = this._error ? `<p class="error" role="alert">${esc(this._error)}</p>` : '';
    // A tap without a name is kept: the question is "who was it?", and the name finishes the tap.
    if (this._pending && !this._who) return `<p class="hint asking" id="ask" role="status">${esc(t.whoWas)}</p><div class="who ask" role="group" aria-labelledby="ask">${chips}</div>${error}`;
    return `<p class="hint" id="ask">${esc(this._who ? t.notYou : t.who)}</p><div class="who" role="group" aria-labelledby="ask">${chips}</div>${error}`;
  }

  /** What the editor's "Appearance" says, as styles of the card itself. */
  _look() {
    const c = this._config;
    const out = [];
    const accent = cssColor(c.accent_color);
    if (accent) out.push(`--primary-color:${accent}`);
    const text = cssColor(c.text_color);
    if (text) out.push(`--primary-text-color:${text}`);
    const fill = Number(c.fill);
    if (c.fill != null && c.fill !== '' && fill >= 0 && fill <= 100) out.push(`--fill:${fill}%`);
    const opacity = c.background_opacity == null || c.background_opacity === '' ? 100 : Math.min(100, Math.max(0, Number(c.background_opacity)));
    const ground = cssColor(c.background_color);
    if (ground || opacity < 100) {
      const base = ground || 'var(--ha-card-background, var(--card-background-color, #fff))';
      out.push(`background:${opacity < 100 ? `color-mix(in srgb, ${base} ${opacity}%, transparent)` : base}`);
    }
    // Nothing behind it: then no frame around nothing either.
    if (opacity === 0) out.push('border-color:transparent', 'box-shadow:none');
    return out.join(';');
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
    const look = this._look();
    const tinte = this._config.style === 'tinte' ? ` class="tinte${this._hass.themes && this._hass.themes.darkMode ? ' dark' : ''}"` : '';
    let html = `<style>${STYLE}</style><ha-card${tinte}${look ? ` style="${esc(look)}"` : ''}>${title ? `<h1>${esc(title)}</h1>` : ''}`;
    if (data && data.version && data.version !== CARD_VERSION) {
      html += `<p class="hint warn">${esc(t.reload)} <button class="btn small" data-act="reload">${esc(t.reloadNow)}</button></p>`;
    }
    if (!data || !data.lists) {
      html += `<p class="hint">${esc(data ? t.notLoaded : '…')}</p>`;
    } else if (['today', 'timetable', 'roster', 'agenda'].includes(viewOf(this._config))) {
      if (data.status === 'offline') html += `<p class="hint warn">${esc(t.offline)}</p>`;
      html += this[`_${viewOf(this._config)}`]();
    } else {
      if (data.status === 'offline') html += `<p class="hint warn">${esc(t.offline)}</p>`;
      if (!data.can_write) {
        html += `<p class="hint">${esc(t.readOnly)}</p>`;
      } else {
        // Right under the names: that is where the eye is after a tap that did not work.
        html += this._chips();
      }
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

  /** Nothing is done in nobody's name: the tap waits, and the names ask who it was. Never an error. */
  _needWho(pending) {
    if (this._who) return true;
    this._pending = pending || null;
    this._error = '';
    this._render();
    const who = this.shadowRoot.querySelector('.who');
    if (who) who.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    // A tap nobody answers is forgotten, so that a name tapped much later does not tick off something old.
    clearTimeout(this._pendingTimer);
    this._pendingTimer = setTimeout(() => {
      if (!this._pending) return;
      this._pending = null;
      this._render();
    }, 30000);
    return false;
  }

  async _call(service, data, busy, then) {
    if (!this._needWho({ service, data, busy, then })) return false;
    this._error = '';
    if (busy) this._busy.add(busy);
    this._touch();
    this._render();
    try {
      await this._hass.callService('orgaia', service, { config_entry_id: this._data.entry_id, person: this._who, ...data });
      if (then) then();
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
      const pending = this._pending;
      this._pending = null;
      clearTimeout(this._pendingTimer);
      this._who = pending ? el.dataset.person : this._who === el.dataset.person ? null : el.dataset.person;
      this._chosen = true;
      this._error = '';
      this._touch();
      this._render();
      // The tap that was waiting for a name is done now, in that name.
      if (pending) this._call(pending.service, pending.data, pending.busy, pending.then);
    } else if (act === 'week') {
      this._week = Number(el.dataset.week);
      this._render();
    } else if (act === 'tick') {
      if (this._busy.has(el.dataset.uid)) return;
      this._call('set_done', { item: el.dataset.uid, done: el.dataset.done === '1' }, el.dataset.uid);
    } else if (act === 'reload') {
      location.reload();
    } else if (act === 'missed') {
      if (this._busy.has(el.dataset.uid)) return;
      this._call('set_not_got', { item: el.dataset.uid, list: el.dataset.list, missed: el.dataset.missed === '1' }, el.dataset.uid);
    } else if (act === 'step') {
      if (this._busy.has(el.dataset.uid)) return;
      this._call('set_quantity', { item: el.dataset.uid, list: el.dataset.list, step: Number(el.dataset.step) }, el.dataset.uid);
    } else if (act === 'set') {
      this._call('add_fixed_purchase', { list: el.dataset.list, set: el.dataset.set });
    } else if (act === 'drive') {
      this._call(el.dataset.take === '1' ? 'take_drive' : 'drop_drive', { item: el.dataset.item, date: el.dataset.date, which: el.dataset.which });
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
    const added = () => {
      delete this._drafts[list];
      delete this._drafts[list + '#qty'];
      this._render();
      const input = this.shadowRoot.querySelector(`form[data-list="${CSS.escape(list)}"] input.title`);
      if (input) input.focus();
    };
    if (form.dataset.kind === 'article') await this._call('add_article', { list, title, ...(qty ? { quantity: qty } : {}) }, undefined, added);
    else await this._call('add_task', { list, title }, undefined, added);
  }
}

/*
 * The editor: first the view, then only what that view can be told. The lists, plans and people on
 * offer are those of the group; while they are not known yet, a name can be typed instead.
 */
const MAPS = { timetable: 'subject_colors', roster: 'shift_colors', agenda: 'kind_colors' };
const SEP = '::';

class OrgaiaCardEditor extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._data = null;
    this._asked = undefined;
  }

  setConfig(config) {
    this._config = config || {};
    this._load();
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._load();
    this._render();
  }

  /** Home Assistant's own form is fetched with its editors; this makes sure it is there. */
  async connectedCallback() {
    if (!customElements.get('ha-form') && window.loadCardHelpers) {
      try {
        const helpers = await window.loadCardHelpers();
        const card = await helpers.createCardElement({ type: 'entities', entities: [] });
        if (card && card.constructor.getConfigElement) await card.constructor.getConfigElement();
      } catch (err) {
        // The form may still arrive on its own.
      }
    }
    this._render();
  }

  _load() {
    const entry = this._config.entry || '';
    if (!this._hass || this._asked === entry) return;
    this._asked = entry;
    known(this._hass, this._config.entry).then((data) => {
      if (this._asked !== entry) return;
      this._data = data;
      this._render();
    });
  }

  _schema() {
    const t = textsFor(this._hass);
    const data = this._data || {};
    const view = viewOf(this._config);
    const pick = (name, items, multiple) =>
      items && items.length
        ? { name, selector: { select: { mode: 'dropdown', multiple: !!multiple, options: items.map((x) => ({ value: x.id, label: x.label || x.name })) } } }
        : { name, selector: { text: {} } };
    const named = (plans) => (plans || []).map((p) => {
      const owner = (data.persons || []).find((x) => x.id === p.person);
      return { id: p.id, label: owner && owner.name !== p.name ? `${p.name} (${owner.name})` : p.name };
    });
    const choice = (name, values) => ({ name, selector: { select: { mode: 'dropdown', options: values.map(([value, label]) => ({ value, label })) } } });
    const flag = (name) => ({ name, selector: { boolean: {} } });
    const number = (name, min, max) => ({ name, selector: { number: { min, max, mode: 'box' } } });
    const schema = [
      { name: 'view', required: true, selector: { select: { mode: 'dropdown', options: VIEWS.map((v) => ({ value: v, label: t['view' + v[0].toUpperCase() + v.slice(1)] })) } } },
      { name: 'entry', selector: { config_entry: { integration: 'orgaia' } } },
      { name: 'title', selector: { text: {} } },
    ];
    const lists = data.lists || [];
    if (view === 'lists' || view === 'shopping' || view === 'tasks') {
      const fit = view === 'shopping' ? lists.filter((l) => l.type === 'shopping') : view === 'tasks' ? lists.filter((l) => l.type !== 'shopping') : lists;
      schema.push(pick('lists', fit, true));
      if (view === 'tasks') schema.push(pick('person', data.persons, false));
      if (view !== 'shopping') schema.push(flag('show_done'), flag('add_tasks'));
      if (view !== 'tasks') schema.push(flag('by_aisle'));
      schema.push(choice('ask', [['auto', t.askAuto], ['always', t.askAlways]]), number('forget_after', 0, 3600));
    } else if (view === 'timetable') {
      schema.push(pick('plan', named(data.timetables), false), choice('layout', [['week', t.layoutWeek], ['day', t.layoutDay]]), flag('show_rooms'), flag('show_pack'));
    } else if (view === 'roster') {
      schema.push(pick('plans', named(data.rosters), true), number('days', 1, 14), choice('start', [['today', t.startToday], ['week', t.startWeek]]));
    } else if (view === 'today') {
      schema.push(pick('person', data.persons, false), flag('show_tomorrow'));
    } else {
      schema.push(number('days', 1, 31), pick('person', data.persons, false), flag('show_plans'), flag('show_deadlines'), flag('show_persons'), flag('show_drives'), number('max', 0, 100));
      schema.push(choice('ask', [['auto', t.askAuto], ['always', t.askAlways]]), number('forget_after', 0, 3600));
    }
    const color = (name) => ({ name, selector: { ui_color: {} } });
    const section = (name, title, fields) => ({ type: 'expandable', name, title, flatten: true, schema: fields });
    // One choice for the look. Colours come from the app; a card that already carries colours of its
    // own (set in an earlier version, or in YAML) keeps them and still offers them here.
    const c = this._config;
    const own = ['accent_color', 'background_color', 'text_color', 'background_opacity', 'fill'].some((k) => c[k] != null && c[k] !== '') || Object.values(MAPS).some((m) => c[m] && Object.keys(c[m]).length);
    const look = [choice('style', [['ha', t.styleHa], ['tinte', t.styleTinte]])];
    if (view === 'agenda') look.push(choice('color_by', [['none', t.colorNone], ['person', t.colorPerson], ['kind', t.colorKind]]));
    if (own) {
      look.push(color('accent_color'), color('background_color'), { name: 'background_opacity', selector: { number: { min: 0, max: 100, step: 5, mode: 'slider' } } }, color('text_color'));
      if (view === 'timetable' || view === 'roster') look.push({ name: 'fill', selector: { number: { min: 0, max: 100, step: 2, mode: 'slider' } } });
    }
    schema.push(section('look', t.look, look));
    const names = own ? this._names() : [];
    if (names.length) schema.push(section('colors', t[{ timetable: 'subjectColors', roster: 'shiftColors', agenda: 'kindColors' }[view]], names.map((n) => color(MAPS[view] + SEP + n))));
    return schema;
  }

  /** What can be given a colour of its own in this view: the subjects, the shifts, or the kinds of entries. */
  _names() {
    const data = this._data || {};
    const view = viewOf(this._config);
    const seen = new Set();
    if (view === 'timetable') {
      const plans = data.timetables || [];
      const plan = (wanted(this._config.plan).length ? among(plans, this._config.plan)[0] : null) || plans[0];
      if (plan) plan.weeks.forEach((w) => w.days.forEach((d) => d.lessons.forEach((l) => seen.add(l.subject))));
    } else if (view === 'roster') {
      among(data.rosters || [], this._config.plans).forEach((p) => p.days.forEach((d) => d.shift && seen.add(d.shift)));
    } else if (view === 'agenda' && this._config.color_by === 'kind') {
      Object.keys(KINDS).forEach((k) => seen.add(k));
    }
    // Colours once set stay on offer, also when the plan does not use the name right now.
    Object.keys(this._config[MAPS[view]] || {}).forEach((k) => seen.add(k));
    return [...seen].sort((a, b) => a.localeCompare(b));
  }

  /** What the form shows where nothing was set: the card's own defaults. */
  _shown() {
    const c = this._config;
    const view = viewOf(c);
    const shown = { ...c, view };
    const fill = (key, value) => {
      if (shown[key] == null) shown[key] = value;
    };
    if (view === 'timetable') {
      fill('layout', 'week');
      fill('show_rooms', true);
      fill('show_pack', true);
    } else if (view === 'roster') {
      fill('days', 7);
      fill('start', 'today');
    } else if (view === 'agenda') {
      fill('days', 7);
      fill('show_plans', true);
      fill('show_deadlines', true);
      fill('show_persons', true);
      fill('show_drives', true);
      fill('ask', 'auto');
      fill('forget_after', 60);
    } else if (view === 'today') {
      fill('show_tomorrow', false);
    } else {
      if (view !== 'tasks') fill('by_aisle', true);
      fill('ask', 'auto');
      fill('forget_after', 60);
    }
    if (shown.background_opacity == null) shown.background_opacity = 100;
    fill('style', 'ha');
    if ((view === 'timetable' || view === 'roster') && shown.fill == null) shown.fill = 16;
    if (view === 'agenda') fill('color_by', 'none');
    // The form knows no nested values: every colour of a subject, shift or kind is a field of its own.
    for (const map of Object.values(MAPS)) {
      for (const [name, value] of Object.entries(c[map] || {})) shown[map + SEP + name] = value;
      delete shown[map];
    }
    return shown;
  }

  _label(field) {
    const t = textsFor(this._hass);
    if (field.name.includes(SEP)) {
      const [map, name] = field.name.split(SEP);
      return map === 'kind_colors' ? t['kind' + name[0].toUpperCase() + name.slice(1)] || name : name;
    }
    const key = {
      view: 'view', entry: 'entry', title: 'title', lists: 'lists', person: 'person', show_done: 'showDone', add_tasks: 'addTasks',
      ask: 'ask', forget_after: 'forget', plan: 'plan', layout: 'layout', show_rooms: 'showRooms', show_pack: 'showPack', plans: 'plans',
      style: 'style', accent_color: 'accent', background_color: 'background', background_opacity: 'opacity', text_color: 'textColor', fill: 'fill', color_by: 'colorBy',
      days: 'days', start: 'startAt', show_plans: 'showPlans', show_deadlines: 'showDeadlines', show_persons: 'showPersons', max: 'max',
      by_aisle: 'byAisle', show_drives: 'showDrives', show_tomorrow: 'showTomorrow',
    }[field.name];
    return t[key] || field.name;
  }

  _changed(ev) {
    ev.stopPropagation();
    const before = viewOf(this._config);
    const value = { ...ev.detail.value };
    // Another view reads from other places: what was chosen for the old one does not carry over.
    if (viewOf(value) !== before) for (const key of Object.keys(value)) if (!['view', 'entry', 'title', 'style', 'accent_color', 'background_color', 'background_opacity', 'text_color'].includes(key)) delete value[key];
    for (const key of Object.keys(value)) {
      if (!key.includes(SEP)) continue;
      const [map, name] = key.split(SEP);
      if (value[key] != null && value[key] !== '' && value[key] !== 'none') value[map] = { ...(value[map] || {}), [name]: value[key] };
      delete value[key];
    }
    if (Number(value.background_opacity) === 100) delete value.background_opacity;
    if (Number(value.fill) === 16) delete value.fill;
    if (value.color_by === 'none') delete value.color_by;
    if (value.style === 'ha') delete value.style;
    for (const key of Object.keys(value)) {
      const v = value[key];
      if (v == null || v === '' || (Array.isArray(v) && !v.length)) delete value[key];
    }
    if (value.ask === 'auto') delete value.ask;
    if (value.by_aisle === true) delete value.by_aisle;
    if (value.show_drives === true) delete value.show_drives;
    if (value.show_tomorrow === false) delete value.show_tomorrow;
    const config = { type: this._config.type || 'custom:orgaia-card', ...value };
    this._config = config;
    this.dispatchEvent(new CustomEvent('config-changed', { detail: { config }, bubbles: true, composed: true }));
    this._load();
    this._render();
  }

  _render() {
    if (!this._hass || !this.isConnected) return;
    if (!this._form) {
      this._form = document.createElement('ha-form');
      this._form.computeLabel = (field) => this._label(field);
      this._form.addEventListener('value-changed', (ev) => this._changed(ev));
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = this._shown();
    this._form.schema = this._schema();
  }
}

/*
 * The ready-made dashboard: today on the left, the shopping to tick off on the right, the week below.
 * The integration puts it into the sidebar when that was chosen in the setup; in a dashboard of one's
 * own it is `strategy: { type: custom:orgaia }`. It is Tinte unless told `style: ha`.
 */
class OrgaiaDashboardStrategy extends HTMLElement {
  static async generate(config, hass) {
    const t = textsFor(hass);
    const base = { type: 'custom:orgaia-card', ...(config && config.entry ? { entry: config.entry } : {}), ...(config && config.style === 'ha' ? {} : { style: 'tinte' }) };
    const section = (title, card) => ({ type: 'grid', cards: [{ type: 'heading', heading: title }, { ...base, ...card, title: '' }] });
    return {
      title: (config && config.title) || 'Orgaia',
      views: [
        {
          title: (config && config.title) || 'Orgaia',
          path: 'home',
          icon: 'mdi:calendar-check',
          type: 'sections',
          max_columns: 2,
          sections: [
            section(t.viewToday, { view: 'today', show_tomorrow: true }),
            section(t.viewShopping, { view: 'shopping' }),
            { ...section(t.dashWeek, { view: 'agenda', days: 7 }), column_span: 2 },
          ],
        },
      ],
    };
  }
}

if (!customElements.get('ll-strategy-dashboard-orgaia')) customElements.define('ll-strategy-dashboard-orgaia', OrgaiaDashboardStrategy);

if (!customElements.get('orgaia-card-editor')) customElements.define('orgaia-card-editor', OrgaiaCardEditor);

if (!customElements.get('orgaia-card')) {
  customElements.define('orgaia-card', OrgaiaCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: 'orgaia-card',
    name: 'Orgaia',
    description: 'An Orgaia group: lists to tick off, the shopping, tasks, today at a glance, a timetable, rosters or what is coming up. The view is chosen in the editor.',
    preview: true,
    documentationURL: 'https://github.com/PixelDevIO/HA-Orgaia#orgaia-card',
  });
}
