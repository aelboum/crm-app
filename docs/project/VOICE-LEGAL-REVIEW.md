# AI voice agents: DPIA requirements and questions for legal counsel

**Status:** preparation for a legal review, 2026-11-03, under decision P15-V
point 4: a legal review is **required before production implementation or
activation**. This document is not a legal determination. The legal summary
in `VOICE-AGENTS-BRIEF.md` §7 is a research summary of sources and must not
be treated as final; counsel decides. Nothing here is implemented.

Policies already set by the owner (P15-V) that counsel should review, not
assume:

- no call recording by default until an approved recording policy and legal
  review exist (point 7);
- explicit, demonstrable consent for every outbound AI call (point 8); no
  outbound calling until the legal interpretation and operational controls
  are reviewed.

## 1. DPIA requirements

A data protection impact assessment (GDPR Art. 35) is expected to be
mandatory: the Autoriteit Persoonsgegevens' list of processing that always
needs one (Stcrt. 2019, 64418) includes communications data and
large-scale observation of behaviour, and AI voice agents are new
technology processing conversations at scale. The DPIA is completed and
signed off before any pilot with real callers (slice V2 with real numbers).

### 1.1 Roles to settle first

| Party | Expected role (to be confirmed by counsel) |
| --- | --- |
| The business using LeadStack (the workspace) | Controller for its callers' data |
| An agency managing client workspaces | Processor or joint controller, depending on the contract |
| LeadStack | Processor for the workspace; AI Act *provider* of the voice agent system |
| Voice platform, telephony, speech and model providers | Sub-processors of LeadStack (or processors of the business, if it holds the accounts) |

### 1.2 What the DPIA must describe

1. **Processing:** inbound and outbound calls; caller number, voice audio in
   transit, transcripts, summaries, extracted fields, call outcomes, the
   CRM changes proposed from a call, consent and opt-out records, usage
   records.
2. **Purposes:** answering and routing calls, booking appointments,
   qualifying leads, follow-up; marketing calls only with consent.
3. **Legal basis per purpose:** contract or legitimate interest for
   answering inbound calls; consent for outbound AI calls (P15-V point 8)
   and for any recording; the balancing test where legitimate interest is
   used.
4. **Data subjects:** callers, contacts called, the business's staff
   (transfers), third parties mentioned in calls.
5. **Data flows and locations:** each provider in the call path, its region,
   what it stores and for how long, and every transfer outside the EEA with
   its mechanism.
6. **Retention:** call metadata, transcripts, summaries, recordings (none by
   default), consent evidence, logs; separately for each (§3).
7. **Necessity and proportionality:** why each data item is needed; why no
   recording is the default; no speaker identification or voice biometrics.
8. **Rights:** how access (including transcripts), rectification, erasure,
   objection to direct marketing (absolute, Art. 21) and restriction are
   handled per workspace, including the export of one contact's call data.
9. **Risks to people and their mitigations:** impersonation by caller ID
   (P7-V rule), unwanted calls, manipulation by an AI, misheard or wrong
   transcripts changing CRM data (human review), disclosure of other
   customers' data (tenant isolation), prompt injection by callers,
   provider breaches, transfers to the US.
10. **Automated decision-making:** confirm no decision with legal or
    similarly significant effect is taken by the agent alone (Art. 22);
    outcomes that change CRM data go through human review.
11. **Security measures:** `VOICE-THREAT-MODEL.md`.
12. **Consultation:** the business's DPO where it has one; prior
    consultation with the AP if high residual risk remains (Art. 36).

### 1.3 Artefacts needed before a pilot

- The signed DPIA and its review date.
- Processor agreements (Art. 28) with each sub-processor; an updated
  LeadStack sub-processor list and a notice process for changes.
- Transfer impact assessments for any non-EEA processing.
- Records of processing (Art. 30) for voice.
- Customer-facing terms: the business's duties as deployer (disclosure
  wording kept, consent collected, objections honoured).
