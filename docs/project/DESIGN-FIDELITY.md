# Design Fidelity — Inventory, Checklist and Evidence

**Source of truth:** the Claude Design export
`C:\Users\imran\Documents\crm-design-export\Design system questionnaire-handoff.zip`
(SHA-256 `128683965341eeace19746a8c8e0b70987bf484f41590036b19b068c030b55d7`,
unchanged since `DESIGN-INSPECTION.md`).
- The export directory contains only this archive.
- It was extracted read-only to a scratch directory outside the
  repository.
- The original was never modified, moved or copied into the repository.
- No mock data, prototype logic or dental-specific content was taken
  over.

**Status:** started 2026-10-22. Updated per screen.

## 1. What the export contains (inspected from source, 2026-10-22)

**Files (`design-system-questionnaire/`):**
- `README.md`.
- `project/` holds 25 files:
  - `LeadStack CRM.dc.html` (503 lines): the shell and router.
  - `LeadStack Design Notes.dc.html` (283): tokens, IA and 18 open
    decisions.
  - `LeadStack Signup.dc.html` (193).
  - 18 `Screen*.dc.html` files. `ScreenTemplates` is empty (13 lines).
  - `support.js` (1911): a generated "dc-runtime" that loads React 18.3.1
    and Babel from unpkg; no app logic.
  - `mock-data.js` (264).
  - `.thumbnail` (WebP).

**Nature:** a functioning, clickable prototype. Templates are compiled in
the browser. Data is mock and in memory; many actions are simulated or
"visual only" (marked `data-visual-only`).

**Assets:**
- Geist and Geist Mono (Google Fonts).
- Lucide icon font (`lucide-static@0.460.0`).
- No images. Logos are text monograms.

**Shared foundations** (`LeadStack CRM.dc.html` L16-27, Design Notes
L243-247):
- **Accent and derived colours:** accent `#0E7C6B`, with soft (9%), line
  (30%) and ink (72% with black) mixes.
- **Neutrals:** `#161B26`, `#454D5C`, `#687082`, `#E3E6EA`, `#D4D8DE`,
  `#F4F5F7`, `#FAFAFB`, `#FFFFFF`.
- **Status pairs:** fixed background/text colour pairs.
- **Type scale:** 22/650 title, 15/600 and 14/600 headings, 13/400 body,
  12 meta, 11/600 uppercase labels.
- **Spacing:** 4 px base, 28 px gutter.
- **Radii:** 6-7 controls, 10 surfaces, 12 dialogs. Shadows only on
  floating layers.
- **Rows:** 40/34 px row heights.
- **Breakpoints, in JS only:** narrow < 760, auto-collapse < 1024,
  wide ≥ 1100.

**Screens discovered:**

