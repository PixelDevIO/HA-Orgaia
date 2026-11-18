# Orgaia for Home Assistant

Your family's **Orgaia** group in Home Assistant: every task and shopping list as a **to-do list**, appointments and planned tasks in a **calendar**, and **sensors** for what is open, due today or overdue. Updates arrive live. With the **Orgaia card** the family ticks off, adds articles and takes over the shopping right at the dashboard, once an admin allowed it in the app.

Orgaia is end-to-end encrypted, and stays that way: Home Assistant joins the group with **its own key**, like a member, and decrypts the entries on your own server. The Orgaia service never sees your data in clear text.

*Deutsche Kurzbeschreibung weiter unten.*

## Requirements

- An Orgaia group with **Orgaia Plus**.
- An admin of the group, who confirms Home Assistant in the app.
- Home Assistant 2025.6 or newer.

## Installation

### HACS / Marketplace (custom repository)

1. Marketplace (HACS) → ⋮ → **Custom repositories** → add `https://github.com/PixelDevIO/HA-Orgaia`, category **Integration**.
2. Install **Orgaia** and restart Home Assistant.

### Manual

Copy `custom_components/orgaia` into your `config/custom_components/` folder and restart Home Assistant.

## Setup

1. In the Orgaia app, open the group → **Home Assistant** → **Connect Home Assistant**. Copy the link.
2. In Home Assistant: **Settings → Devices & services → Add integration → Orgaia**. Paste the link and choose the name the group's admins will see.
3. Home Assistant now waits (up to 10 minutes) while an admin confirms it in the app. Compare the safety number shown in Home Assistant with the one in the app.

Connect several groups by adding the integration again with a link from each group. Every group gets its own key, so the groups never learn of each other.

Home Assistant is **not counted as a person** in the group. A group can connect up to 3 integrations.

## Entities

Per group (device named after the group):

| Entity | Description |
|---|---|
| `todo.<group>_<list>` | One per task or shopping list. Repeating tasks show their current occurrence. Assignees, note and subtasks are in the description. Ticked items stay for 14 days. |
| `calendar.<group>_calendar` | Appointments and tasks with a time slot, including repetitions and their exceptions; tasks with a deadline on their day ("Due: …"), and released shopping lists on the day they are to be bought by. What is ticked off starts with ✓. |
| `sensor.<group>_open_tasks` | Open tasks, including today's repeating ones. Attribute `titles`. |
| `sensor.<group>_due_today` | Tasks due today. |
| `sensor.<group>_overdue` | Everything that should be done by now: one-off tasks past their due date, today's repeating and packing tasks past their time, and planned task slots that ended unticked. The app lists the last two apart, as "missed"; here they count as overdue, so one automation can remind of all of it. |
| `sensor.<group>_shopping_list` | Items still to buy. |
| `sensor.<group>_shopping_waiting` | Released shopping lists nobody took over yet. |
| `binary_sensor.<group>_school_holidays` | On during the school holidays entered in the app. |
| `sensor.<group>_next_appointment` | Start of the next appointment, with title and location. |
| `sensor.<group>_connection` | Diagnostic: `ok`, `offline`, `needs_plus`, `update_required` or `removed`. Attribute `last_sync`: when the group was last read. |

Per person of the group (device named "<person> (<group>)"):

| Entity | Description |
|---|---|
| `todo.<person>_<group>_tasks` | Everything assigned to the person, from all task lists. |
| `calendar.<person>_<group>_calendar` | Appointments and planned tasks the person takes part in. |
| `sensor.<person>_<group>_open_tasks`, `_due_today`, `_overdue` | The counts above, for this person. |
| `sensor.<person>_<group>_next_task` | Title of the person's open task due next; attribute `due`. |

New lists and people appear by themselves; deleted lists and people who left disappear.

### Shopping lists

A shopping list of a group is written by everybody until somebody **releases** it; then whoever is out anyway takes it over. The to-do entity of a shopping list tells where it stands, in its attributes: `shopping_state` (`off`, `draft`, `ready`, `going`), `open`, `bought`, `released_by`, `released_at`, `due`, `for`, `note`, `shopper` and `shopper_entity`. Quantities are part of the title ("Milk (2 l)"); articles that came onto the list after the release carry 🆕 in the description.

