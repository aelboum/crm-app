# AI voice agents: hosted voice platforms and telephony providers compared

**Status:** research for the deferred provider decision (P15-V point 3),
2026-11-03. Web research from official pricing pages and documentation; no
account was created, nothing was purchased, no number was requested. Prices
are list prices on the date checked and change often; anything marked
*unverified* could not be confirmed from a primary source. Architecture
assumed: option A of `VOICE-AGENTS-BRIEF.md` §6.2 (the platform handles
audio; every LLM turn goes to LeadStack's own endpoint and through SaaS-OS
governed inference). Costs per minute: `VOICE-COST-MODEL.md`.

## 1. What LeadStack needs from a voice platform

1. A **custom LLM endpoint**: the platform calls LeadStack for every turn
   (ideally OpenAI Chat Completions-compatible, so it is portable).
2. **EU residency** for audio, transcripts and storage, contractually,
   without silent fallback to other regions.
3. **Dutch** speech recognition on phone audio (8 kHz) and natural Dutch
   voices.
4. Call **transfer** to people (warm and cold), voicemail detection, DTMF.
5. Telephony: Dutch (+31) numbers, or bring-your-own carrier or SIP trunk.
6. A **DPA**, a published **sub-processor list**, retention controls
   (zero retention ideally), recording off.
7. Webhooks and events LeadStack can verify per tenant.
8. Reasonable per-minute pricing, concurrency and a test tier.
9. **Portability:** a generic contract, so swapping platforms is a
   configuration and adapter change, not a rewrite.

## 2. Hosted voice platforms

