# Orgaia for Home Assistant

Your family's **Orgaia** group in Home Assistant: every task and shopping list as a **to-do list**, appointments and planned tasks in a **calendar**, and **sensors** for what is open, due today or overdue. Updates arrive live. With the **Orgaia card** the family ticks off, adds articles and takes over the shopping right at the dashboard, once an admin allowed it in the app.

Orgaia is end-to-end encrypted, and stays that way: Home Assistant joins the group with **its own key**, like a member, and decrypts the entries on your own server. The Orgaia service never sees your data in clear text.

*Deutsche Kurzbeschreibung weiter unten.*

## Requirements

- An Orgaia group with **Orgaia Plus**.
- An admin of the group, who confirms Home Assistant in the app.
- Home Assistant 2025.6 or newer.

## Installation

### HACS / Marketplace

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=PixelDevIO&repository=HA-Orgaia&category=integration)

1. Click the button above, or in Marketplace (HACS) → ⋮ → **Custom repositories** add `https://github.com/PixelDevIO/HA-Orgaia`, category **Integration**.
2. Install **Orgaia** and restart Home Assistant.

### Manual

Copy `custom_components/orgaia` into your `config/custom_components/` folder and restart Home Assistant.

## Setup

[![Add the Orgaia integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=orgaia)

1. In the Orgaia app, open the group → **Home Assistant** → **Connect Home Assistant**. Tap **Copy and open in Home Assistant**: the link is copied and your Home Assistant opens on "Add integration: Orgaia".
2. Or by hand: **Settings → Devices & services → Add integration → Orgaia**. Paste the link and choose the name the group's admins will see.
3. Home Assistant now waits (up to 10 minutes) while an admin confirms it in the app. Compare the safety number shown in Home Assistant with the one in the app.

Connect several groups by adding the integration again with a link from each group. Every group gets its own key, so the groups never learn of each other.

Home Assistant is **not counted as a person** in the group. A group can connect up to 3 integrations, for example the Home Assistant of three households of a club.

To connect the integration to the group again with a fresh link (after it was removed in the app, say), use **⋮ → Reconfigure** on the integration: entities, automations and dashboards stay as they are.

### Options

Under **Settings → Devices & services → Orgaia → Configure**:

- **People**: which Home Assistant person each person of the group is (see *People in Home Assistant*).
- **Settings**: which lists become to-do lists (none chosen: all); whether every person gets a device of their own with to-do list, calendar and sensors (switch off for large groups); how many days ticked-off tasks stay (normally 14); and in whose name a voice assistant puts articles on a shopping list.

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
| `sensor.<group>_today` | Today in a few words ("2 appointments, 3 tasks"). Attributes: `speech` (the day in sentences, for a loudspeaker), `appointments`, `due`, `overdue`, `school`, `work` and `shopping`. For tomorrow or another day use `orgaia.get_agenda`. |
| `sensor.<group>_open_drives` | Drives in the next 14 days nobody took yet. Attribute `drives`: title, item, date, start, `missing` (`to`/`from`) and who it is for. |
| `sensor.<group>_connection` | Diagnostic: `ok`, `offline`, `needs_plus`, `update_required` or `removed`. Attribute `last_sync`: when the group was last read. |
| `binary_sensor.<group>_may_tick_off_and_add` | Diagnostic: on when an admin allowed Home Assistant to write. |

Per person of the group (device named "<person> (<group>)"):

| Entity | Description |
|---|---|
| `todo.<person>_<group>_tasks` | Everything assigned to the person, from all task lists. |
| `calendar.<person>_<group>_calendar` | Appointments and planned tasks the person takes part in. |
| `sensor.<person>_<group>_open_tasks`, `_due_today`, `_overdue` | The counts above, for this person. |
| `sensor.<person>_<group>_next_task` | Title of the person's open task due next; attribute `due`. |
| `sensor.<person>_<group>_next_appointment` | Start of the person's next appointment. |
| `sensor.<person>_<group>_today` | The person's day, as `sensor.<group>_today`. |
| `binary_sensor.<person>_<group>_appointment_now` | On while an appointment of the person is on. |
| `binary_sensor.<person>_<group>_out_shopping` | On while the person said "I'll do it" and is out shopping. |

New lists and people appear by themselves; deleted lists and people who left disappear.

### Shopping lists

A shopping list of a group is written by everybody until somebody **releases** it; then whoever is out anyway takes it over. The to-do entity of a shopping list tells where it stands, in its attributes: `shopping_state` (`off`, `draft`, `ready`, `going`), `open`, `bought`, `released_by`, `released_at`, `due`, `for`, `note`, `shopper` and `shopper_entity`. Quantities are part of the title ("Milk (2 l)"); articles that came onto the list after the release carry 🆕 in the description, articles the shopper did not get ✗, and the aisle (🏷 Bakery) is there too. Further attributes: `not_got` (titles not got on the last trip) and `fixed_purchases` (the list's fixed purchases such as "Weekly shop", by name).

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

- A **timetable** is a to-do list with today's packing tasks ("Pack sports kit"), due at the packing time. They count in the sensors, appear in the person's to-do list and fire `task_overdue` when not ticked off in time. The school day is in the person's calendar, holidays left out, and so is care after school (reliable school or OGS) when the timetable has it. With "Plan pick-up" in the app, care asks "who picks up?" like a drive, on the card too.
- A **roster** puts working time into the person's calendar: the fixed week with its days off, or the shifts entered day by day (with the shift's name unless the roster shows "busy" only). It has no to-do list.

Each plan also has entities of its own, on the device of the person it is for:

| Entity | Description |
|---|---|
| `sensor.<person>_<group>_school_today` | Today at school: from when to when ("08:00–13:05"), or that there is no school. Attributes: `status` (`school`, `free`, `holiday`), `start`, `end`, `lessons` (period, start, end, subject, room), `pack_today`, `pack_tomorrow`, `tomorrow`, `week` (A/B weeks), `holiday`, `changed` (today differs from the usual week), `note`, `exams` (tests today), `exams_ahead` (the next ones) and `care` (care after school today: `kind` `vs` for reliable school or `ogs`, `start`, `end`). Single changed days and timetables valid for a half-year only are taken into account. |
| `binary_sensor.<person>_<group>_at_school` | On between the first and the last lesson of today. Attribute `care_until`: when care after school ends today. |
| `binary_sensor.<person>_<group>_in_care_after_school` | On from the end of school to the end of care (reliable school or OGS), only for timetables with care. Attributes: `until`, `kind`. |
| `calendar.<person>_<group>_timetable` | The timetable lesson by lesson, for a calendar card of its own, with care after school as one more entry. |
| `sensor.<person>_<group>_work_today` | Today's working time or shift. Attributes: `spans`, `start`, `end`, `shift`, `code`, `standby`, `tomorrow`, `next_days` (seven days), `hours_week`. |
| `binary_sensor.<person>_<group>_at_work` | On during working time, night shifts included; on-call shifts are not working time. |
| `binary_sensor.<person>_<group>_on_call` | On during an on-call shift (only for rosters that have one). |

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
| `shopping_released` / `shopping_taken` / `shopping_done` | A shopping list was released, somebody took it over, the trip ended (`bought`, `left`, `not_got`, `shopper`, `released_by` and their `_entity`). |
| `drive_needed` | An appointment in the next 14 days needs a drive there or back (`way`: `to`/`from`) and nobody took it yet. |
| `drive_taken` | Somebody took a drive (`driver`, `driver_entity`, `previous_driver`), or gave it back. |
| `rsvp_changed` | Somebody answered an invitation (`person`, `person_entity`, `answer`, `before`, `all_answered`). |
| `poll_decided` | A date poll was decided (`start`, `end`, `location`) or called off (`cancelled: true`). |

A `task_created` on a shopping list also says whether somebody is out shopping right now (`shopping_state`, `added_late`, `shopper`, `shopper_entity`), so an article added late can reach their phone.

Every event carries `group`, `device_id`, `item_id`, `title`, `list`, `assignees` (names) and `assignee_entities`; tasks also `list_type`, `due` and `date` (the occurrence of a repeating task), appointments `start`, `end`, `all_day` and `location`.

Nothing fires for what was already there when Home Assistant started, and every change fires once. After a restart of up to 15 minutes (an update, for example), what changed meanwhile and appointments that began meanwhile still fire once Home Assistant is running, with `late: true` in the event data. After a longer break nothing is caught up, so automations do not act on old news. The same mark is set on what changed while the Orgaia service could not be reached for more than 15 minutes.

### Blueprints

Ready-made automations, to import with one click. Each one asks for the person and their phone (Companion app); the buttons in the notifications act in that person's name.

| Blueprint | What it does | |
|---|---|---|
| Overdue task with a "Done" button | An overdue task reaches the phone of whoever is responsible; "Done" ticks it off. | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FPixelDevIO%2FHA-Orgaia%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Forgaia%2Foverdue_task_done_button.yaml) |
| Packing in the evening | At a chosen time: what to pack for school tomorrow, and tomorrow's tests. | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FPixelDevIO%2FHA-Orgaia%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Forgaia%2Fpack_in_the_evening.yaml) |
| Shopping released | Somebody who is out gets told, with "I'll do it". | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FPixelDevIO%2FHA-Orgaia%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Forgaia%2Fshopping_released_when_away.yaml) |
| Article added while shopping | The shopper's phone hears about it. | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FPixelDevIO%2FHA-Orgaia%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Forgaia%2Farticle_added_while_shopping.yaml) |
| Nobody drives yet | A drive is still open: ask somebody, with "I'll drive". | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FPixelDevIO%2FHA-Orgaia%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Forgaia%2Fdrive_needed.yaml) |
| Appointment reminder | Before each appointment of an Orgaia calendar, with place and drives. | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FPixelDevIO%2FHA-Orgaia%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Forgaia%2Fappointment_reminder.yaml) |