```yaml
# Conditional card: only while a list waits for somebody
type: conditional
conditions:
  - condition: state
    entity: todo.familie_einkauf
    attribute: shopping_state
    state: ready
card:
  type: markdown
  content: "🛒 **{{ state_attr('todo.familie_einkauf', 'released_by') }}** released the shopping list."
```

### Timetables and rosters

They show as in the app, worked out on your Home Assistant; nothing extra is fetched for them.

- A **timetable** is a to-do list with today's packing tasks ("Pack sports kit"), due at the packing time. They count in the sensors, appear in the person's to-do list and fire `task_overdue` when not ticked off in time. The school day is in the person's calendar, holidays left out.
- A **roster** puts working time into the person's calendar: the fixed week with its days off, or the shifts entered day by day (with the shift's name unless the roster shows "busy" only). It has no to-do list.

Each plan also has entities of its own, on the device of the person it is for:

| Entity | Description |
|---|---|
| `sensor.<person>_<group>_school_today` | Today at school: from when to when ("08:00–13:05"), or that there is no school. Attributes: `status` (`school`, `free`, `holiday`), `start`, `end`, `lessons` (period, start, end, subject, room), `pack_today`, `pack_tomorrow`, `tomorrow`, `week` (A/B weeks), `holiday`. |
| `binary_sensor.<person>_<group>_at_school` | On between the first and the last lesson of today. |
| `calendar.<person>_<group>_timetable` | The timetable lesson by lesson, for a calendar card of its own. |
| `sensor.<person>_<group>_work_today` | Today's working time or shift. Attributes: `spans`, `start`, `end`, `shift`, `code`, `tomorrow`, `next_days` (seven days). |
| `binary_sensor.<person>_<group>_at_work` | On during working time, night shifts included. |

An example for a dashboard, with standard cards only:

```yaml
type: vertical-stack
cards:
  - type: markdown
    title: School today
    content: >-
      {% set s = 'sensor.ben_familie_school_today' %}
      {% for l in state_attr(s, 'lessons') or [] %}
      {{ l.period }}. {{ l.start }} **{{ l.subject }}**{% if l.room %} ({{ l.room }}){% endif %}

      {% else %}{{ states(s) }}{% endfor %}
      {% if state_attr(s, 'pack_today') %}🎒 Pack for tomorrow: {{ state_attr(s, 'pack_today') | join(', ') }}{% endif %}
  - type: entities
    entities:
      - entity: binary_sensor.ben_familie_at_school
      - entity: sensor.anna_familie_work_today
      - entity: binary_sensor.anna_familie_at_work
  - type: calendar
    initial_view: listWeek
    entities:
      - calendar.ben_familie_timetable
```

Titles follow Home Assistant's language (German or English).

### Subscribed calendars

A calendar the family subscribed to in Orgaia (school, club, waste collection) shows in the group's calendar and in the calendars of the people it is for. Like every phone, Home Assistant fetches it itself, straight from its address, every 6 hours; the entries never go through the Orgaia service and are kept in their own storage file. When a fetch fails, the entries of the last good one stay. They fire `event_starting`, but never `event_created` or `event_changed`. Only HTTPS addresses on the internet are fetched: an address (or a redirect) that points into the home network, such as the router or `homeassistant.local`, is refused, since anybody in the group can enter one.

### People in Home Assistant

Under **Settings → Devices & services → Orgaia → Configure**, choose which Home Assistant person (`person.*`) each person of the group is. People with the same name are suggested. Events and person sensors then carry the person entity too (`assignee_entities`, `completed_by_entity`, `person_entity`), so a notification can go to the right phone.

## Automations

Every change that matters fires the event `orgaia_event`. The same events are offered as **device triggers** on the group's device (Automation → Add trigger → Device → your group).

| `type` | When |
|---|---|
| `task_created` | A task or shopping item was added. |
| `task_assigned` | Somebody was assigned to an open task (`assigned`, `assigned_entities`). |
| `task_completed` | A task was ticked off (`completed_by`, `completed_by_entity`). A task that comes back fires it too, for the round just finished. |
| `task_reopened` | A ticked task was opened again. |
| `task_overdue` | A task passed its due date or time. |
| `event_created` | An appointment was added. |
| `event_changed` | Time, place, title, repetition or participants of an appointment changed. |
| `event_starting` | An appointment begins. For a reminder ahead of time, use the calendar trigger with an offset. |

