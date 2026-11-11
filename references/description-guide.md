# Writing descriptions.json

**Language rule.** Write every value in the language given by `descriptions.json["_lang"]` (`en` English, `ja` Japanese, `zh` Simplified Chinese, `es` Spanish, `ko` Korean; a file with no `_lang` is Japanese).
These stay exactly as specified, in every language:
- the JSON keys;
- the `evidence` ids (`init`, `c02`, `s02` …) and screen ids (`pXXX`);
- the three `confidence` values: `Verified`, `Inferred`, `To confirm` (the book translates the label).

Quote UI labels of the target app exactly as they appear on screen. Never translate them.
The examples below are in English; write the same kind of content in the document language.

Fill in the `descriptions.json` that `app-spec-crawler describe DIR --lang <code>` generates.
It becomes the body of the spec. The reader is a developer, or a person taking over the system, who has never used the app.

## Principles
- **Look at the screenshot before you write.** Text from `pages.json` alone loses layout, emphasis, empty states, badges and the like.
- **Separate fact from inference.** State what you saw as fact. Mark guesses about behavior as inferred ("probably", "appears to"). Put what you cannot confirm into `open_questions`. The behavior of a button that was not pressed is always an inference.
- **Say why it exists and when it is used, not only what is there.** The auto-extracted data already lists the buttons. The description adds the business context.
- **Be specific.** Not "a list screen" but "a list for finding customers by company name, contact and status, leading to the detail screen; 20 rows per page, probably sorted by creation date, newest first".
- Write in the document language. When the app's UI is in another language, quote the labels as they are and write the explanation in the document language.
- For a screen's `name`, prefer the heading or menu label in the UI; if there is none, name it from the URL. Keep `category` consistent with the side menu or the first URL segment (it groups the table of contents).
- Do not copy personal data visible in the screenshots (names, email addresses, employee numbers) into the text.

## Spec items (`specs`) at three levels — the core of the book
Write a spec as **one item per line**, not as a paragraph of explanation. In the book the items become a numbered table, each linked to the capture that supports it.

```json
{"type": "Action", "statement": "Pressing \"Filter\" opens a dropdown for entering conditions", "condition": "Always", "evidence": "c02", "confidence": "Verified", "notes": ""}
{"type": "Permission", "statement": "The \"Add New\" button is shown only to the administrator role", "condition": "Role = administrator", "evidence": "init", "confidence": "Inferred", "notes": "Screens for ordinary users were not captured"}
```
| Field | Content |
|---|---|
| type | Display / Action / Input / Navigation / Permission / Visibility / Business rule / List & search / Non-functional, etc. (use the equivalents in the document language). Keep the vocabulary consistent |
| statement | In the form "doing X shows Y" or "X is Y". One sentence, one spec. Do not drop the subject |
| condition | When it holds (when, for whom, in which state). If unconditional, "Always" |
| evidence | The capture that supports it: `init` for the initial view, `c02` etc. for an interaction state. Empty if it was not pressed or not visible |
| confidence | Exactly one of `Verified` (seen in a capture) / `Inferred` (guessed from context) / `To confirm` (hard even to guess) |
| id | Optional. If omitted, numbered automatically, like `SPEC-p003-01`. If you assign one by hand, keep it unique across the whole file |

**Which level**: a spec for that screen alone goes in `pages[pXXX].specs`. A spec shared by several screens in the same section (e.g. every screen under a customer has a breadcrumb;
a URL with an ID returns 404 for a customer that does not exist) goes in `sections[path].common_specs`. App-wide matters (authentication, the common header, language, the permission model) go in `app.specs`.
When you lift a spec from a lower level to a higher one, remove it from the lower one (do not duplicate).

## sections
The template has one key per URL directory (`/`, `/customers`, `/customers/{id}` …). `_children` and `_pages` are for reference (child sections and the screens directly under the section).
| Key | What to write |
|---|---|
| name | Section name. Match the label in the side menu (e.g. Customer management). If empty, the index screen's name or the last path segment is used |
| summary | What this group of screens is (1–2 sentences) |
| purpose | Its role in the business |
| contains | The screens included and how they divide the work (say how to read the section: list → detail → tabs in the detail → list of child resources …) |
| common_specs | Spec items shared across the section |
| navigation | Navigation patterns within the section (list → detail, detail → edit modal, the way back) |
| access | Permissions and display conditions (who can see this section at all) |
| open_questions | What is unclear |