### Examples

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

Read the day out in the morning:

```yaml
triggers:
  - trigger: time
    at: "07:00:00"
actions:
  - action: orgaia.get_agenda
    response_variable: agenda
  - action: tts.speak
    target:
      entity_id: tts.home_assistant_cloud
    data:
      media_player_entity_id: media_player.kitchen
      message: "{{ agenda.speech }}"
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

Who ticked off must be known, also at a display on the wall that belongs to nobody. So every change is made **in the name of a person of the group**, and the app shows that name with the note "via Home Assistant".

- **Standard to-do lists and calendars**: a signed-in user whose Home Assistant person is assigned under **Configure** can tick off in the to-do lists, add tasks and articles ("Bread, 2 eggs" become two articles), and create appointments in the Orgaia calendars (in a person's calendar that person takes part). Other users get a message instead, and nothing is written. Simple repetitions (daily, weekly on weekdays, monthly, yearly, with an end date) are taken over.
- **Voice assistants** (Assist, "put milk on the shopping list") do not know who is speaking. Only when **Configure → Settings → Articles by voice in the name of** names a person do they add articles, in that person's name. They never tick off.
- **The Orgaia card** asks who you are, for shared displays.

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

**First tap who you are, then tick off.** Without a name nothing happens. On a personal phone the card knows who is signed in, when that user's person is assigned under **Configure** (see *People in Home Assistant*); on a shared display everybody taps their name, and after a minute without a tap the card forgets it again. On a shopping list the card adds articles (with a quantity), sorts them by aisle, changes counted quantities with **+ and −**, adds a list's **fixed purchases** ("+ Weekly shop"), releases the list, and offers "I'll do it", "Not after all" and "Shopping done"; while out shopping every article has **"Not got"**. Where everybody ticks off their own part ("each for themselves"), the tick is the chosen person's own.

Anybody at the display can tap any name: the card keeps track of who did what among people who trust each other; it is no lock.

#### Views

One card, several views. The editor first asks for the **view** and then offers only what that view can be told, with the group's lists, plans and people to choose from:

| `view` | Shows | Options |
| --- | --- | --- |
| `lists` (default) | all lists, to tick off and add to | `lists`, `show_done`, `add_tasks`, `by_aisle`, `ask`, `forget_after` |
| `shopping` | only the shopping lists | `lists`, `by_aisle` (default on), `ask`, `forget_after` |
| `tasks` | only the task lists | `lists`, `person` (only what is assigned to them), `show_done`, `add_tasks` |
| `timetable` | a timetable as a week grid, this week and the next, with the lesson that is on and what to pack today | `plan`, `layout: week \| day`, `show_rooms`, `show_pack` |
| `roster` | rosters side by side, day by day | `plans`, `days` (1–14), `start: today \| week` |
| `today` | today at a glance for a wall display: appointments, school with tests and packing, work, what is due and overdue, the shopping | `person`, `show_tomorrow` |
| `agenda` | what is coming up, day by day, with who drives and buttons to take a drive | `days` (1–31), `person`, `show_plans`, `show_deadlines`, `show_persons`, `show_drives`, `max`, `ask`, `forget_after` |

```yaml
type: custom:orgaia-card
view: timetable
plan: Leonie        # name or id; without it the first timetable
```

#### Appearance

Every view has an **Appearance** section in the editor; the timetable, roster and appointments also offer colours of their own:

```yaml
accent_color: teal         # today, buttons, ticks; one of Home Assistant's colours or any CSS colour
background_color: '#102030'
background_opacity: 40     # per cent; 0 shows the dashboard's background through the card
text_color: white
fill: 30                   # timetable, roster: how strong the coloured fields are, per cent
subject_colors:            # timetable
  Mathe: red
  Sport: green