| Screen (file) | Intended CRM route | Phase | Status |
| --- | --- | --- | --- |
| Shell (`LeadStack CRM.dc.html`: header, sidebar, palette, menus, toast, placeholder) | frame of `/app/w/{id}/*` | 2 (F1) | **Implemented; compared (§3)** |
| Settings › Team & roles (`ScreenSettings.dc.html` L11-27, L54-68) | `/app/w/{id}/settings` | 2 | **Implemented; compared (§4)** |
| Settings › My profile (`ScreenSettings.dc.html` L43-52) | `/app/w/{id}/settings?section=profile` | 2 | **Implemented, read-only parts; compared (§4a)** |
| Settings › other sections (business, notifications, custom fields, AI, integrations, appearance) | `/settings` (sections) | 3+ | Listed in the settings nav, marked "soon" |
| Contacts (`ScreenContacts`) | `/contacts` | 3 | List, preview drawer and create/edit dialog built on the slice 3A API (§4c); compared from source values; flows checked in Chrome at desktop width |
| Companies (`ScreenCompanies`) | `/companies` | 3 | List, drawer with the company's people, and create/edit dialog (§4c); compared from source values; flows checked in Chrome at desktop width |
| Opportunities (`ScreenPipeline`) | `/opportunities` | 4 | Placeholder (4B) |
| Settings › Sales pipeline (not in the design; P4 4A) | `/settings?section=pipeline` | 4 | **Implemented** — stage names, probabilities and order; won and lost are outcomes, not stages |
| Tasks (`ScreenTasks`) | `/tasks` | 4 | Placeholder |
| Inbox (`ScreenConversations`) | `/inbox` | 6 | Placeholder |
| Calendar (`ScreenCalendar`) | `/calendar` | 5 (outside MVP, K5) | Placeholder |
| Campaigns, Automations, Forms & pages, Reviews | `/campaigns`, `/automations`, `/forms`, `/reviews` | 7-10 (Reviews deferred, K5) | Placeholders |
| Assistants, Knowledge, AI activity (`ScreenAssistants`, `ScreenKnowledge`, `ScreenAIActivity`) | `/assistants`, `/knowledge`, `/ai-activity` | 9 | Placeholders |
| Reports (`ScreenReports`) | `/reports` | 10 | Placeholder |
| Home / Dashboard (`ScreenDashboard`) | `/home` | needs CRM data | Placeholder |
| Agency views: Workspaces, Templates (empty), Team, Billing | none yet | 11 (agency model undecided, P2-B) | Not implemented |
| Sign-in (account step of `LeadStack Signup.dc.html`, L23-50, L118-125) | `/app` and `/app/invite/{id}` when signed out | 2 (approved 2026-10-24) | **Implemented; compared (§4e)** |
| Self-service signup (the rest of `LeadStack Signup.dc.html`) | none | P2-C | Not implemented; excluded by P2-C |
| ⌘K palette (`LeadStack CRM.dc.html` L257-281), toast | frame | 2 | Toast implemented. Palette implemented with page navigation only; **compared (§4b)** |

## 2. Recorded gaps and ambiguities in the source

- **Phone layout:** none designed (Design Notes, decision 10). At 390 px
  the prototype's own header overflows: 9 elements extend past the right
  edge, measured in Chrome.
- **States:** no loading, error or confirmation states beyond "Loading
  workspace…".
- **Destructive actions:** they run immediately with only a toast.
- **Inconsistent role model:** the settings select, the permissions
  matrix and signup each use different role names. This product uses the
  approved Q6 roles: Owner, Admin, Member, Read-only.
- **Hardcoded values:** the notification dot is always on, and the user
  persona and "today" are fixed.
- **Dental and health content (not used):**
  - the "Patient" stage;
  - Invisalign and implant tags;
  - insurance and date-of-birth fields;
  - "Lead → patient" KPIs;
  - clinic copy in automations, assistants and reviews;
  - a HIPAA note.
- **Built versus placeholder:** the design notes call several modules
  placeholders, while the shell renders them as built.

## 3. Shell (frame): comparison evidence

- **Reference:** `LeadStack CRM.dc.html`, client workspace, grouped shell.
  It was served locally from the read-only extraction and switched to a
  client workspace with the prototype's own switcher.
- **Viewport:** both 1280×665 CSS px (Chrome, DPR 1.5), measured with
  `getBoundingClientRect` and `getComputedStyle` on the same elements.
- **Screenshots** (scratch, outside the repository):
  - reference: `claude-chrome-screenshots-lcgIMS/screenshot-1792663264615-1.jpg`;
  - implementation: `…/screenshot-1792663210472-0.jpg`.

| Element | Reference | Implementation | Result |
| --- | --- | --- | --- |
| Header | 52 px, white, `#E3E6EA` bottom border | 52 px, same | match |
| Brand tile | 26×26 at (12,13), r7, 12/700, accent | same | match |
| Workspace switcher | 36 px, r8, border `#E3E6EA` | 36 px, same; width depends on the name | match |
| Search trigger | 460×34, r8, `#F6F7F9`, text `#687082` | 460×34, same | match |
| "+ New" | 71×34, r7, accent, 13/500 | 71×34, same | match |
| Sidebar | 232 px, `#FAFAFB` | 232 px, same | match |
| Group header | 26 px, 11/600, `#687082` | same | match |
| Nav item | 215×32, r6, 13/500, `#3A4252` | 215×32, same | match, after fix |
| Active item | accent-soft, accent-ink, 600 | same | match |