For deep sections (`/a/{id}/b/{id}/c`), write at each level what that section represents relative to its parent (a customer's orders, an order's line items …) and make the parent-child relation explicit.

## app
| Key | What to write |
|---|---|
| name | The app's name (from the header logo or title) |
| overview | What the system is, its main business areas, how the screens are organized overall (3–8 sentences). The first sentence is shown on the cover, so make it stand alone |
| target_users | Kinds of users (administrator, ordinary user, customer, etc.) and the permission differences you can read from the screens |
| auth_and_roles | How login works, role switching, what is shown or hidden by permission |
| global_navigation | The structure of the header and side menu, and the screen ID each menu item corresponds to |
| common_ui | Shared components (search bar, pagination, notifications, help, language switch, etc.) and shared behavior |
| specs | App-wide spec items |
| business_domain | The business handled, the main entities and their relations (customer 1—N orders …) |
| non_functional | Non-functional aspects you could observe (responsive layout, multiple languages, browsers, loading indicators, etc.) |
| open_questions / notes | Unknowns and remarks that concern the whole app |

## pages.pXXX (each screen)
| Key | What to write | Example |
|---|---|---|
| name | Screen name | Customer list |
| category | Feature category | Customer management |
| summary | 1–2 sentences | A list for searching and filtering registered customers and moving to the detail screen. |
| purpose | Business purpose and where it sits | The starting point for a sales rep looking for their customers. Reached from the "Customers" menu on the dashboard. |
| display_conditions | When it is shown and when it is not | Shown to every logged-in role. With 0 customers, an empty state "No customers" (verified in c03). The "Add New" button is probably for administrators only (not shown in the ordinary user's screenshot). |
| users_and_usage | Intended users and how they use it | Sales reps check their customers daily. Administrators probably use it to change statuses in bulk. |
| specs | **This screen's spec items (the core)** | See "Spec items at three levels" above |
| features | Main features | ["Keyword search by company name and contact", "Filter by status (active / dormant / cancelled)", "Sort by creation date and update date", "CSV export (not verified)"] |
| ui_elements | Behavior per element | {"element":"Status tabs","behavior":"Clicking filters the list (verified in c02)","notes":"With a count badge"} |
| inputs | Input fields | {"field":"Keyword","type":"text","required":"Optional","validation_assumption":"Partial match; no filter when empty","notes":"placeholder \"Company or contact name\""} |
| flows | Usage flow | ["Click \"Customers\" in the menu", "Enter a keyword and search", "Click a row to open the detail"] |
| transitions | Navigation | {"trigger":"Company name link in a row","to":"p007 Customer detail","notes":"/customers/{id}"} |
| states_and_variants | Variations | Empty state, loading, error display, permission differences, differences in responsive layout |
| business_rules | Inferred rules | A customer with the status "Cancelled" probably cannot be edited (the edit button is greyed out). |
| open_questions | What is unclear | ["Which fields the CSV export outputs", "Whether the page size can be changed"] |
| states.cNN | Interaction state | {"description":"Dropdown of filter conditions. Can filter by status, person in charge and period","when_shown":"When the \"Filter\" button is pressed","notes":"The Apply button was not pressed"} |

Each `cNN` under `states` must match `states[].id` in `pages.json`. For a state whose `result` is "no change", still leave one line,
such as "Clicking produced no change (probably disabled, or insufficient permission)". `_label` `_result` `_url` `_title` are for reference and do not appear in the book.

## Quality check (verify yourself after filling in)
- [ ] Every screen has at least one item in `specs`; every section has `summary` and `contains`
- [ ] Every page has `summary` and `display_conditions`
- [ ] Every interaction state `cNN` has a `description`
- [ ] No behavior of an unpressed button is stated as fact
- [ ] Navigation targets are referenced by screen ID (pXXX)
- [ ] Unknowns are not filled in by guessing (they are left in `open_questions`)
- [ ] The same category is always spelled the same way (no mix of "Customer management" and "Customers")
- [ ] `confidence` is always exactly `Verified`, `Inferred` or `To confirm`
- [ ] Every value is in the language of `_lang`; UI labels are quoted as on screen
- [ ] No personal data from the screenshots (names, email addresses) is copied into the text

## Splitting the work for many pages
Above 50 screens, split the work across subagents by category. Give each agent
(1) the list of page IDs it owns, (2) the matching part of `pages.json`, (3) the screenshot paths, (4) this guide, and the document language (`_lang`),
and have it return only the `pages` object for its share; the parent merges. The parent writes `app` after looking at the whole.
