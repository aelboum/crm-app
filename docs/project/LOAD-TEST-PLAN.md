# Load-test plan: one workspace with 50,000 contacts

**Status:** plan only, prepared on 2026-11-02 under the owner's instruction
"Prepare the 50,000-contact load-test plan and resource requirements". No
load test has been run. Nothing here touches a production system, a real
workspace or a paid service: the test runs against a local or disposable
test database only, with email sending, inbound processing, AI, billing,
tracking and custom domains all off. It expands item 2 of DECISIONS 13-O1.

## 1. Goal

Set a measured baseline, before production, for one large workspace:

- 50,000 contacts, 5,000 companies, 150,000 notes and activity entries,
  20,000 opportunities, 30,000 tasks, 10,000 appointments, 25,000 form
  submissions, 200 tags (up to 5 per contact), 50 active automations;
- plus 20 small workspaces (500 contacts each), so that the row-level
  security policies and indexes are exercised with other tenants present.

The question answered is "where does the product slow down first, and at
what size", not "is it fast". The result is a table of timings and a short
list of the first indexes or limits to change, which then go through the
normal review.

## 2. Pass marks (proposed; the owner may change them)

Measured on the reference machine in section 5, server-side time at the
95th percentile, warm cache, 10 concurrent users:

| Scenario | Pass mark |
| --- | --- |
| Contact list, first page, default sort | 300 ms |
| Contact list, page 50 by cursor | 300 ms |
| Contact search by name or email fragment | 500 ms |
| Contact list filtered by tag, owner and lifecycle stage | 500 ms |
| Contact record with notes, activity and opportunities | 300 ms |
| Pipeline board (all open opportunities of one pipeline) | 500 ms |
| Reports page, 90-day window, every card | 1.5 s per card |
| CSV export of all 50,000 contacts | 60 s, memory flat |
| CSV import of 10,000 rows (validate and commit) | 5 min |
| Public form submission | 300 ms |
| Reminder run for 1,000 due appointments | 2 min |
| Automation fan-out: one tag added to 5,000 contacts | runs drained in 15 min |

A scenario that fails its mark is reported with its query plan; it is not
fixed in the same change as the measurement.

## 3. Scenarios

1. **Read paths (HTTP):** the list, search, filter, record, pipeline and
   report requests above, through the real FastAPI app with a real session,
   so authorisation, row-level security and serialisation are in the timing.
2. **Write paths (HTTP):** create and edit contacts, add notes, move
   opportunities, submit public forms (with the rate limit raised for the
   test process only, never in configuration that ships).
3. **Bulk paths:** the CSV export (`records.EXPORT_BATCH = 1_000`) and an
   import of 10,000 rows (`import_commit.BATCH = 500`).
4. **Background work (the commands scheduled in `OPERATIONS.md`):** the
   email maintenance run with 1,000 due reminders (sending off, so messages
   are only queued; the run's own time is what is measured), the automation
   worker draining a 5,000-run fan-out, and the import clean-up.
   `python -m crm_app.health_check` runs before and after, and must report
   nothing overdue once each run finishes.
5. **Isolation under load:** while the scenarios run, a second user signed in
   to a small workspace repeats its own list and search; every response is
   checked to contain only that workspace's records. A single foreign row
   fails the whole test, whatever the timings.

## 4. Method

- **Database:** a disposable PostgreSQL database (the major version used in
  CI), migrated with `crm-app-migrate` to the current head. Never the shared
  `crm_app_test` database used by the integration suite, and never
  production.
- **Seeding:** a seed script under `tests/load/` (to be written), run with
  `ENVIRONMENT=test`, that creates the workspaces through the product's own
  services (so history, audit and search columns are filled as in real use),
  1,000 rows per transaction, with a fixed random seed so a run can be
  repeated. Names and emails are generated
  (`person-12345@load.example.test`); no real personal data.
- **Driver:** Locust or k6 against a local uvicorn with 2 workers, chosen
  when the script is written; either is a test-only tool and is not added to
  the product's dependencies without the usual review.
- **Measurement:** server timings from the access log,
  `pg_stat_statements` for the slowest queries, `EXPLAIN (ANALYZE, BUFFERS)`
  for every query over its mark, and process memory sampled once a second.
- **Repetition:** three runs per scenario; the median run is reported.
- **Clean-up:** the database is dropped after the run; the report keeps only
  timings, plans and counts, never generated rows.

## 5. Resource requirements

| Resource | Reference machine | Notes |
| --- | --- | --- |
| CPU | 4 cores | Driver, app and database on one machine; the report says so |
| Memory | 8 GB free | PostgreSQL `shared_buffers` 1 GB; each app worker about 300 MB |
| Disk | 10 GB free, SSD | Seeded database about 2–3 GB with indexes and audit, plus WAL while seeding |
| PostgreSQL | Same major version as CI | `pg_stat_statements` on, for the test database only |
| Redis | Local, as in development | Rate limits and idempotency keys |
| Time | About 1 working day | Half seeding and scripting, half running and reporting |
| Cost | None | Local only; no cloud or paid service |

The development laptop used so far is memory-constrained (the integration
suite already runs in groups for that reason), so it is not a fair
reference machine: timings taken there would understate the product. A
4-core, 8 GB machine or a disposable local VM is needed. A cloud VM is a
paid service and needs the owner's approval first.

## 6. Known before measuring (read from the code, not measured)

- Lists are cursor-paginated and capped (for example
  `conversations.LIST_LIMIT = 100`, `campaigns.LIST_LIMIT = 100`); no list
  endpoint is unbounded.
- Report queries have their own indexes (migration `0018_report_indexes`);
  conversation search has its own (migration `0023_conversation_search`).
- Contact search by fragment is the likeliest first slow path at 50,000
  rows; it is measured before any index is proposed.
- The automation worker and the email maintenance run process work in
  batches; how long a 5,000-run fan-out takes to drain at the current
  schedule is unknown and is the main background question.

## 7. Output

`docs/project/LOAD-TEST-REPORT.md`: the machine, the data sizes, a timing
table against section 2, the slowest queries with their plans, memory
curves for export and import, the isolation result, and a ranked list of
proposed changes, each one a separate, reviewable change.
