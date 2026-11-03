# Proposal to SaaS-OS: streaming inference and real-time audio for voice agents

**Status:** a technical proposal for review, prepared on 2026-11-03 under
the owner's decision P15-V point 6 ("Prepare the technical proposal for
streaming audio and real-time AI interactions. Do not change SaaS-OS, its
release or LeadStack's dependency pin."). It is written for the SaaS-OS
maintainers. Nothing changes in this repository because of it: the pin stays
at v0.6.0 (`d980e73b0313ed63f2a59fd4a991a89f75791c0e`), and SaaS-OS is not
edited, forked or released from here. Product context:
`VOICE-AGENTS-BRIEF.md` §6. Companion: `SAAS-OS-GET-PROPOSAL.md`.

## 1. Why

LeadStack's voice agents (roadmap workstream 15V) must keep every LLM turn
inside SaaS-OS governed inference (authority, data classification,
eligibility, admission, attempt evidence, usage). A phone conversation needs
the first words of a reply within about a second. In v0.6.0:

- `stream_inference` refuses every request (`streaming_not_enabled`);
- the inference egress has no time-to-first-event limit; the read-inactivity
  candidate is 30 s and the total deadline 120 s;
- there is no governed path for audio (speech recognition, speech
  synthesis, speech-to-speech);
- egress is HTTP POST only (no GET, no WebSocket);
- there is no object storage in the public surface.

Without streaming, a voice turn waits for the whole reply, which forces very
short answers and still risks noticeable pauses. Without governed audio, the
audio leg must stay with a hosted voice platform outside SaaS-OS, which is
LeadStack's recommended first path anyway (option A in the brief).

## 2. Verified state at the pin

Read in the pinned package and in SaaS-OS's own documents at the pinned
commit:

- `docs/architecture/AI-INFERENCE-CONTRACTS.md` §6 already specifies
  `stream_inference` as an async context manager yielding `TextDelta`,
  `ToolCallDelta`, `UsageUpdate` and `StreamCompleted`, with lifecycle,
  partial-output, disconnect, usage and logging rules (§6.1–6.5), and six
  release criteria (§6.6).
- `docs/AI-INFERENCE-ROADMAP.md`: streaming is deferred behind a "streaming
  gate (inside AI-D, separately authorized)".
- ADR-0054 §8a: "Latency-sensitive use cases (voice, interactive
  completion) may need tighter limits, in particular a time-to-first-token
  or first-event deadline" (open question Q3).
- The adapters (`openai_compatible`, `anthropic_messages`,
  `gemini_generate_content`) are non-streaming; the attempt ledger already
  has a `streamed` column; `InferenceStreamInterruptedError` exists.
- `core.usage` accepts any metric string, so voice minutes, characters and
  calls can be metered without a SaaS-OS change.

## 3. Request A: enable `stream_inference` (as already designed)

LeadStack asks SaaS-OS to complete its own streaming gate, unchanged in
substance:

1. Meet the six release criteria of contracts §6.6: conformance for both
   adapters including abrupt close and malformed events; the connection
   closed on break, exception, cancellation and each deadline; no retry or
   fallback after the first delta; correct ledger rows and usage exactly
   once; open streams counted by the per-tenant concurrency limit; the
   canary-credential test on streaming error paths.
2. **Settle Q3 for voice:** a per-use-case first-event deadline (proposed
   for a `voice.turn` use case: 1.5 s, configurable per deployment, never
   above the installation maximum) and a short maximum lifetime (proposed:
   30 s for a voice turn).
3. **Cancellation on interruption:** when the caller speaks over the agent,
   LeadStack leaves the `async with`; §6.3 already finalises the attempt as
   interrupted. Please confirm that usage is settled exactly once in that
   path (criterion 4 covers it) and that a caller cancellation does not
   count as a provider failure for the circuit breaker.
4. **Tool-call deltas:** voice agents call tools (book an appointment,
   transfer). `ToolCallDelta` is in the contract; the request is that the
   streaming adapters emit complete, validated tool calls before
   `StreamCompleted`, so a product never acts on a partial call.

