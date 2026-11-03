# AI voice agents: cost model (no commercial prices)

**Status:** a cost model, 2026-11-03, under decision P15-V point 5 ("Prepare
a cost model covering inbound minutes, outbound minutes, AI inference,
speech recognition, speech generation, recordings, storage and concurrency.
Do not establish commercial prices yet."). It estimates **LeadStack's
costs**, not prices to customers. Unit prices are list prices from
`VOICE-PROVIDER-COMPARISON.md` (checked 2026-11-03, USD unless stated) and
will change; volume discounts and EU-tier contract prices are unknown.

## 1. Cost per call minute: the formula

```
cost per minute =
    platform fee                       (voice platform, per minute)
  + speech recognition                 (if not included in the platform fee)
  + speech generation                  (characters spoken x price per character)
  + model inference                    (turns per minute x tokens x price)
  + telephony                          (inbound or outbound per minute, by destination)
  + audio streaming                    (carrier media stream, if used)
  + recording and storage              (zero by default: no recording, P15-V point 7)
fixed per month = phone numbers + concurrency lines above the plan + minimums
per call        = post-call summary inference + (later) any per-call fees
```

## 2. Assumptions (to be measured in the slice V2 sandbox)

| Assumption | Value | Basis |
| --- | --- | --- |
| Agent speaking share | 40% of call time | Estimate |
| Characters per minute of speech | 750–800 (Cartesia's published figure); 320 per call minute at 40% | Cartesia pricing page |
| Turns per minute | 4 | Estimate |
| Input tokens per turn | 3,000 (instructions, disclosure rules, knowledge snippets, history) | Estimate; grows with call length |
| Output tokens per turn | 60 (short spoken replies) | Token cap in the design |
| Post-call summary | 2,000 tokens in, 300 out, per call | Estimate |
| Average call | 4 minutes | Estimate |
| Transcript size | about 1 KB per minute | Estimate |

## 3. Unit costs per minute by component

| Component | Low | High | Notes |
| --- | --- | --- | --- |
| Platform fee | $0.050 (Vapi, Telnyx engine) | $0.080 (ElevenLabs Agents) | Deepgram Voice Agent with own LLM $0.065 (includes recognition and voice) |
| Speech recognition (if separate) | $0.0077 (Deepgram Nova-3) | $0.0150 (Azure West Europe, €0.0150) | Included in Deepgram, Telnyx and ElevenLabs fees |
| Speech generation (320 chars a minute) | $0.0096 (Deepgram Aura-2, $30 per 1M) | $0.0256 (ElevenLabs Multilingual, $80 per 1M) | Flash voices $0.0128 ($40 per 1M); included in some platform fees |
| Model inference (4 turns x 3,000 in / 60 out) | $0.0013 (Haiku 5.5 or gpt-6-luna, $0.10 / $0.50, +10% EU) | $0.0110 (gpt-5.4-mini, $0.75 / $4.50, +10% EU) | Through SaaS-OS; EU route limits in the comparison §4 |
| Telephony inbound | $0.0040 (Twilio SIP or app) | $0.0100 (Twilio mobile number) | Telnyx $0.002 plus SIP fee |
| Telephony outbound, NL landline | $0.0139 (Twilio SIP from the EEA) | $0.0179 (Twilio from the EEA) | Sinch from NL $0.01; from outside the EEA up to $0.37 (never configure that) |
| Telephony outbound, NL mobile | $0.0201 (Twilio SIP from the EEA) | $0.0350 (Sinch from NL) | |
| Audio streaming (if used) | $0 (included) | $0.0044 (Twilio Media Streams) | Telnyx $0.0035 |
| Recording | **$0** (none by default) | $0.0025 a minute + $0.0005 a minute-month storage (Twilio), only if a policy is ever approved | |
| Transcript storage | ≈ $0 | ≈ $0 | 100,000 minutes ≈ 100 MB in PostgreSQL |

## 4. Scenarios: cost per minute

| Scenario | Inbound | Outbound NL mobile |
| --- | --- | --- |
| **S1** Deepgram Voice Agent (own LLM) + Twilio IE1 audio | 0.065 + 0.0044 + 0.0040–0.0100 + 0.0013–0.0110 = **$0.075–0.091** | 0.065 + 0.0044 + 0.0201–0.0241 + 0.0013–0.0110 = **$0.091–0.105** |
| **S2** Vapi + Deepgram recognition + Flash voice + Twilio SIP | 0.050 + 0.0092 + 0.0128 + 0.0040 + 0.0013–0.0110 = **$0.077–0.087** (EU region: Premier price unknown) | 0.050 + 0.0092 + 0.0128 + 0.0201 + 0.0013–0.0110 = **$0.093–0.103** |
| **S3** ElevenLabs Agents (own LLM) + Twilio SIP | 0.080 + 0.0040 + 0.0013–0.0110 = **$0.085–0.095** (EU: Enterprise price unknown) | 0.080 + 0.0201 + 0.0013–0.0110 = **$0.101–0.111** |
| **S4** LeadStack-run pipeline (option C; not possible today) | 0.0092 + 0.0096 + 0.0044 + 0.0040 + 0.0013–0.0110 + compute ≈ **$0.03–0.05** | ≈ **$0.05–0.07** | 

Rule of thumb from these lists: **about $0.08 to $0.11 a minute** before
volume discounts, EU-tier contracts and number costs; a self-run pipeline
later could roughly halve it at the price of much more engineering and
operations.

## 5. Fixed and per-call costs

| Item | Cost | Notes |
| --- | --- | --- |
| Dutch number | $7.70 a month (Twilio mobile; check it is not a +3197 number, which may not carry person-to-person voice); local numbers need a KvK extract and an in-area address | Telnyx local from $1.00 (NL availability unverified) |
| Concurrency above the plan | Vapi +$10 per line a month; Retell +$8; Deepgram EU up to 45 on Growth; ElevenLabs 4–40 by plan | Size by peak simultaneous calls per workspace |
| Post-call summary | $0.0004 (Haiku 5.5) to $0.003 (gpt-5.4-mini) per call | 2,000 in / 300 out tokens |
| Minimum commitments | Unknown for EU tiers (Vapi Premier, ElevenLabs Enterprise); CM.com HALO from €1,000 a month | Needed before any choice |
| Legal review and DPIA | One-off, unknown | P15-V point 4 |

## 6. Example month for one workspace (S1, mid-range)

| Usage | Quantity | Cost |
| --- | --- | --- |
| Inbound minutes | 500 | 500 x $0.083 = $41.50 |
| Outbound minutes (NL mobile) | 300 | 300 x $0.098 = $29.40 |
| Calls (summaries) | 200 | 200 x $0.002 = $0.40 |
| Number | 1 | $7.70 |
| Recording | none | $0 |
| **Total** | 800 minutes | **≈ $79 a month**, ≈ $0.099 a minute all-in |

## 7. What a plan would meter (for later pricing, not set now)

`core.usage` metrics (any metric name works in v0.6.0): `voice_minutes_inbound`,
`voice_minutes_outbound`, `voice_calls`, `voice_campaign_recipients`,
`voice_numbers`; limits through `core.billing` entitlements: minutes a
month, concurrent calls, campaign size, numbers, daily spend cap. Hard stops
at the limit (`consume_quota` before each call), a maximum call length, and
budget alerts at 50%, 80% and 100%.

## 8. Sensitivities

- **Model choice** moves the cost by up to $0.01 a minute; the platform fee
  dominates.
- **Outbound origin:** a misconfigured non-EEA origin multiplies Dutch
  termination by 10 to 30 (up to $0.37 a minute): a configuration test is
  part of slice V4.
- **Premium voices** up to $0.026 a minute more.
- **Long prompts:** input tokens grow with call length; knowledge snippets
  and history must be bounded.
- **Price changes:** Gemini Flash prices double on 2027-01-01; Twilio NL
  rates are "current as of August 2026".
- **Currency:** most lists are in USD; the euro rate moves the result.