Every event carries `group`, `device_id`, `item_id`, `title`, `list`, `assignees` (names) and `assignee_entities`; tasks also `list_type`, `due` and `date` (the occurrence of a repeating task), appointments `start`, `end`, `all_day` and `location`.

Nothing fires for what was already there when Home Assistant started, and every change fires once. After a restart of up to 15 minutes (an update, for example), what changed meanwhile and appointments that began meanwhile still fire once Home Assistant is running, with `late: true` in the event data. After a longer break nothing is caught up, so automations do not act on old news. The same mark is set on what changed while the Orgaia service could not be reached for more than 15 minutes.

**Examples**

Tell whoever is responsible when the bin chore is late:

```yaml
triggers:
  - trigger: event
    event_type: orgaia_event
    event_data:
      type: task_overdue
conditions:
  - condition: template
    value_template: "{{ trigger.event.data.assignee_entities | count > 0 }}"
actions:
  - action: notify.notify
    data:
      title: "Still open: {{ trigger.event.data.title }}"
      message: "For {{ trigger.event.data.assignees | join(', ') }}"
```

Flash the hallway light when the shopping is done:

```yaml
triggers:
  - trigger: event
    event_type: orgaia_event
    event_data:
      type: task_completed
      list_type: shopping
actions:
  - action: light.turn_on
    target:
      entity_id: light.hallway
    data:
      flash: short
```

Remind 30 minutes before an appointment:

```yaml
triggers:
  - trigger: calendar
    event: start
    entity_id: calendar.familie_calendar
    offset: "-0:30:0"
actions:
  - action: notify.notify
    data:
      message: "{{ trigger.calendar_event.summary }} at {{ trigger.calendar_event.location }}"
```

## Ticking off and adding from Home Assistant

Home Assistant only reads a group until an **admin allows it to write**: in the Orgaia app, open the group → **Manage › Home Assistant** and switch on **"May tick off and add"** for this Home Assistant. It can be switched off again at any time.

Who ticked off must be known, also at a display on the wall that belongs to nobody. So every change is made **in the name of a person of the group**, and the app shows that name with the note "via Home Assistant". The standard to-do cards stay display only, because they cannot ask who you are.

### Orgaia card

The card comes with the integration; no resource has to be added by hand. In the dashboard, add a card and pick **Orgaia**, or:

```yaml
type: custom:orgaia-card
# all optional:
entry: 01JABC…            # the group, when more than one is connected
title: Familie
lists: [Haushalt, Einkauf] # names or ids; without it all lists show
show_done: false           # also list tasks that are ticked off
add_tasks: false           # a field to add tasks (articles can always be added)
forget_after: 60           # seconds without a tap until the card forgets who it was; 0 = never
ask: always                # ask even when the signed-in user is known
```

**First tap who you are, then tick off.** Without a name nothing happens. On a personal phone the card knows who is signed in, when that user's person is assigned under **Configure** (see *People in Home Assistant*); on a shared display everybody taps their name, and after a minute without a tap the card forgets it again. On a shopping list the card adds articles (with a quantity), releases the list, and offers "I'll do it", "Not after all" and "Shopping done". Where everybody ticks off their own part ("each for themselves"), the tick is the chosen person's own.

Anybody at the display can tap any name: the card keeps track of who did what among people who trust each other; it is no lock.

#### Views

One card, several views. The editor first asks for the **view** and then offers only what that view can be told, with the group's lists, plans and people to choose from:

| `view` | Shows | Options |
| --- | --- | --- |
| `lists` (default) | all lists, to tick off and add to | `lists`, `show_done`, `add_tasks`, `ask`, `forget_after` |
| `shopping` | only the shopping lists | `lists`, `ask`, `forget_after` |
| `tasks` | only the task lists | `lists`, `person` (only what is assigned to them), `show_done`, `add_tasks` |
| `timetable` | a timetable as a week grid, this week and the next, with the lesson that is on and what to pack today | `plan`, `layout: week \| day`, `show_rooms`, `show_pack` |
| `roster` | rosters side by side, day by day | `plans`, `days` (1–14), `start: today \| week` |
| `agenda` | what is coming up, day by day | `days` (1–31), `person`, `show_plans`, `show_deadlines`, `show_persons`, `max` |