LeadStack's side, after a release that has it: switch the turn endpoint
from `run_inference` to `stream_inference` and forward text deltas to the
voice platform as they arrive. Each step needs the owner's approval of the
pin move first.

## 4. Request B: governed audio (optional, for a LeadStack-run pipeline)

Only needed if LeadStack later runs its own audio pipeline (option C in the
brief) instead of a hosted voice platform. Offered as a design for
discussion, not as a request to build now.

### 4.1 Interfaces (a sketch; the maintainers' design governs)

```python
async with transcribe_stream(caller, tenant_id=..., request=TranscribeRequest(
        alias="default-stt", use_case="voice.listen", language="nl-NL",
        sample_rate=8000, encoding="mulaw")) as session:
    await session.send_audio(chunk)          # bytes
    async for event in session:              # PartialTranscript | FinalTranscript | UsageUpdate | Completed
        ...

async with synthesize_stream(caller, tenant_id=..., request=SynthesizeRequest(
        alias="default-tts", use_case="voice.speak", voice="nl-NL-standard-1",
        text_source=...)) as session:
    async for event in session:              # AudioChunk | UsageUpdate | Completed
        ...
```

### 4.2 Guarantees, by analogy with governed text inference

- The same authority, classification (audio and transcripts are
  `tenant_data` and personal data), eligibility, admission and attempt
  evidence as text inference; provider and model aliases configured by
  platform operations only.
- **Destination policy per data class:** audio may go only to providers
  marked eligible for personal voice data in the deployment's region (the
  EU for LeadStack), with the processor agreement recorded in
  configuration.
- **Usage units:** seconds of audio received, characters synthesised,
  sessions; reported as `core.usage` events exactly once per session.
- **Limits:** maximum session length, maximum bytes in and out, an idle
  timeout, concurrent sessions per tenant.
- **No storage:** SaaS-OS never persists audio; the product decides what to
  keep (LeadStack's default is no recording, decision P15-V point 7).
- **Logging:** no audio and no transcript text; counts, durations, codes.

### 4.3 Egress for streaming providers

Speech providers stream over WebSocket or HTTP/2. This needs a
`StrictEgressClient` WebSocket (and, separately, the GET of
`SAAS-OS-GET-PROPOSAL.md`) with the same guarantees as POST: the
destination allowlist, address validation, TLS required, the proxy tunnel
(ADR-0059), no redirects, frame and total byte caps, idle and lifetime
deadlines.

## 5. Request C: inbound media streams (only for option C)

Telephony providers deliver call audio by connecting **to** the product
(for example one WebSocket per call). SaaS-OS offers no such ingress today.
If it ever does, it needs per-tenant authentication of the provider's
connection (a signed token issued when the call is set up, bound to one
call and expiring quickly), the edge's size and rate limits, and routing to
the product without the tenant being taken from the URL. Until then
LeadStack keeps audio with a hosted voice platform.

## 6. Priorities

| Request | Value for LeadStack | Needed for |
| --- | --- | --- |
| A. `stream_inference` with a voice first-event deadline | High: natural turn latency with full governance | Slice V2 onwards, if latency without streaming proves too high (measured in V2) |
| GET egress (`SAAS-OS-GET-PROPOSAL.md`) | Medium: fetch transcripts and call details from the voice platform | Slice V3 |
| B. Governed audio and WebSocket egress | Low now: only for a LeadStack-run pipeline | Option C, if ever chosen |
| C. Inbound media streams | Low now | Option C, if ever chosen |

## 7. What LeadStack does meanwhile

- Builds and tests nothing for voice until the owner authorises a slice.
- When a slice is authorised, measures turn latency with `run_inference` in
  a sandbox (slice V2) before asking for Request A to be prioritised.
- Meters voice usage with `core.usage` metrics it can already record
  (`voice_minutes_inbound`, `voice_minutes_outbound`, `voice_calls`), with
  no SaaS-OS change.

## 8. Reversibility

Every request is additive: `run_inference` and `post` keep their current
behaviour, and LeadStack can switch between non-streaming and streaming
turns by configuration.