**Material differences found and fixed:**
1. The page scrolled as a whole and narrowed every element by 15 px. Now
   it uses a fixed 100vh frame with internal scrolling, as in the
   design.
2. A visible nav scrollbar narrowed items to 200 px. It is now hidden,
   as in the design.
3. Headings used line-height 1.25 instead of the design's inherited
   1.45, giving a 25 px h1 instead of 29.
4. Default 15 px scrollbars replaced the design's 9 px ones.
5. Member IDs fell back to Consolas instead of Geist Mono; the font is
   now self-hosted.
6. The member action control lacked the select chevron.

**Remaining deviations, with reasons:**
- **Context strip** ("Working in … · client of …", 32 px): not shown,
  because no agency model exists (P2-B). This accounts for a 32 px
  vertical offset of everything below the header.
- **Avatar:** a person icon instead of initials, because no name is
  stored.
- **Inbox unread badge and notification dot:** not shown, because there
  is nothing unread; the design hardcodes the dot.
- **"soon" markers:** shown on every unbuilt module, using the design's
  own `showPreview` marker. They use `#687082` instead of `#8A91A0` for
  4.5:1 contrast, and the accent-ink colour on the active item.
- **"+ New", Help and profile menu items:** disabled and labelled "Not
  available yet" where the feature is missing. Search answers with the
  design's toast pattern. The notifications panel shows an empty state
  instead of invented notifications.
- **Workspace switcher:** shows the current workspace and "Open another
  workspace". There is no list, because no workspace directory exists
  (G1/G5).
- **Below 760 px:** search and help are hidden and the switcher is
  tightened, so nothing overflows. The design overflows at that width.
- **Not built:** the ⌘K palette and the rail shell (the design's
  alternative).

## 4. Settings › Team & roles: comparison evidence

- **Reference:** `ScreenSettings.dc.html`, section `team`, in the client
  workspace.
- **Viewport:** 1280 px wide.
- **Measured in the implementation, matching the reference exactly:**
  - settings nav 236 px wide, white;
  - "Settings" 18/650 at x=242;
  - active "Team & roles" item 215×32, accent-soft;
  - h1 20/650, 739 px wide at (500, top);
  - Invite button 78×30 at x=1145;
  - member row 738×57.

**Remaining deviations, with reasons:**
- **Member rows:** show the membership ID (Geist Mono) and status instead
  of name and email, because member profiles wait on G1.
- **Role control:** the design's per-row role `<select>` is a "select"
  button opening the actions menu. Roles are added and removed
  individually, Owner changes need confirmation, and Admins may not touch
  Owners (G-LOCK).
- **Scope pills:** show the member's roles (Owner, Admin, Member,
  Read-only) instead of Agency or Client staff.
- **Role permissions:** shows this product's approved matrix (Q6) with
  the design's check, eye and minus marks. Minus uses `#8A91A0` instead
  of `#C2C8D1` for 3:1 non-text contrast.
- **Other settings sections:** listed and marked "soon".
- **Invite:** answers that invitations are not available yet (G1/G4).

## 4a. Settings › My profile: assessment and comparison evidence

**What the source specifies** (`ScreenSettings.dc.html` L43-52):
- a card with a 52 px avatar, the name (15/600) and a role line;
- two editable inputs, Display name and Time zone. The design has no save
  action;
- an identity-provider card, "Email, password & two-factor", with a
  visual-only "Manage ↗" button.

**What the system supports:**
- **Role line:** available through `/v1/workspaces/{id}/access` and the
  workspace name.
- **Name and e-mail:** not available. SaaS-OS stores no name, and
  `/auth/me` returns only the user ID.
- **Storing a display name or time zone:** blocked. It would need a
  product table holding personal data, which waits on G1 together with
  member profiles (`PHASE2-PLAN.md` §6.5). No storage was added.