- A privacy notice text a business can link from its greeting.
- An incident process covering voice data (Art. 33/34).

## 2. Questions for Dutch and EU legal counsel

### 2.1 Outbound calls and consent

1. Is a conversational AI agent an "automated calling system without human
   intervention" under ePrivacy Art. 13(1) and Telecommunicatiewet
   art. 11.7(1)? If so, does that apply to calls to businesses (legal
   persons) as well as consumers?
2. What makes consent to AI calls *demonstrable* under 11.7(1)? Which
   evidence must be kept (wording, time, channel, IP or call reference),
   and for how long?
3. Can consent given through a web form (with double opt-in, decision P7-V)
   cover AI phone calls, and what wording is needed so it is specific to
   AI calls?
4. Does consent for ordinary telemarketing cover AI calls, or is separate
   consent needed?
5. For calls to natural persons acting professionally (sole traders, VOFs),
   which rule applies, and may contact details published for business
   contact (11.7(3)) ever be used for an AI call?
6. Are non-marketing outbound calls (appointment confirmations, a callback
   the person asked for) direct marketing? Do they need consent when made
   by an AI?
7. How must the free, easy way to object (11.7(2)) be offered during an AI
   call, and is a spoken "say stop" plus a confirmation sufficient?
8. Are there calling-hour limits that apply (statute, the Code
   Telemarketing 2024, ACM guidance)? Is following the Code expected even
   when not a member?
9. Do rules of other EU member states apply when a Dutch business calls
   their residents, and which ones differ most (opt-in versus opt-out
   registers)?

### 2.2 AI Act

10. Is LeadStack the *provider* of an AI system that interacts directly
    with people (Art. 50(1)), and the business the *deployer*? What changes
    if an agency configures and resells the agent?
11. What disclosure wording and timing satisfy Art. 50(1) and (5) on a
    phone call? May the business shorten or rephrase it?
12. Which Art. 50(2) marking obligations apply to synthetic speech on a
    phone line, and from which date for LeadStack (the Digital Omnibus,
    Regulation 2026/1744, and the status of systems placed on the market
    before 2 August 2026)?
13. Would any planned use fall under high-risk categories (Annex III) or a
    prohibited practice (Art. 5), for example persuasion techniques in
    sales calls?
14. Does offering a choice of synthetic voices, without cloning a real
    person, raise any Art. 50(4) duty?

### 2.3 Recording, transcripts and retention

15. With recording off by default, is a live transcript itself a
    "recording" for the information duty at the start of the call?
16. If a business turns recording on later: which legal basis, which
    spoken notice, and is consent needed for recording?
17. What retention periods are defensible for transcripts, summaries and
    call metadata kept as CRM history (§3)?
18. Must callers be able to receive their transcript on an access request,
    and within what period?

### 2.4 Privacy and transfers

19. Is the controller and processor split in §1.1 right for direct
    customers and for agencies?
20. Is a DPIA required per business, or can LeadStack provide a template
    DPIA the business completes?
21. Under which conditions may a US-based voice or model provider be used
    (the EU-US Data Privacy Framework, the pending appeal C-703/25 P), and
    should EU-only processing be a requirement?
22. Does caller-number matching against the CRM (as a claim, not as
    verification) need specific information to the caller?

### 2.5 Telecom and consumer protection

23. If LeadStack obtains Dutch numbers through a licensed provider for its
    customers, could LeadStack itself need ACM registration as an
    electronic communications service, with 112 and number-portability
    duties? Which account structure avoids that?
24. Which consumer-protection rules (the Unfair Commercial Practices
    Directive, Dutch Civil Code 6:193a and onwards) constrain AI sales
    calls, for example persistence and hidden commercial intent?
25. What liability does LeadStack carry when a business misuses outbound
    calling, and what contract terms, controls and audit evidence reduce
    it?

## 2a. Further requirements to put before counsel (2026-11-03)

