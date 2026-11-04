# Three-language accuracy controls: prepared follow-up

This targeted follow-up asks whether a mixed-language accuracy difference survives a Chinese-only control and additional boundary inputs. It does not change optimizer defaults or admit any compression template.

The prepared design contains 30 synthetic opaque-ID inputs across stock filtering, half-open interval overlap and latest-device-state selection. Every input receives concise English, Chinese-only and Chinese/English instructions, repeated three times. The English clauses retain the earlier concise baseline; mixing translates the first rule clause and keeps the second clause in English. SOURCE, literal field names and the JSON output contract stay identical.

Two model connections would require 540 target answers. Supplied connections are third-party gateway labels, not independently authenticated provider identities. Gemini returned an upstream HTTP 400 during semantic review, and Grok returned HTTP 403 `routes_paused`. A single bounded probe of the listed Gemini low variant also returned HTTP 400. The available GPT label is being tested separately; the two-model objective remains incomplete.

The GPT portion paused after 15 target requests when quota metadata returned HTTP 429 with `Retry-After: 1200`. No target accuracy was inspected. All returned answers were preserved, and remaining prompts were left unchanged. Recovery requires honoring that cooldown and verifying accounting before further inference. The recovery amendment reduces metadata polling to at most once per 90 additional requests; quota limits remain soft and may overshoot between checks.

Original preparation, the gateway amendment and the later recovery amendment are separate records. The gateway amendment explicitly replaces unavailable native-tokenizer matching and independent bilingual review with a descriptive local `o200k_base` subset and an automated review from the available target label. Twenty of 30 inputs have local maximum/minimum token counts within 10%; this is not model-native length matching. All 30 inputs remain primary.

The paired analysis aggregates repeats within each case and resamples whole cases within family, with 10,000 fixed-seed bootstrap draws. English and Chinese-only contrasts are exploratory; three selected templates, correlated reviews, repeated structures, provider-default sampling/reasoning, cache behavior and gateway identity uncertainty limit generalization. No output-based retries or prompt changes are allowed. Target-only quota is separate from review and failed setup overhead.

Scripts:

- `research/prepare_language_control.py`: deterministic fixtures, independently checked rule oracles and input hashes; no inference calls.
- `research/language_control_gateway.mjs`: explicit credential injection in memory, frozen review/target requests, complete attempts and soft quota checks. It refuses to overwrite a previous execution. Never put credentials in a published file.
- `research/analyze_language_control.py`: offline provenance, exact JSON answers, paired case-level analysis, quota reconciliation and graphs. It refuses to grade an unfinished target schedule.

The experiment is in progress. No accuracy or savings result is claimed in this methods note.