- **"Manage":** has no target that keeps the identity provider invisible
  (Login V2 has no self-service page; the ZITADEL console would expose
  the provider, against SaaS-OS ADR-0023).

**Implemented:**
- the design's layout with the real role line;
- disabled fields with an explicit note that they cannot be saved yet;
- the browser's detected time zone shown read-only;
- "Manage" disabled.
- No backend change, endpoint or storage.

**Comparison** (1280 px; reference values offset by the 32 px context
strip):

| Element | Reference | Implementation |
| --- | --- | --- |
| h1 | 748×29, 20/650 | same |
| Card | 748 px, r10, padding 18/20 | same |
| Avatar | 52×52 at x 521, `#3D5A80` | same |
| Name | x 587, 15/600 | same |
| Inputs | 346×34 at x 521 and 881, r7 | same |
| Labels | 12.5/500 | same |
| Identity card | 707×62, `#F6F7F9`, r8 | same |
| Manage | 88×30, 13/500, x 1125 | same, after one fix (it first reused the 12.5/400 select style) |

- **Screenshot:** `claude-chrome-screenshots-lcgIMS/screenshot-1792665726967-2.jpg`.
- **Deviations, with reasons:**
  - the card is 51 px taller because of the honesty note;
  - the inputs have a disabled background because they cannot save;
  - the avatar shows an icon and the name line says "Signed in", because
    no name is stored.
  - In the settings nav, "Appearance & white-label" is truncated because
    of its "soon" marker.
- **Checks:**
  - Lighthouse (desktop 1280×800, a test session in `crm_app_test`):
    Accessibility 100, 35 passed, 0 failed, colour contrast included;
    the console was empty;
  - at a 390×844 emulated phone viewport, no element overflows;
  - a jsdom axe scan and the tests pass.
- **Defect found in review and fixed:** the role line showed the
  alphabetically first role, so a member with Admin and Owner read
  "Admin". It now shows the most senior role (`highestRole`); the profile
  menu had the same flaw and is fixed too. A unit test covers it.

## 4b. ⌘K palette: implementation and checks

**What the source specifies:**
- an overlay at 28% opacity and a 600 px panel (r12) with a 52 px input
  and a 15 px "Search {scope}, or jump to a page…" placeholder;
- result groups Contacts, Opportunities, Workspaces and Go to (38 px
  rows);
- "No matches for …";
- a footer reading "↵ open · ⌘K toggle · Scoped to {workspace}".

**Implemented:**
- the same panel, input, row and footer styling;
- **"Go to" only:** the modules (placeholders say "Not available yet")
  and the Settings sections;
- typing filters the pages; arrow keys and Enter navigate;
- ⌘/Ctrl+K toggles; Escape closes and returns focus to the trigger.

**Deliberate deviations:**
- The placeholder and the header trigger say "Jump to a page…", not
  "Search contacts, deals, pages…", because no record search exists.
- A one-line note says that searching contacts, deals and other records
  is not available yet.
- The Contacts, Opportunities and Workspaces groups are absent; nothing
  is invented.
- The empty state reads "No pages match …".

**Checks:**
- Real Chrome (DevTools, a test session in `crm_app_test`), real keys:
  - ⌘/Ctrl+K opens with focus in the input;
  - typing "task" leaves only "Tasks (Not available yet)", and Enter
    opens its placeholder;
  - Escape closes and focus returns to the trigger;
  - no console messages.
- Lighthouse with the palette open: Accessibility 100, 34 passed,
  0 failed.
- Vitest covers navigation, the empty state, Ctrl+K, Escape and an axe
  scan.

**Comparison (2026-10-22):**
- **Reference:** the prototype's palette in a client workspace, served
  locally from the read-only extraction.
- **Viewport:** both 1280×609 CSS px in Chrome (DPR 1.5).
- **Method:** `getBoundingClientRect` and `getComputedStyle` on the same
  elements in both pages.
- **Screenshots** (scratch, outside the repository): reference
  `claude-chrome-screenshots-lcgIMS/screenshot-1792667943105-3.jpg`;
  implementation `…/screenshot-1792668019092-4.jpg`.