A research summary, not legal advice; items marked "to confirm" were not
verified in a primary source this session.

### 2a.1 Special categories spoken during calls
Callers may volunteer health or other special-category data (GDPR Art. 9),
for example at a dental or medical practice, the design's example vertical.
Product controls proposed:
- extraction never targets special categories;
- summaries avoid repeating them;
- transcripts follow the shortest retention;
- a workspace can turn transcripts off.

Counsel to confirm the lawful basis, and whether a workspace in health care
needs stricter defaults.

### 2a.2 Transcription as processing
Even without recording, a live transcript is processing of the
conversation's content.

Proposed:
- the greeting says the call is handled by an AI and transcribed (with the
  disclosure);
- the privacy notice link is in the workspace's contact pages.

Counsel to confirm the wording and the legal basis (`§2.3` Q15).

### 2a.3 AI Act duties beyond Art. 50
- **AI literacy (Art. 4):** providers and deployers ensure sufficient AI
  literacy of the people operating the system, in force since 2 Feb 2025
  (to confirm whether the Digital Omnibus changed it).
  - Product support: operator guidance in the review screens and a short
    help page.
- **General-purpose AI models:** the upstream LLM and speech providers carry
  their own duties. LeadStack keeps their documentation and terms on file.
- **No high-risk use intended:** the product should not offer uses listed
  in Annex III (for example creditworthiness or employment screening by
  phone).
  - Product control: terms of use, plus agent templates limited to
    reception, qualification, booking and follow-up.

### 2a.4 Dutch numbers and telecom
- Number types (as reflected in carrier guidelines that follow the Dutch
  numbering rules):
  - geographic numbers need an address in the area;
  - national (085, 088) numbers need a Dutch address;
  - +3197 numbers are machine-to-machine and may not carry
    person-to-person voice.
- Caller ID must not be withheld for telemarketing (Tw 11.7(8)), and the
  number shown should be one on which the business can be reached (to
  confirm).
- Numbers held in the business's or agency's own carrier account, so
  LeadStack is not the number holder (`§2.5` Q23).
- Porting the business's existing number to a voice platform is a carrier
  process outside LeadStack; it is documented, not automated.

### 2a.5 Children and vulnerable callers
No targeting of minors.

Proposed:
- the agent offers a person when a caller seems to be a child or in
  distress;
- such calls are flagged for review.

Counsel to confirm whether more is needed.

### 2a.6 Cross-border calls
Outbound is limited to Dutch numbers at first. Calls to other member states
follow their own telemarketing rules (`§2.1` Q9), so other countries stay
off until reviewed.
## 3. Retention, documented separately (proposal for review)

| Data | Default proposal | Notes |
| --- | --- | --- |
| Recordings | **None** (not made) | Only after an approved recording policy and legal review (P15-V point 7) |
| Transcripts | 90 days, then deleted; configurable shorter | Needed for review and quality; counsel to confirm the period |
| Summaries and extracted fields | Kept with the contact as CRM history while the contact exists, removed with the contact | They are CRM records once reviewed |
| Call metadata (time, duration, direction, outcome, agent, numbers) | As CRM history, numbers masked in logs | Needed for reporting, disputes and billing |
| Consent and opt-out evidence | For as long as calls rely on it, plus the period counsel advises for proof | Opt-outs never expire |
| Usage records | As required for billing and tax | `core.usage` |
| Application logs | Ids, codes and durations only; the deployment's log retention | Never transcripts or audio |

## 4. Operational controls counsel should review (P15-V point 8)

- Consent check at dial time, failing closed; per-campaign approval; caller
  ID always shown; the disclosure spoken first and recorded as spoken;
  in-call opt-out effective immediately and across all the workspace's
  agents; frequency caps per number; a calling window; budget limits;
  emergency stop per workspace, per agency and platform-wide.
- Evidence export per call and per contact (consent, disclosure, opt-out,
  outcome) for disputes and regulators.
