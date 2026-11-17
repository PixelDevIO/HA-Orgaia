# Orgaia for Home Assistant

Your family's **Orgaia** group in Home Assistant: every task and shopping list as a **to-do list**, appointments and planned tasks in a **calendar**, and **sensors** for what is open, due today or overdue. Updates arrive live.

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
| `calendar.<group>_calendar` | Appointments and tasks with a time slot, including repetitions and their exceptions. |
| `sensor.<group>_open_tasks` | Open tasks, including today's repeating ones. Attribute `titles`. |
| `sensor.<group>_due_today` | Tasks due today. |
| `sensor.<group>_overdue` | Tasks past their due date, and today's repeating tasks past their time. |
| `sensor.<group>_shopping_list` | Items still to buy. |
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

### Timetables and rosters

They show as in the app, worked out on your Home Assistant:

- A **timetable** is a to-do list with today's packing tasks ("Pack sports kit"), due at the packing time. They count in the sensors, appear in the person's to-do list and fire `task_overdue` when not ticked off in time. The school day is in the person's calendar, holidays left out.
- A **roster** puts working time into the person's calendar: the fixed week with its days off, or the shifts entered day by day (with the shift's name unless the roster shows "busy" only). It has no to-do list.

Titles follow Home Assistant's language (German or English).

### People in Home Assistant

Under **Settings → Devices & services → Orgaia → Configure**, choose which Home Assistant person (`person.*`) each person of the group is. People with the same name are suggested. Events and person sensors then carry the person entity too (`assignee_entities`, `completed_by_entity`, `person_entity`), so a notification can go to the right phone.

## Automations

Every change that matters fires the event `orgaia_event`. The same events are offered as **device triggers** on the group's device (Automation → Add trigger → Device → your group).

| `type` | When |
|---|---|
| `task_created` | A task or shopping item was added. |
| `task_assigned` | Somebody was assigned to an open task (`assigned`, `assigned_entities`). |
| `task_completed` | A task was ticked off (`completed_by`, `completed_by_entity`). |
| `task_reopened` | A ticked task was opened again. |
| `task_overdue` | A task passed its due date or time. |
| `event_created` | An appointment was added. |
| `event_changed` | Time, place, title, repetition or participants of an appointment changed. |
| `event_starting` | An appointment begins. For a reminder ahead of time, use the calendar trigger with an offset. |

Every event carries `group`, `device_id`, `item_id`, `title`, `list`, `assignees` (names) and `assignee_entities`; tasks also `list_type`, `due` and `date` (the occurrence of a repeating task), appointments `start`, `end`, `all_day` and `location`.

Nothing fires for what was already there when Home Assistant started, and every change fires once.

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

This version **reads only**. Changes are made in the Orgaia app; ticking off from Home Assistant comes in a later version.

## Good to know

- **Service not reachable**: everything stays on screen as last read, and `sensor.<group>_connection` says `offline` (with `last_sync`). Home Assistant also starts without a connection. Changes arrive as soon as the service is back.
- **Time zone**: Orgaia stores times as wall-clock times. Home Assistant reads them in its own time zone, so it should be the one your family lives in.
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

Home Assistant zählt nicht als Person; pro Gruppe gehen bis zu 3 Integrationen. Für jede Person der Gruppe gibt es eine eigene To-do-Liste, einen Kalender und Sensoren; unter **Konfigurieren** ordnest du ihr eine Person in Home Assistant zu. Für Automationen gibt es das Ereignis `orgaia_event` (auch als Geräte-Auslöser), zum Beispiel wenn eine Aufgabe erledigt oder überfällig ist oder ein Termin beginnt. Stundenpläne erscheinen als To-do-Liste mit den Pack-Aufgaben von heute, Schulzeit und Arbeitszeit aus Dienstplänen stehen im Kalender der Person. Ist der Orgaia-Dienst nicht erreichbar, bleibt der letzte Stand sichtbar und der Sensor „Verbindung“ zeigt `offline`. Diese Version liest nur, abhaken aus Home Assistant kommt später. Home Assistant sollte auf die Zeitzone eingestellt sein, in der ihr lebt.

**Lizenz:** Apache 2.0 (siehe [LICENSE](LICENSE)). Name und Logo „Orgaia“ sowie App und Dienst sind davon nicht umfasst.
