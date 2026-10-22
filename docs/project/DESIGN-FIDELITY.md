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
| Settings › other sections (profile, business, notifications, custom fields, AI, integrations, appearance) | `/settings` (sections) | 3+ | Listed in the settings nav, marked "soon" |
| Contacts (`ScreenContacts`) | `/contacts` | 3 | Design spec in `PHASE3-PLAN.md` §13; placeholder page (G1) |
| Companies (`ScreenCompanies`) | `/companies` | 3 | Same as Contacts |
| Opportunities (`ScreenPipeline`) | `/opportunities` | 4 | Placeholder |
| Tasks (`ScreenTasks`) | `/tasks` | 4 | Placeholder |
| Inbox (`ScreenConversations`) | `/inbox` | 6 | Placeholder |
| Calendar (`ScreenCalendar`) | `/calendar` | 5 (outside MVP, K5) | Placeholder |
| Campaigns, Automations, Forms & pages, Reviews | `/campaigns`, `/automations`, `/forms`, `/reviews` | 7-10 (Reviews deferred, K5) | Placeholders |
| Assistants, Knowledge, AI activity (`ScreenAssistants`, `ScreenKnowledge`, `ScreenAIActivity`) | `/assistants`, `/knowledge`, `/ai-activity` | 9 | Placeholders |
| Reports (`ScreenReports`) | `/reports` | 10 | Placeholder |
| Home / Dashboard (`ScreenDashboard`) | `/home` | needs CRM data | Placeholder |
| Agency views: Workspaces, Templates (empty), Team, Billing | none yet | 11 (agency model undecided, P2-B) | Not implemented |
| Signup (`LeadStack Signup.dc.html`) | none yet | P2-C | Not implemented |
| ⌘K palette, toast | frame | 2 | Toast implemented; palette not built (search is not available) |

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
- The Contacts and Companies screens; they wait on G1.
- Screen reader output (only the accessibility tree was checked).
- The design reference at 390 px beyond the overflow measurement.
- Firefox and Safari.