| Element | Reference | Implementation |
| --- | --- | --- |
| Backdrop | full viewport, `rgba(22,27,38,0.28)`, 90 px top padding; click closes | same |
| Panel | 600×507 at (340, 90), white, r12, shadow `0 24px 60px rgba(22,27,38,0.28)` | same, after a fix (below) |
| Input row | 600×52, padding 0 16 | same |
| Input | 500×24 at (383, 104), 15 px, line-height 21.75, ink | same, after a fix (below) |
| esc hint | 31×19 at (893, 106), mono 11 px, border `#E3E6EA`, r4, padding 1/5 | same |
| Group header | 11/600, padding 10/10/4, 30 px, `#687082` | same |
| Rows | 579×38, r7, padding 0 10; label 13/500; sub 12 px `#687082`; ↵ icon | same |
| Results area | max 420 px, padding 6 | 386 px, so the note row fits the same total height |
| Footer | 600×35, 11.5 px, padding 9/16, `#FAFAFB`, top border `#EEF0F3` | same |
| Empty state | 588×75, padding 28, centred, `#687082` | same block, with different text (below) |

**Material differences found and fixed:**
1. **Input text colour:** typed text was pure black instead of the
   design's ink `#161B26`.
2. **Panel height:** the panel was 541 px instead of 507, because of the
   honesty note. At this viewport its bottom (631 px) passed the window's
   609 px; it ended at 597 px in the design. The results area now caps at
   386 px, which brings the total back to 507 px.
3. **Placeholder colour:** set to `#687082` (4.5:1) instead of the
   design's `#8A91A0`; recorded as an accessibility deviation.

**Remaining deviations, with reasons:**
- **Wording:** "Jump to a page…" instead of "Search contacts, deals,
  pages, or jump to a page…", and "No pages match …" instead of "No
  matches for …". No record search exists.
- **Note row:** a 34 px row stating that record search is not available.
  As a result, the empty-state panel is 208 px instead of 174.
- **Missing groups:** no Contacts or Opportunities groups and no recent
  records; the Go to group lists every page instead of three before
  scrolling.
- **Pixels:** no pixel-level overlay was made (no image library);
  geometry and computed styles match as listed.
- **Not checked:** Firefox, Safari, a real screen reader, and the palette
  at phone width against the design (the design defines no phone
  layout).

## 4c. Contacts and Companies (slice 3A.4, 2026-10-24)

Built from `ScreenContacts.dc.html` (list L12-97, drawer L194-222, dialog
L224-247) and `ScreenCompanies.dc.html`, read from the export zip without
extracting it. Values below were taken from the source; they have **not**
been measured in a browser yet (§6).

**Matched from source values:** page padding `20px 28px 40px`, gap 14 and
max width 1480 / 1320 px; eyebrow 12 px; title 22 px / 650 / -0.015em with
a 16 px count; 32 px secondary and primary buttons; 280 px search box;
dashed filter buttons that turn solid accent when active, with 16 px
checkbox menus; view tabs 36 px with a 2 px accent underline; table card
radius 10; 36 px uppercase 11.5 px header on `#FAFAFB`; 48 px rows with
`#F1F2F4` dividers, `#F7F8FA` hover and accent-soft selection; 30 px
avatars in the design's six colour pairs (square `#F1F2F4` for companies);
stage pills with the design's colours; 22 px owner dots; 440 px drawer
with an 18 % scrim, a `100px 1fr` field list and 46 px avatar; dialogs of
560 px (contact) and 500 px (company) with a two-column 14 px grid, 34 px
inputs, accent focus ring, `#D6453D` invalid border and 12 px `#A3302A`
messages; the design's validation texts.

**Deliberate differences:**
- *Data model (P2-E, P3-A):* the dental "Patient" stage is "Customer"
  (same colours); sources are the P3-A list (Manual, Referral, Other for
  people; Import and Form shown only when the system set them); no
  score, so its column and card are left out. Notes and activity arrived
  in slice 3B (§4d).
