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
| `sensor.<group>_overdue` | Tasks past their due date. |
| `sensor.<group>_shopping_list` | Items still to buy. |
| `sensor.<group>_next_appointment` | Start of the next appointment, with title and location. |
| `sensor.<group>_connection` | Diagnostic: `ok`, `offline`, `needs_plus`, `update_required` or `removed`. |

New lists appear by themselves; deleted lists disappear.

This version **reads only**. Changes are made in the Orgaia app; ticking off from Home Assistant comes in a later version.

## Good to know

- **Time zone**: Orgaia stores times as wall-clock times. Home Assistant reads them in its own time zone, so it should be the one your family lives in.
- **Plus ended**: Home Assistant stops reading and shows a repair notice. Once Plus is renewed it picks up again by itself.
- **Removed from the group**: Home Assistant shows a notice under Settings → Devices & services that asks for a new link from the app.
- **Removing the integration** leaves the group, so the admins see Home Assistant is gone.
- **Privacy**: titles and names are decrypted on your Home Assistant and may end up in its history and logbook. Private lists in Orgaia never reach Home Assistant. Diagnostics hold only counts, no content and no keys.

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

Home Assistant zählt nicht als Person; pro Gruppe gehen bis zu 3 Integrationen. Diese Version liest nur, abhaken aus Home Assistant kommt später. Home Assistant sollte auf die Zeitzone eingestellt sein, in der ihr lebt.

**Lizenz:** Apache 2.0 (siehe [LICENSE](LICENSE)). Name und Logo „Orgaia“ sowie App und Dienst sind davon nicht umfasst.
