# Role upgrade runbook (gate G7, decisions P2-G7 and 13-R1)

Workspaces created before a permission was added to the role templates
(`crm_app.roles.ROLE_TEMPLATES`) do not hold it: SaaS-OS v0.6.0 has no
documented way to grant a new permission to existing tenants' roles
(upstream request saas-os #88). `python -m crm_app.role_upgrade` closes that
gap, one reviewed step at a time. **It has never been run against a real
workspace; running it there needs the owner's approval** (it changes what
customers' members may do).

## What it does and never does

- Compares each product role (Owner, Admin, Member, Read-only) with its
  template and grants only what is missing from that template.
- Never revokes a grant, creates or renames a role, touches a membership,
  or grants outside the role's own template; custom grants are kept and
  counted.
- Holds back administrative and safeguarded permissions unless
  `--include-administrative` is given.
- Skips a workspace that is not active or lacks the four product roles.
- Each grant is SaaS-OS's audited `grant_permission`
  (`role_permission.grant` in the audit log); a re-run grants nothing twice.
- Prints identifiers and permission names only.

## Procedure

1. **Back up** (or confirm the point-in-time backup of) the production
   database. Nothing is deleted, but the change is to access control.
2. **Dry run**, one workspace first, then the set:

       python -m crm_app.role_upgrade --workspace <id> --confirm-production
       python -m crm_app.role_upgrade --all --confirm-production --json > plan.json

   The text report starts with `plan fingerprint: <16 hex>`; the JSON
   report carries the same `fingerprint`, every workspace, and per role what
   it would `grant`, what is `held_back` and how many custom grants are kept.
3. **Review** `plan.json` with the owner: the permissions, the workspaces,
   anything held back. Record the fingerprint and the approval in the change
   record.
4. **Apply exactly the reviewed plan**:

       python -m crm_app.role_upgrade --all --apply --confirm-production \
           --expect <fingerprint> --json > applied.json

   In production `--apply` refuses to run without `--expect`, and refuses if
   anything changed since the dry run (a workspace created, a grant made):
   then repeat steps 2 and 3. Administrative permissions need a separate,
   explicitly approved run with `--include-administrative` (its own dry run
   and fingerprint).
5. **Verify**: run the dry run again; it must show nothing to grant. Keep
   `plan.json` and `applied.json` with the change record; the audit log has
   one `role_permission.grant` entry per grant.

## Rollback

There is no automatic revoke (by design: the command only ever adds what
the approved matrix already gives new workspaces). To undo a grant, an
owner removes it with SaaS-OS's audited role-permission revocation for the
affected roles, using `applied.json` as the list.