```yaml
type: custom:orgaia-card
view: timetable
plan: Leonie        # name or id; without it the first timetable
```

Put the card on a dashboard several times for several views. The card is listed among the dashboard resources by the integration itself; after an update of the integration, reload the browser once.

### Actions

For automations and scripts (an NFC tag at the bin, a button next to the fridge). All of them need `person`: a name from the group, or a `person.*` entity assigned under **Configure**. `list` is the list's to-do entity or its name. With more than one group, add `config_entry_id`.

| Action | What it does |
|---|---|
| `orgaia.set_done` | Ticks off `item` (title, or the id the to-do list gives), or opens it again with `done: false`. Of a repeating task the day that is due now. |
| `orgaia.add_article` | Puts `title` (and `quantity`) on a shopping list; on a released list it is marked as new. |
| `orgaia.add_task` | Adds a task to a task list, optionally with `due_date` and `assignees`. |
| `orgaia.release_shopping_list` | Says the list is complete, optionally with `due_date`, `for` and `note`. |
| `orgaia.withdraw_shopping_list` | Takes the release back. |
| `orgaia.take_shopping` / `orgaia.drop_shopping` | "I'll do it" / "Not after all". |
| `orgaia.finish_shopping` | Ends the trip: what was bought leaves the list. |

```yaml
# The tag at the bin: whoever scans it has taken the bins out
triggers:
  - trigger: tag
    tag_id: bins
actions:
  - action: orgaia.set_done
    data:
      person: "{{ states.person | selectattr('attributes.user_id', 'eq', trigger.context.user_id) | map(attribute='entity_id') | first }}"
      item: Müll rausbringen
```

A change reaches the service at once or fails with a message; nothing is kept for later, so Home Assistant never shows a tick the others do not see.

## Good to know

- **Service not reachable**: everything stays on screen as last read, and `sensor.<group>_connection` says `offline` (with `last_sync`). Home Assistant also starts without a connection. Changes arrive as soon as the service is back.
- **Time zone**: Orgaia stores times as wall-clock times. Home Assistant reads them in its own time zone, so it should be the one your family lives in.
- **Wrong clock**: if Home Assistant's clock is more than five minutes off, the integration goes by the service's time, so changes are not skipped as "from the future".
- **Plus ended**: Home Assistant stops reading and shows a repair notice. Once Plus is renewed it picks up again by itself.
- **Removed from the group**: Home Assistant shows a notice under Settings → Devices & services that asks for a new link from the app.
- **Removing the integration** leaves the group, so the admins see Home Assistant is gone.
- **Privacy**: titles and names are decrypted on your Home Assistant. The lists of titles on the count sensors and the title and place of the next appointment are kept out of the recorder. What stays in its history: the state of the "next task" sensor (a title), and the data of `orgaia_event` in the logbook. Exclude `sensor.*_next_task` in the `recorder:` settings if you do not want that. The integration's storage file (`.storage/orgaia.*`) holds the group keys and every entry in plain text and goes into every Home Assistant backup: keep backups encrypted. Private lists in Orgaia never reach Home Assistant. Diagnostics hold only counts, no content and no keys.

## License

The integration is licensed under the [Apache License 2.0](LICENSE). The license does not cover the name and logo "Orgaia", and the Orgaia app and sync service are not part of it.

---

## Deutsch

Die **Orgaia**-Gruppe deiner Familie in Home Assistant: jede Aufgaben- und Einkaufsliste als **To-do-Liste**, Termine und geplante Aufgaben im **Kalender**, dazu **Sensoren** für Offenes, heute Fälliges und Überfälliges. Änderungen kommen live an.

Alles bleibt Ende-zu-Ende-verschlüsselt: Home Assistant tritt der Gruppe mit eigenem Schlüssel bei und entschlüsselt die Einträge auf deinem eigenen Server.

**Voraussetzung:** eine Gruppe mit Orgaia Plus und ein Admin, der Home Assistant in der App bestätigt.

**Einrichten:**

