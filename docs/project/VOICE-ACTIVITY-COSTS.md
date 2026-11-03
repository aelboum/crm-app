# AI voice agents: cost estimate for a provider bake-off and the legal review

**Status:** an estimate, 2026-11-03, under the owner's instruction of that
date: "Do not create paid vendor sandbox accounts. Do not commission legal
counsel yet. Prepare a cost estimate for both activities, including any
minimum commitments." Neither activity is approved. Figures come from
public pages only; no account was created and no vendor or law firm was
contacted. Running costs per call minute are in `VOICE-COST-MODEL.md`.

Flags: **[V]** read on the official page; **[S]** secondary source (a
commercial guide or a search summary); **[U]** not verified; **[I]**
inference.

## 1. Summary

| Activity | Estimate | Minimum commitments | Main blocker |
| --- | --- | --- | --- |
| Bake-off: 3 platforms × 30 Dutch test calls | **About $60–120 out of pocket; budget €150 with a buffer** [I] | None for the self-serve tiers. Vapi's EU region needs the Premier package (custom price, no published minimum). ElevenLabs EU residency and zero retention are Enterprise only (no published minimum) | A Dutch local or national number needs a KvK extract and a Dutch business address; trial accounts call only verified numbers |
| Legal review and DPIA | **About €5,000–12,000 at a boutique firm; €15,000–35,000 at a large Amsterdam firm** [I] | None published | No published fee survey; scope to be fixed with counsel |

## 2. Bake-off

### 2.1 Trial terms and minimums

| Vendor | Free credit or trial | Paid entry and minimums | EU and Dutch notes |
| --- | --- | --- | --- |
| Deepgram | $200 credit, no card, does not expire [V] | Voice Agent pay-as-you-go $0.075 a minute (Standard), $0.163 (Advanced), billed on connection time [V]; Growth plan from $4,000 a year, prepaid [V] | EU agent endpoint exists, no fallback region [V]; **whether free and pay-as-you-go accounts may use it is not stated** [U] |
| ElevenLabs | 15 agent minutes on the free plan [V] | Starter $6 (first month $1), 75 minutes; Creator $22 (first month $11), 275 minutes; Pro $99; extra minutes $0.08; the LLM is billed separately [V]; Enterprise custom, **no published minimum** [V] | Bring your own Twilio or SIP [V]; zero retention for Agents is Enterprise only [V] |
| Vapi | $5 credit [V] | Base $0.05 a minute, no minimum; Core $29 a month; Pro has a $999 a month minimum; Premier custom [V] | **The EU region only on Premier** (minimum not published) [V] |
| Telnyx | $5 trial credit; the trial dials only the account's own verified number and allows one number, reclaimed after 30 days without an upgrade [V] | Numbers "from $1 a month" [V]; Dutch per-minute and number prices not public [U] | Identity checks and company details before international numbers and calling, review up to 48 hours [S] |
| Twilio | 75 voice minutes for 30 days; calls only to up to 5 verified numbers, within the sign-up country [V] | Upgrade needs a profile, address, payment method and starting balance; minimum not stated [U] | Dutch number rules below [V] |

### 2.2 Dutch numbers for a test

- **Not +3197 numbers:** they are machine-to-machine blocks that "cannot be
  used for standard person-to-person (P2P) voice" (Twilio's Dutch
  guidelines) [V]. Twilio's $7.70 "mobile" number is of this type, so it is
  not usable for an AI voice line.
- **Local numbers:** a KvK extract or ID plus an address inside the area
  code; no PO box; Telnyx wants proof under 3 months old [V].
- **National numbers:** a Dutch address; Telnyx sells them to businesses
  only [V].
- So a bake-off on real Dutch numbers needs LeadStack's (or a test
  business's) KvK registration and a Dutch business address first. Monthly
  prices for local and national numbers are not published by Twilio or
  Telnyx [U]; estimated $1–8 a month [I].

### 2.3 Estimate (30 calls × 4 minutes = 120 minutes per platform)

Carrier minutes priced at Twilio outbound to Dutch mobiles from the EEA,
$0.0241 a minute [V].

