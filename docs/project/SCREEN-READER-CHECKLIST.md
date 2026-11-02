# Screen-reader test checklist (NVDA and VoiceOver)

For a person testing LeadStack's main workflows with a screen reader. It
completes the automated checks of 13-H4 (axe in component tests; labels,
names, contrast and overflow in Chrome), which cannot judge whether the
spoken experience makes sense. Record each item as pass, fail (with what was
heard) or not applicable, with the date, browser and screen-reader version.

## Set-up

| Screen reader | Browser | Platform | Basic keys |
| --- | --- | --- | --- |
| NVDA (latest) | Firefox and Chrome | Windows | Insert+Space browse/focus mode, H headings, D landmarks, F form fields, B buttons, Insert+F7 elements list |
| VoiceOver | Safari | macOS | VO = Ctrl+Option; VO+U rotor, VO+Cmd+H headings, Tab between controls |
| VoiceOver | Safari | iOS (390 px) | swipe next/previous, rotor two-finger twist, double-tap activate |

Use a test workspace with sample data (contacts, a deal, an appointment, a
campaign draft, an automation, a template, a conversation). Never test with
real customer data.

## Everywhere (check once per screen)

- [ ] The page title and the single `h1` name the screen.
- [ ] "Skip to content" is the first stop and moves to the main region.
- [ ] Landmarks are announced: banner, navigation, main.
- [ ] Heading levels are in order; every section has a heading or label.
- [ ] Every button and link says what it does ("Delete Follow up", not "Delete" or "button").
- [ ] Icon-only buttons (edit, delete, close) have spoken names.
- [ ] Badges and statuses are read as text, not by colour alone.
- [ ] Loading, empty and error states are announced (errors as alerts).
- [ ] Toasts ("Saved", "Reminder queued") are announced once, without stealing focus.
- [ ] Focus is always visible; it never lands on something hidden.

## Dialogs and drawers

- [ ] Opening one moves focus into it and announces its title.
- [ ] Tab stays inside it; Escape closes it.
- [ ] Closing returns focus to the control that opened it.
- [ ] A confirmation ("Cancel this appointment?") reads its question and both choices.

## Workflows

**Sign-in and workspace**
- [ ] The workspace switcher announces the current workspace and opens as a menu.
- [ ] The navigation reads each section; the current page is announced.

**Contacts**
- [ ] The table announces column headers and sort state ("Name, sorted ascending").
- [ ] Filters (stage, owner, tags) announce their state and the count of results.
- [ ] New contact: each field's label, required fields and errors are read
  and tied to their field; focus moves to the first error.
- [ ] Contact drawer: sections (notes, activity, deals, appointments) are reachable by heading.

**Deals and pipeline**
- [ ] The board is usable without dragging: a stage can be changed from the deal's own controls.
- [ ] Won/lost outcome and value are read with their currency.

**Calendar and reminders**
- [ ] Day, week and month views announce the range; appointments read time, title and status.
- [ ] Booking dialog: date, time and length fields are labelled; a conflict warning is announced.
- [ ] Appointment drawer: status choices are read as toggle buttons with their pressed state; the Reminders section reads the setting, the next reminder or why none is planned, and past reminders.
- [ ] "Send reminder" announces success or the reason it was refused.

**Inbox**
- [ ] Conversation items read contact, subject and status; the selected one is announced.
- [ ] Composer: the mode, "Use a template" and the text box are labelled; the "queued, not sent" hint is read.
- [ ] Review queue: each held message reads its reason.

**Campaigns and templates**
- [ ] "Campaigns cannot be sent yet" is read near the top.
- [ ] Campaign states (draft, awaiting approval) and the eligibility estimate are read.
- [ ] Template list reads name and subject; edit and delete name the template.
- [ ] Template editor: the placeholder hint is read; a refusal names the problem.

**Automations**
- [ ] The trigger picker ("When this happens"), its tag, form, page or stage choice, the condition and each step are labelled with their branch and number.
- [ ] Adding and removing steps announces the change.
- [ ] Run history reads each run's status and steps.

**Reports**
- [ ] Each card reads its title, figures and comparison; the CSV button names its report.
- [ ] The period picker announces the chosen period.

**Settings**
- [ ] Business profile: the reminder lead time is a labelled select.
- [ ] Domains and Sending domains: DNS records are read as a table with headers; the deadline, status and "no provider connected" notes are read; the "Use this address for" group reads both choices.

**Public pages (no sign-in)**
- [ ] Booking page: times are buttons with their full date and time; the honeypot field is never announced.
- [ ] Form page: labels, required fields, consent text and errors are read; success is announced.
- [ ] Unsubscribe and booking-management pages read their outcome.

## At 390 px (iOS VoiceOver)

- [ ] The navigation opens and closes from its button and is announced as expanded or collapsed.
- [ ] Tables that scroll sideways (contacts) are reachable and announce their headers.
- [ ] Dialogs fit the screen; no control is reachable only by scrolling sideways.

## Reporting

File each failure with the screen, the step, what was heard, what was
expected, the screen reader, browser and versions, and the WCAG criterion if
known. Fixes get a regression test where practical (13-H4).