| Platform | Custom LLM | EU residency | Dutch | Telephony | Platform price per minute | Concurrency | DPA and sub-processors |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Deepgram Voice Agent API** | Any OpenAI Chat Completions endpoint | **EU endpoint generally available, self-serve** (`api.eu.deepgram.com`), fails closed rather than falling back; full in-region processing also needs the model-improvement opt-out | Nova-3 streaming lists Dutch; agent-level Dutch recognition and Dutch voices to confirm | None: bring Twilio or Telnyx audio | $0.065 with own LLM; $0.050 with own LLM and speech synthesis | Up to 45 in the EU on Growth | SOC 2; sub-processor list not found |
| **ElevenLabs Agents** | OpenAI Chat Completions or Responses API over SSE; function calling | **EU isolated environment on Enterprise only**; processing limited to the EU only with Zero Retention Mode; a custom LLM and webhooks may be out of region (LeadStack's endpoint is in the EU) | Likely the strongest Dutch voices (quality unverified) | Bring Twilio or SIP | $0.08 ($0.16 when bursting) | 4 to 40 by plan | DPA (elevenlabs.io/dpa); sub-processors (compliance.elevenlabs.io); SOC 2 unverified |
| **Vapi** | OpenAI-style `/chat/completions`, streaming in practice; Vapi tools (transfer) | **Isolated EU region (dashboard, API, SIP) on the Premier package only (sales)** | Through the chosen speech engines (Dutch unverified) | Own numbers, bring SIP trunk, Twilio or Telnyx | $0.05 hosting; speech and models at cost | 4 free, 10 Core, 30 Pro; +$10 per line a month | SOC 2 Type II; sub-processors at security.vapi.ai; zero retention from Core; recordings and transcripts to the customer's own storage |
| **Telnyx Voice AI** | OpenAI-compatible base URL | Data locality Germany: storage at rest is a hard EU control; **EU processing is best effort, not guaranteed** | Unverified | Telnyx is a carrier: numbers and SIP built in (+31 availability unverified) | $0.05 voice engine (speech in and out) | 500 on pay-as-you-go | DPA found; sub-processor list not found |
| **Twilio ConversationRelay** | LeadStack runs the WebSocket and the LLM loop | Twilio Ireland (IE1) supports Programmable Voice; **ConversationRelay in IE1 unverified**; in US1 audio and transcripts are processed in the US | Dutch defaults documented (Google speech recognition, ElevenLabs voices) | Twilio numbers, including +31 (regulatory bundle) | $0.07 plus voice minutes | Unverified | Twilio DPA and sub-processor list |
| **Retell AI** | Its own WebSocket protocol (not OpenAI-compatible) | **US only** (standard contractual clauses) | Unverified | Own numbers; bring SIP, Twilio or Telnyx | $0.055 plus speech synthesis and LLM | 20 included; +$8 per call a month | SOC 2 |
| **Synthflow** | Non-enterprise accounts are locked to Synthflow's LLM | "EU hosting" claimed | Unverified | SIP by contract | Enterprise annual contracts only | Contracted | SOC 2, ISO 27001 |
| **Bland AI** | Enterprise only, sales-assisted | EU not stated | Unverified | Bring Twilio or SIP | $0.12–$0.14 bundled | 10 / 50 | SOC 2, ISO 27001, DPA |
| **OpenAI Realtime, Azure Voice Live, Gemini Live** | No: the provider's model is the conversation (speech-to-speech); Voice Live's own-model mode is in preview | Azure realtime SIP only in Sweden Central and East US 2 (global deployment) | Good (unverified) | Azure via Azure Communication Services | Per token | Quota | Provider DPAs |
| **CM.com HALO** (Dutch) | Not documented | Dutch company, EU processing (secondary source) | 70+ languages | CM voice and SIP | From €1,000 a month | — | Unverified |
| **Sinch Voice Relay** (Swedish) | WebSocket to the customer's agent | Unverified | 160+ languages claimed | Sinch numbers | Unverified | — | Pages blocked to automated reading |
| **Bird** (Dutch), **Vonage AI Studio** | Bird: voice agents launched Sept 2026, undocumented; Vonage: own engine, own AI only through WebSockets | Unverified | — | Own networks | Unverified | — | Bird DPA and sub-processor list found |

Speech-to-speech models (OpenAI Realtime, Gemini Live, Azure Voice Live)
conflict with keeping each turn inside LeadStack's governed inference, so
they are excluded for now. Retell is excluded on residency (US only);
Synthflow and Bland because LeadStack cannot supply its own LLM on standard
terms.

## 3. Telephony providers (Dutch numbers and minutes)

| Provider | NL number a month | Inbound per minute | Outbound NL landline / mobile per minute | Billing | Streaming audio | EU region | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Twilio** | Mobile $7.70; local NL not shown | Mobile number $0.0100; SIP or app $0.0040 | **From the EEA: $0.0179 / $0.0241**; from outside the EEA $0.3675 / $0.2763 | Not stated | Media Streams $0.0044 | Ireland (IE1) for Programmable Voice and Elastic SIP; Media Streams in IE1 unverified | Recording $0.0025 a minute, storage $0.0005 a minute-month |
| **Twilio Elastic SIP** | Mobile $7.70 | Origination $0.0060 | From the EEA $0.0139 / $0.0201 | Not stated | — | IE1 | For a platform that takes SIP |
| **Telnyx** | Local from $1.00 | $0.002 plus SIP fee | **NL rates not published** | Not stated | $0.0035 | `api.telnyx.eu`, data locality Germany (storage at rest) | Media anchoring in Frankfurt |
| **Sinch** | Generic $0 shown (unverified for NL) | Generic $0.00 shown | **From NL: $0.01 / $0.035**; other origins $0.187 / $0.378 | Per minute (60 s / 60 s) | Not stated | Unverified | Rate sheet valid from 2026-10-15 |
| **Plivo** | Not shown | **NL inbound "not supported"** | From the EEA $0.0145 / $0.0195 | Not stated | Included | Unverified | Excluded for inbound |
| **CM.com** (Dutch) | Not shown | Not shown | From €0.0075 (not split) | Per second | Not shown | Dutch company | Full list after registration |
| **Vonage, Bird** | Not retrievable | — | — | Vonage per second | — | — | Prices behind a login or US-only tables |
| Dutch SIP providers (Voys/Holodeck, Speakup, Voiceworks) | No public API price lists found | | | | | | Worth asking for business SIP trunks |

**Origin matters:** terminating Dutch calls is 10 to 30 times cheaper when
the call originates in the EEA (Twilio, Plivo) or in the Netherlands
(Sinch); the voice platform and carrier must be configured that way.

**Dutch number rules** (as reflected in Twilio's regulatory guidelines,
which follow ACM rules; to be confirmed with the provider chosen):

- Geographic (local) numbers: a business needs a KvK extract and an address
  inside the number's area (no PO box).
- National numbers: a KvK extract or ID and a Dutch address.
- **+3197 (machine-to-machine) mobile numbers: ACM forbids person-to-person
  voice on them.** Twilio's only listed Dutch number is "mobile" at $7.70;
  whether that is a +3197 number must be checked before any plan relies on
  it.
- Toll-free +31800: no documents.

Account holder: to avoid LeadStack becoming an electronic communications
provider itself (ACM registration, 112 duties; `VOICE-LEGAL-REVIEW.md` Q23),
numbers should be held under the business's or the agency's own account
with a licensed carrier.

## 4. Model providers, through SaaS-OS

Every LLM turn goes through `saas_os.inference`. In v0.6.0 its adapters are
`openai_compatible`, `anthropic_messages` and `gemini_generate_content`;
**the Bedrock and Vertex AI protocols are not implemented** (SaaS-OS
`AI-INFERENCE-ROADMAP.md`). That matters for EU processing:

| Model (fast tier) | List price per 1M tokens in / out | EU processing route | Reachable through SaaS-OS v0.6.0 |
| --- | --- | --- | --- |
| Claude Haiku 5.5 | $0.10 / $0.50 | First-party API offers "us" or "global" only; EU through Bedrock or Vertex regional (+10%) | Not in the EU (no Bedrock or Vertex adapter) |
| OpenAI gpt-6-luna | $0.10 / $0.50 | Regional processing endpoints (+10%) | Through `openai_compatible`, if the regional endpoint is configured by platform operations |
| OpenAI gpt-5.4-mini | $0.75 / $4.50 | Same | Same |
| Gemini 3.8 Flash | $0.75 / $3.75 until 2026-12-31, then $1.50 / $7.50 | Vertex europe regions | Not through Vertex (adapter missing); the Gemini API route's region unverified |

EU processing of the model is therefore another reason for the SaaS-OS
requests (`SAAS-OS-REALTIME-PROPOSAL.md`): either Bedrock or Vertex
adapters, or a confirmed EU endpoint through an existing adapter.

## 5. Shortlist (for a bake-off, not a choice)

1. **Deepgram Voice Agent API with an EU carrier** (Twilio IE1 or Telnyx
   EU): the only self-serve, generally available EU endpoint that fails
   closed; a plain OpenAI-compatible LLM contract (easy to swap); the
   lowest own-LLM rate. Costs: LeadStack builds transfer, voicemail
   detection and DTMF handling; Dutch recognition on phone audio must be
   proven.
2. **ElevenLabs Agents:** the best-specified custom-LLM contract and likely
   the best Dutch voices; EU residency needs an Enterprise contract (price
   and written zero-retention confirmation needed).
3. **Vapi (EU region):** the richest call features (transfers, SIP, own
   storage for transcripts) and published SLAs; the EU region needs the
   Premier package (price needed).

Runner-up: **Telnyx** as one vendor for carrier and voice, if EU storage at
rest without guaranteed EU processing is acceptable.

## 5a. Answered on 2026-11-03 (public documentation; detail in `VOICE-ACTIVITY-COSTS.md` §4)

- **Twilio ConversationRelay and Media Streams run in Ireland (IE1)** (`<Connect>`
  documentation).
- **Twilio's Dutch "mobile" number is a +3197 machine-to-machine number** and
  cannot carry person-to-person voice; an AI voice line needs a local or
  national number (KvK extract and Dutch address).
- **Deepgram:** Nova-3 recognises Dutch (`nl`, `nl-BE`) and Aura-2 has Dutch
  voices; trial accounts get a $200 credit; whether free or pay-as-you-go
  accounts may use the EU endpoint is not stated.
- **ElevenLabs:** zero retention for Agents is Enterprise only.
- **Telnyx:** Dutch local, national, mobile (application use only) and toll-free
  numbers exist; Dutch per-minute rates are not public.

## 5b. Second research pass (2026-11-03): integration details

[V] read on the vendor's page; [S] secondary or search text only; [U] not
found. Public documentation only.

| Topic | Deepgram Voice Agent | ElevenLabs Agents | Vapi | Telnyx Voice AI | Twilio ConversationRelay |
| --- | --- | --- | --- | --- | --- |
| Latency claim | Median under 700 ms, P90 under 1 s (one vendor set-up) [S]; per-turn `LatencyReport` [S] | None numeric; speech starts at the first comma [V] | None [U] | None [U] | Median under 0.5 s, P95 under 0.725 s (internal) [S] |
| Turn detection | Flux `eot_threshold`, `eager_eot_threshold`, `eot_timeout_ms`, changeable mid-call; `ForceEndTurn` [V] | `turn_timeout`, `turn_eagerness`, filler while the LLM is slow [V] | `waitSeconds`; "vapi" smart endpointing recommended for non-English (Dutch) [V] | Flux or `wait_seconds` [S] | Inside the speech provider [U] |
| Barge-in signal | `UserStartedSpeaking`; our bridge clears the carrier audio [V]; `defer_until_eot` holds function calls until the turn is final [V] | Interruption on or off [V]; cancel to the custom LLM [U] | `stopSpeakingPlan` [V]; abort of the in-flight LLM call [U] | On by default; backchannel threshold [S] | `interrupt` with what the caller actually heard (`utteranceUntilInterrupt`) [V] |
| Custom LLM | Any Chat Completions endpoint, free-form headers [V]; streaming requirement [U] | Chat Completions or Responses, **SSE required** [V] | `/chat/completions`, API key or OAuth2 [V]; call metadata option [S] | `/v1/chat/completions` [S]; stored bearer key [V]; metadata forwarding [V] | Our own WebSocket loop (no LLM contract) [V] |
| Webhook signing | No webhooks: WebSocket events | HMAC header, one secret per webhook [V]; dedupe on conversation id [V] | Bearer, secret header, OAuth2 or **HMAC with timestamp** [V]; 7.5 s limit on assistant requests [V] | Ed25519 signature and timestamp [S] | HMAC-SHA1 `X-Twilio-Signature` [V]; idempotency token header and retry overrides [V] |
| Retention | Model-improvement programme **on by default** (keeps audio): `mip_opt_out: true` required [V]; no deletion API found [U] | `retention_days` (default 2 years) [V]; delete API [V] | Zero data retention org-wide [V] (another page calls it an add-on [S]); delete API [V] | [U] | [U] |
| Transfers | Our carrier code [I] | Warm and blind **only with native Twilio**; SIP REFER on trunks [V] | Mostly Twilio-only warm modes; one experimental on own SIP [V] | SIP REFER, warm transfer [S] | Carrier features [S] |
| Outbound | 45 concurrent per project in the EU [V]; voicemail detection from the carrier | Voicemail tool [V]; caller ID must be a Twilio number [V]; Twilio IE1 compatibility [U] | Voicemail detection options [V]; plan-based concurrency [V] | Voicemail detection [U] | Answering-machine detection [V]; in IE1 [U] |
| Configuration as code | The whole agent is our own JSON settings [V] | CLI pull and push of JSON configs [V] | CLI for assistants [V] | JSON assistant API [V] | Our code |
| SLA | None public [U] | "SLAs" on Enterprise, no figure [S] | 99% Pro, 99.9% Premier [V] | 99.99% core voice [V] | APIs 99.95% [S] |

**What changes in the shortlist:**
1. **Deepgram stays first, with a condition:** `mip_opt_out: true` and the
   EU endpoint are mandatory, because by default it keeps audio. It has the
   best turn-detection controls and `defer_until_eot` (suited to tools that
   change data), and the configuration is entirely ours. Costs: LeadStack
   builds transfers, answering-machine detection and the barge-in clear on
   the carrier; no public SLA.
2. **ElevenLabs moves down for an EU set-up:** warm and blind transfers need
   its native Twilio integration (IE1 compatibility unverified); the static
   EU SIP endpoint and zero retention are Enterprise only; SSE is mandatory.
3. **Vapi improves on governance:** HMAC or OAuth2 webhooks, zero retention
   and a delete API; the EU region is still Premier only.
4. **Twilio ConversationRelay strengthens as the build-it-ourselves option:**
   the clearest interruption signal, documented retries and idempotency
   tokens, available in IE1.
5. **Telnyx rises slightly:** the only published voice uptime (99.99%), SIP
   REFER and Ed25519 signing.
6. **Gaps for every platform:** no published first-token timeout and no
   documented cancel to the custom LLM on interruption. Both must be
   measured in the bake-off.
7. **Dutch carriers:** no Dutch provider was found with a public
   programmable-voice API; CM.com is the only plausible Dutch SIP carrier
   (requirements unverified).

The shortlist for a bake-off is therefore: (1) Deepgram with Twilio IE1,
(2) Vapi, (3) Twilio ConversationRelay as the do-it-yourself baseline;
ElevenLabs and Telnyx as alternates. No provider is selected; selection
needs the owner's approval with this evidence.
## 6. Questions for vendors (before any account)

- Written EU processing and storage commitments, including sub-processors,
  and zero retention for agents.
- EU-tier pricing (Vapi Premier, ElevenLabs Enterprise).
- Dutch recognition accuracy on 8 kHz phone audio (no published benchmarks
  found); a sandbox for a bake-off.
- Twilio: monthly prices of Dutch local and national numbers.
- Deepgram: EU endpoint eligibility for pay-as-you-go accounts.
- Telnyx: Dutch rates and +31 availability; guaranteed EU processing.
- SLAs and uptime history (only Vapi publishes SLA tiers: 99% Pro, 99.9%
  Premier).
- Webhook signing: per-account secrets, header-based, replay protection.

## 7. Bake-off method (proposal, when the owner authorises sandbox accounts)

The same 30 scripted Dutch calls per shortlisted platform (bookings,
questions answered from knowledge, a transfer, an opt-out, background
noise, a strong regional accent), measured for: recognition word error
rate, time from end of speech to first audio, interruption handling, tool
success, cost per minute from the provider's own usage export, and how much
of the platform-specific adapter would change to swap platforms.

## 8. Sources

Platforms: docs.vapi.ai (custom LLM, EU region, data flow), vapi.ai/pricing,
docs.retellai.com, retellai.com/pricing, elevenlabs.io/docs (custom LLM,
data residency), elevenlabs.io/pricing/api, developers.deepgram.com (voice
agent LLM models, data, TTS models), deepgram.com/pricing, twilio.com
(conversational AI pricing, ConversationRelay voice configuration,
regional availability), telnyx.com/pricing/voice-ai, developers.telnyx.com
(custom LLM, data residency, regional endpoints), synthflow.ai/pricing,
docs.bland.ai, learn.microsoft.com (Voice Live, realtime SIP),
cm.com/pricing/halo. Telephony: twilio.com/en-us/voice/pricing/nl,
twilio.com/en-us/sip-trunking/pricing/nl,
twilio.com/en-us/guidelines/nl/regulatory, telnyx.com/pricing/call-control,
plivo.com/voice/pricing/nl, sinch.com/pricing/voice (and its price list),
cm.com/nl-nl/voice/sip-trunk. Models: platform.claude.com pricing and data
residency, developers.openai.com pricing, aistudio.google.com pricing.
Checked 2026-11-03.