| Platform | Platform usage | Carrier (120 min) | Number, 1 month | Out of pocket |
| --- | --- | --- | --- | --- |
| Deepgram | $9 (Standard) to $19.56 (Advanced), covered by the $200 credit | about $2.90 | $1–8 [U] | **about $5–15** |
| ElevenLabs | Creator, $11 the first month, covers 275 minutes; LLM $2–10 [I] | about $2.90 | $1–8 [U] | **about $20–35** |
| Vapi | $6 hosting plus $6–12 pass-through speech and LLM [I], less the $5 credit | about $2.90 | $1–8 [U] | **about $15–30**, outside the EU region unless on Premier |
| Carrier prepaid balances | Twilio and Telnyx, about $20 each [U] | | | about $20–40 |
| **Total** | | | | **about $60–120** |

The LLM for every test turn goes through SaaS-OS governed inference, so its
cost falls under LeadStack's own model account (included above as an
estimate).

What the low self-serve price does **not** buy: an EU-only test on Vapi
(Premier) or with ElevenLabs zero retention (Enterprise). A test outside the
EU region would use only scripted test data, never real customer data.

## 3. Legal review and DPIA

| Item | Estimate | Basis |
| --- | --- | --- |
| Hourly rates, Netherlands | €150–400 excluding VAT, averages around €200–350; Zuidas partners €400–600, senior partners up to €800; specialists €250–400 | Commercial guides (advocatenhub.nl, trustoo.nl, legal8.nl) [S] |
| DPIA, fixed fee | Generic DPIAs from about €2,000–2,500 (RISKID €2,500; VDT Advocaten €1,975); an AI voice DPIA likely more | Search summaries [S]; [I] |
| Opinion on Telecommunicatiewet 11.7 and AI Act Art. 50 (questions in `VOICE-LEGAL-REVIEW.md` §2.1–2.2) | 8–20 hours, about €2,000–9,000 | [I] |
| Processor agreement and sub-processor terms | 4–10 hours, about €1,000–4,000 | [I]; templates exist but would not cover voice |
| Remaining questions (recording, transfers, telecom status, consumer law) | 4–10 hours, about €1,000–4,000 | [I] |
| **Total** | **Boutique €5,000–12,000; large Amsterdam firm €15,000–35,000** | Sum of the above at €200–350 versus €400–600 an hour [I] |

No minimum commitments were found. A fixed-fee quote against the question
list in `VOICE-LEGAL-REVIEW.md` is the way to make the figure firm.

Free channels:
- The Dutch government publishes a free DPIA guide
  (ondernemersplein.overheid.nl) [V].
- Prior consultation with the Autoriteit Persoonsgegevens (GDPR Art. 36),
  for high residual risk after a DPIA, has no fee as far as found; its
  procedure page could not be read [U].
- No free ACM advisory channel for telemarketing was found [U].

## 4. Provider questions resolved by this research

| Question | Answer |
| --- | --- |
| Twilio ConversationRelay and Media Streams in Ireland (IE1) | **Yes**: "Connect Stream and Connect ConversationRelay are now available in the Ireland (IE1) and Australia (AU1) Regions" [V] |
| Twilio's Dutch "mobile" number | **+3197 machine-to-machine**, not usable for person-to-person voice [V] |
| Telnyx Dutch numbers | Local, national, mobile (application use only) and toll-free exist [V]; per-minute rates not public [U] |
| Deepgram Dutch | Nova-3 recognises `nl` and `nl-BE`; Aura-2 has Dutch voices [V]; set by `agent.listen.provider.language` [V] |
| ElevenLabs zero retention for Agents | Enterprise only, for selected customers, set per agent [V] |

These answers are also reflected in `VOICE-PROVIDER-COMPARISON.md`.

## 5. Sources

deepgram.com/pricing; developers.deepgram.com (regional endpoints, models
and languages, TTS models, configure voice agent);
elevenlabs.io/pricing/agents;
elevenlabs.io/docs/developer-guides/zero-retention-mode; vapi.ai/pricing;
docs.vapi.ai/security-and-privacy/eu-region;
developers.telnyx.com/docs/account-setup/levels-and-capabilities/trial;
support.telnyx.com (articles 1130595, 1311472);
twilio.com/docs/usage/tutorials/how-to-use-your-free-trial-account;
twilio.com/en-us/guidelines/nl/regulatory; twilio.com/en-us/voice/pricing/nl;
twilio.com/docs/voice/twiml/connect; advocatenhub.nl; trustoo.nl;
legal8.nl; dpia.riskid.nl; vdt-advocaten.nl; ondernemersplein.overheid.nl;
acm.nl. Checked 2026-11-03.