1. In der App die Gruppe öffnen → **Home Assistant** → **Home Assistant verbinden** und den Link kopieren.
2. In Home Assistant: **Einstellungen → Geräte & Dienste → Integration hinzufügen → Orgaia**, Link einfügen.
3. Ein Admin bestätigt in der App. Die Sicherheitsnummer in Home Assistant und in der App muss gleich sein.

Home Assistant zählt nicht als Person; pro Gruppe gehen bis zu 3 Integrationen. Für jede Person der Gruppe gibt es eine eigene To-do-Liste, einen Kalender und Sensoren; unter **Konfigurieren** ordnest du ihr eine Person in Home Assistant zu. Für Automationen gibt es das Ereignis `orgaia_event` (auch als Geräte-Auslöser), zum Beispiel wenn eine Aufgabe erledigt oder überfällig ist oder ein Termin beginnt. Stundenpläne erscheinen als To-do-Liste mit den Pack-Aufgaben von heute, Schulzeit und Arbeitszeit aus Dienstplänen stehen im Kalender der Person. Abonnierte Kalender (Schule, Verein, Müllabfuhr) holt Home Assistant selbst alle 6 Stunden und zeigt sie bei den Personen, für die sie gelten. Ist der Orgaia-Dienst nicht erreichbar, bleibt der letzte Stand sichtbar und der Sensor „Verbindung“ zeigt `offline`. Nach einem Neustart von höchstens 15 Minuten kommen die Ereignisse von zwischendurch nach, mit `late: true`. Dieselbe Markierung bekommt, was sich geändert hat, während der Dienst länger als 15 Minuten nicht erreichbar war. „Überfällig“ umfasst auch Serien- und Pack-Aufgaben nach ihrer Uhrzeit und verpasste Zeitfenster. Home Assistant sollte auf die Zeitzone eingestellt sein, in der ihr lebt.

**Stunden- und Dienstpläne:** Je Plan gibt es zusätzlich `sensor.…_school_today` (Stunden von heute mit Fach, Raum und Zeiten, was zu packen ist, morgen) und `binary_sensor.…_at_school`, einen eigenen Kalender mit den einzelnen Stunden, `sensor.…_work_today` (Arbeitszeit oder Schicht, die nächsten 7 Tage) und `binary_sensor.…_at_work`, außerdem `binary_sensor.<gruppe>_school_holidays`. Ein Beispiel-Dashboard mit Standardkarten steht oben unter *Timetables and rosters*.

**Einkaufslisten:** Die To-do-Entität zeigt in `shopping_state`, ob an der Liste noch geschrieben wird (`draft`), ob sie freigegeben ist (`ready`) oder jemand einkauft (`going`), dazu wer freigegeben hat, bis wann und wer einkauft. Mengen stehen im Titel, später dazugekommene Artikel tragen 🆕.

**Abhaken und eintragen:** Home Assistant liest nur, bis ein Admin in der App unter **Verwalten › Home Assistant** „Darf abhaken und eintragen“ einschaltet. Danach geht alles über die **Orgaia-Karte** (`type: custom:orgaia-card`, sie kommt mit der Integration): **erst antippen, wer man ist, dann abhaken**, Artikel auf die Einkaufsliste setzen, Liste freigeben, „Mache ich“ und „Einkauf fertig“. In der App steht der Name mit dem Zusatz „über Home Assistant“. Nach einer Minute ohne Tippen vergisst die Karte, wer es war; auf dem eigenen Handy kennt sie die angemeldete Person, wenn diese unter **Konfigurieren** zugeordnet ist. Die Karte hat mehrere **Ansichten**, die im Editor gewählt werden: alle Listen, nur Einkauf, nur Aufgaben (auch nur einer Person), **Stundenplan** als Wochenraster, **Dienstplan** und **Termine**; dazu jeweils die passende Quelle (Liste, Plan, Person). Die Standard-To-do-Karten bleiben reine Anzeige. Für Automationen gibt es die Aktionen `orgaia.set_done`, `orgaia.add_article`, `orgaia.add_task`, `orgaia.release_shopping_list`, `orgaia.take_shopping`, `orgaia.finish_shopping` und weitere, jeweils mit `person`.

**Lizenz:** Apache 2.0 (siehe [LICENSE](LICENSE)). Name und Logo „Orgaia“ sowie App und Dienst sind davon nicht umfasst.