shift_colors:              # roster
  Nacht: deep-purple
color_by: kind             # appointments: a coloured bar by person or by kind
kind_colors:               # event, task, school, work, due, shopping
  work: orange
```

Put the card on a dashboard several times for several views. The card is listed among the dashboard resources by the integration itself; after an update of the integration the card says so and offers to reload the page.

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
| `orgaia.set_not_got` | Marks an article as not got (`missed: false` takes it back). |
| `orgaia.set_quantity` | Sets `quantity`, or counts it up or down with `step` (+1, −1). |
| `orgaia.set_aisle` | Sorts an article into an `aisle` (produce, bakery, dairy, …), remembered for next time. |
| `orgaia.add_fixed_purchase` | Puts a fixed purchase (`set`, such as "Weekly shop") on the list. |
| `orgaia.take_drive` / `orgaia.drop_drive` | Takes or gives back the drive to an appointment (`item`), `which: to \| from \| both`, optionally on a `date`. |
| `orgaia.get_agenda` | Returns a day (or up to 14) as data and as `speech`, for every group or one, optionally of one `person`. Needs no `person` and no permission to write. |

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
- **Repairs and diagnostics**: when writing was refused because an admin switched it off, a repair notice says where to switch it on. The diagnostics download shows the live connection, the last read, subscribed calendars and options, without any content.
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

**Stunden- und Dienstpläne:** Je Plan gibt es zusätzlich `sensor.…_school_today` (Stunden von heute mit Fach, Raum und Zeiten, was zu packen ist, morgen) und `binary_sensor.…_at_school`, bei Betreuung (verlässliche Schule oder OGS) `binary_sensor.…_in_care_after_school` und das Attribut `care`, einen eigenen Kalender mit den einzelnen Stunden, `sensor.…_work_today` (Arbeitszeit oder Schicht, die nächsten 7 Tage) und `binary_sensor.…_at_work`, außerdem `binary_sensor.<gruppe>_school_holidays`. Ein Beispiel-Dashboard mit Standardkarten steht oben unter *Timetables and rosters*.

**Einkaufslisten:** Die To-do-Entität zeigt in `shopping_state`, ob an der Liste noch geschrieben wird (`draft`), ob sie freigegeben ist (`ready`) oder jemand einkauft (`going`), dazu wer freigegeben hat, bis wann und wer einkauft. Mengen stehen im Titel, später dazugekommene Artikel tragen 🆕.

**Abhaken und eintragen:** Home Assistant liest nur, bis ein Admin in der App unter **Verwalten › Home Assistant** „Darf abhaken und eintragen“ einschaltet. Danach geht alles über die **Orgaia-Karte** (`type: custom:orgaia-card`, sie kommt mit der Integration): **erst antippen, wer man ist, dann abhaken**, Artikel auf die Einkaufsliste setzen, Liste freigeben, „Mache ich“ und „Einkauf fertig“. In der App steht der Name mit dem Zusatz „über Home Assistant“. Nach einer Minute ohne Tippen vergisst die Karte, wer es war; auf dem eigenen Handy kennt sie die angemeldete Person, wenn diese unter **Konfigurieren** zugeordnet ist. Die Karte hat mehrere **Ansichten**, die im Editor gewählt werden: alle Listen, nur Einkauf, nur Aufgaben (auch nur einer Person), **Stundenplan** als Wochenraster, **Dienstplan** und **Termine**; dazu jeweils die passende Quelle (Liste, Plan, Person). Unter **Aussehen** lassen sich Akzent-, Hintergrund- und Textfarbe, die Deckkraft des Hintergrunds sowie eigene Farben je Fach, Schicht oder Art des Eintrags einstellen. Neu sind die Ansicht **Heute** (für ein Wanddisplay, auch mit morgen), im Einkauf **Gänge**, **+ und −** bei Mengen, **„Nicht bekommen“** und **feste Einkäufe**, und in den Terminen, wer hin- und zurückfährt, mit „Ich fahre hin“.

**Standard-To-do-Listen und Kalender:** Ein angemeldeter Benutzer, dessen Person unter **Konfigurieren** zugeordnet ist, kann dort abhaken, Aufgaben und Artikel anlegen und Termine in den Orgaia-Kalendern eintragen. Sprachassistenten wissen nicht, wer spricht: Sie setzen nur Artikel auf die Einkaufsliste, und nur im Namen der Person, die unter **Konfigurieren › Einstellungen** dafür gewählt ist. Abhaken können sie nie.

**Aktionen** (jeweils mit `person`): `orgaia.set_done`, `add_article`, `add_task`, `release_shopping_list`, `take_shopping`, `finish_shopping`, `set_not_got`, `set_quantity`, `set_aisle`, `add_fixed_purchase`, `take_drive`, `drop_drive`. `orgaia.get_agenda` liefert einen Tag als Daten und als Satz zum Vorlesen (`speech`), ohne Person.

**Neue Ereignisse und Sensoren:** `drive_needed`, `drive_taken`, `rsvp_changed`, `poll_decided`; `sensor.<gruppe>_today` und je Person (Tag in Sätzen), `sensor.<gruppe>_open_drives`, je Person „Termin gerade“, „Kauft gerade ein“ und „Nächster Termin“, bei Dienstplänen „Bereitschaft“. Der Schul-Sensor kennt einzelne geänderte Tage, Arbeiten und Halbjahrespläne.

**Vorlagen (Blueprints):** überfällige Aufgabe aufs Handy mit „Erledigt“, abends ans Einpacken erinnern, Einkauf freigegeben an wer unterwegs ist, nachträglicher Artikel an den Einkäufer, „Für einen Termin fährt noch niemand“ mit „Ich fahre“, Erinnerung vor Terminen mit Fahrt. Die Import-Knöpfe stehen oben unter *Blueprints*.

**Neu verbinden:** **⋮ › Neu konfigurieren** verbindet mit einem neuen Link aus der App, ohne Entitäten und Dashboards zu verlieren. In der App kopiert **„Kopieren und in Home Assistant öffnen“** den Link und öffnet direkt „Integration hinzufügen: Orgaia“.

**Lizenz:** Apache 2.0 (siehe [LICENSE](LICENSE)). Name und Logo „Orgaia“ sowie App und Dienst sind davon nicht umfasst.