- *Custom fields (slice 3D, decision P3-D):* the design's "Custom fields"
  card with "Manage" (label and value rows) in both drawers, shown when
  the record type has active fields; "Manage" opens Settings › Custom
  fields and is shown to Owners and Admins only. Settings › Custom fields
  covers companies as well as contacts (the design names contacts only).
  *Addition:* the record dialogs show one typed input per active field
  after the core fields.
- *Tags (slice 3C, decision P3-C):* the design's neutral pills
  (`#F1F2F4` on `#2A303C`, 11.5 px) in a Tags column (first three and
  "+N", hidden on narrow screens) and in the drawer's Tags section; the
  design's Tag filter on both lists. Tags have no colour, as in the
  design. *Improvement:* instead of the design's inline "+ Add tag" field,
  "Edit tags" opens a dialog that saves the whole set with the record's
  version (no race between quick changes); Owners and Admins can create a
  tag there. *Addition:* Settings › Tags lists, renames and deletes tags
  (the design notes' "Central Settings" option); the design has no such
  section.
- *Views:* "Assigned to me" instead of a named person; "Hot (80+)",
  "Recall due" and "+ Save view" are left out (no score, no recall, no
  saved views); an "Archived" view is added so archived contacts can be
  restored. Companies get an Active/Archived switch instead of industry
  chips (industry is free text and the API has no industry filter).
- *Import (slice 3F, decision P3-F):* the design's Import button opens a
  dialog (the design has no import screen): choose a CSV file, review the
  column mapping, the counts and the refused rows, then import and follow
  the progress. Members and Read-only users see Import disabled, named
  "Import (Only Owners and Admins can import)". Companies gain the same
  Import button. *Not built, shown honestly:* quick actions (Message, Call, Book, Deal), the
  bulk bar, the columns picker, opportunities, pipeline and "Won" are left
  out, and the drawer says what is not available.
- *Export (slices 3E1 and 3E2, decisions P3-E1 and P3-E2):* Export works on
  both Contacts and Companies and downloads a CSV of the current search,
  filters, view and order. It sits in the header actions as the design's
  secondary button. Members and Read-only users see it disabled, named
  "Export (Only Owners and Admins can export …)"; while it runs it reads
  "Exporting…" with a spinner, and a refusal shows an inline error message
  under the header. The bulk bar's "Export" stays out (no bulk bar).
- *Paging:* "Load more" by cursor instead of page numbers (the API pages
  by keyset cursor); the count reads "N of M" up to 10,000, then "10,000+".
- *Columns:* contacts show Name (with email or phone), Stage, Owner,
  Company, Source and Updated; companies show Company (with domain),
  Industry, Owner, City and Updated. Sorting is by name or last update,
  the API's allow-list.
- *Owners* show as "You" or "Member <id>", because member names are not
  stored yet (PHASE2-PLAN.md §6.5).
- *Full record page:* not built; the drawer holds every stored field and
  the edit, archive, restore and delete actions. The companies drawer
  lists the company's people; choosing one opens it in Contacts.
- *Archive, restore and permanent delete* are added (the design has none);
  delete asks for confirmation and is shown only to roles that may delete.
- *Contrast:* the count, placeholders and unchecked checkbox border use
  darker greys than the design so they meet WCAG contrast.

**Tests:** `frontend/src/records/records.test.tsx` (jsdom): listing,
read-only permissions, search/stage/view filters reaching the API,
create with validation and an idempotency key, duplicate refusal with
"Open existing", edit sending only changed fields with `If-Match`, the
stale-version message, delete only after confirmation, cursor paging,
the companies list, the people list opening a contact, and the company
dialog; axe scans of both lists report no violations (contrast is not
measurable in jsdom).

## 4d. Notes and activity in the drawers (slice 3B.4, 2026-10-24)

**Source:** `ScreenContacts.dc.html` L181-187 (note composer and cards) and
L155-164, L218-219 (timeline). Decision P3-B D1 puts both in the existing
drawers; the design shows them on the full record page, which is deferred.

**Matches:** the composer (placeholder "Write a note… visible to your team
only", `#FFFDF5` text area, `#FAFAFB` bar with a primary "Add note"), the
note card (`#FFFBEB` with a `#F0E6C4` border, 8 px radius, text with its
line breaks, author and time in `#7A6A3A` at 12 px), and the timeline row
(24 px tinted icon square, text, then meta in `#687082`; notes in the
note tint).

**Deliberate differences:**
- Placement in the drawers, newest first, five at a time with "Show
  more"; no Overview/Activity/Notes tabs and no activity filter chips
  (only record and note events exist).
- Edit and Delete on each note for its author and for Owners and Admins
  (D3), which the design does not show; delete asks for confirmation;
  "Edited" marks a changed note. Closing a drawer with an unsaved new note
  or a changed edit asks "Discard note?". Edit moves focus into the text;
  Cancel and Save return it to the Edit button.
- History is worded from field names, stages, owners and companies only
  (D5): "Updated email and city", "Stage changed from Lead to Customer";
  never field values. People appear as "You" or "Member xxxxxxxx" until
  member names exist.
- Archived records show their notes with "Restore this contact to add or
  edit notes." instead of the composer (D8).

**Tests:** `frontend/src/records/notes.test.tsx` (jsdom): markup in a note
shown as text (no element created), history wording, adding with an
idempotency key, editing with `If-Match` and only on one's own note,
the stale-version message, delete after confirmation, the read-only and
archived views, and the discard prompt; an axe scan of the drawer reports
no violations.

## 4e. Branded sign-in (2026-10-24)

**Scope (owner approval, 2026-10-24):** a LeadStack-branded sign-in screen
from the sign-in parts of `LeadStack Signup.dc.html`, before slice 3C.
Decision P2-C is unchanged: there is no self-service signup and no public
workspace creation.

**Implemented** (`frontend/src/pages/SignInScreen.tsx`, styles under
"Sign-in" in `styles.css`):
- Shown on `/app` and on invitation links whenever no session is known
  (while the session is checked, when it is absent, and when the check
  fails). The application header is shown only to a signed-in person.
- The one action is a **Sign in** link to the existing `/auth/login`
  (SaaS-OS OIDC: PKCE, state, nonce). Credentials are entered only on
  ZITADEL's Login V2 pages; the screen has no form or input (SaaS-OS
  ADR-0026 was rejected).
- States: "Checking your session…"; a failed session check with
  **Try again** and sign-in still offered; after a click the link shows a
  spinner, announces "Opening the sign-in page…" and ignores further
  clicks; returning with the browser's Back button (back/forward cache)
  makes it usable again. Modified clicks (new tab) are left alone.
- An invitation link without its token shows "This invitation link is
  incomplete" on the same screen.

**Compared with the source (values from the file):**

| Element | Design | Implemented |
| --- | --- | --- |
| Layout | `flex-wrap` row: aside `flex: 0 1 340px`, min 280; main `flex: 1 1 520px`, padding 48/24 | Same widths and padding; below 760 px a column with the aside as a 58 px brand bar (the design only wraps) |
| Aside | `#161B26`, white, padding 32/28, gap 28 | Same (`--ink`) |
| Brand | 30 px tile, radius 8, accent, 700 13 px "LS"; name 650 15 px | Same |
| Aside foot note | 12 px `#A9B0BE` | Same colour and size; text replaced (below) |
| Text | Geist 13.5/1.5, `#161B26` | Same |
| Kicker | Geist Mono 12 px `#687082` ("Step 1 of 7") | Same face and size, `--muted` `#5F6778` for contrast; text "LeadStack CRM" |
| Title | 26 px, 650, -0.02em, margin 4/0/6 | Same; 23 px below 760 px |
| Subtitle | `#454D5C` | Same |
| Primary action | 40 px, radius 8, accent, white 600, arrow-right icon | 42 px (the design's height for the account step's main buttons), full width, same colours and icon |
| Helper text | 12 px `#687082`, "Password and two-factor are handled by our identity provider." | 12 px `--muted`, same meaning |
| Footer line | 12.5 px `#687082`, centred, above a `#E3E6EA` rule | Same |
| Content width | max 560 px, top-aligned | max 420 px, centred vertically (one action instead of a form) |

**Left out on purpose:** the step rail, "Continue with Google/Microsoft"
(no such provider integration exists or is approved; D-IDL.1 turned
external providers off), the name and work-email fields, "Create your
LeadStack account", "Free for 14 days", "Already have an account?", and
the prototype disclaimer. They belong to self-service signup (P2-C). In
their place the aside says accounts are created by invitation and there
is no public sign-up, and the footer tells a visitor without an account
to ask an Owner or Admin for an invitation. The aside's one-line product
description is new copy, not from the design.

**Checks (2026-10-24; commit `04a4bb6`, CI run 40097066377 green):**
- Vitest (`HomePage.test.tsx`, `InvitePage.test.tsx`): branded screen,
  link target, no header or sign-out while signed out, no input, form,
  sign-up, Google or Microsoft text and only the skip link besides
  **Sign in**, the redirecting state and second-click guard, the
  back/forward-cache reset, the session-check loading and failure states
  with retry, sign-out from the start page (`POST /auth/logout`, then
  `GET /v1/sign-out-url`, then the sign-in screen); axe without
  violations on the screen and its error state.
- Chrome at 1280×609 (desktop window): layout as in the table, the Tab
  order skip link → **Sign in** with the 2 px focus outline, no
  horizontal scroll, no console errors; **Sign in** showed the
  redirecting state and reached ZITADEL Login V2 on `localhost:8000`;
  Back returned to a usable screen.
- Phone, 390×844 emulated in Chrome (DevTools): column layout, brand
  bar 58 px, action 358 px wide, page width 390 (no horizontal scroll).

## 5. Accessibility and quality evidence (2026-10-22)

- **Lighthouse** (Chrome DevTools, desktop 1280×800, snapshot mode):
  - Settings › Team & roles: Accessibility 100, 36 passed, 0 failed;
  - the Contacts placeholder: Accessibility 100, 33 passed, 0 failed;
  - both include colour contrast. Earlier runs found label-in-name
    mismatches and a contrast failure on the active item's "soon"
    marker; both were fixed before these results.
- **Keyboard:** the Tab order runs skip link → brand → workspace →
  search → New → notifications → help → account → navigation, with a
  2 px focus outline on every stop.
  - The phone overlay traps focus, closes on Escape and returns focus to
    "Open navigation".
  - Dialogs and menus come from React Aria (focus trap and restore).
- **Phone (390×844 emulated):** no element overflows the viewport, the
  overlay sidebar works, and settings stack vertically.
- **Admin view** (a test Admin session): no actions on the Owner or on
  the Admin's own row; the Member's menu omits "Add role: Owner".
- **Console and CSP:** a real violation was found. React Aria injects one
  fixed stylesheet (a `touch-action` rule). It is now admitted by its
  SHA-256 hash only (`style-src 'self' 'sha256-…'`); `'unsafe-inline'`
  is still not allowed, and a unit test pins the hash to the exact rule
  text. A `/favicon.ico` 404 was removed with an inline empty icon.
  Afterwards the console showed no messages.
- **`HEAD /app`:** answers 200 with no body (integration test).

## 6. Not yet verified

- Pixel-difference overlays: no image library is installed, so geometry
  was compared numerically instead.
- The Contacts and Companies screens at phone width in a real browser,
  and their geometry measured against the design export. They were
  exercised in Chrome at desktop width after a ZITADEL sign-in on
  2026-10-24 (`PROGRESS.md`).
- Screen reader output (only the accessibility tree was checked).
- The design reference at 390 px beyond the overflow measurement.
- Firefox and Safari.
- Sign-in: a real phone (only emulation), a screen reader, and the
  provider's error pages (a failed or cancelled sign-in ends on
  SaaS-OS's plain JSON answer at `/auth/callback`; see `PROGRESS.md`).
