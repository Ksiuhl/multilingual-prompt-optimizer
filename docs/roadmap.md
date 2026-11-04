# Roadmap

## Closeout status — 4 November 2026

The current investigation is closed. [Final conclusion and evidence](final-conclusion.md).
General incremental savings and a mixing-specific accuracy advantage were not established.
The repository remains an experimental research prototype; no profitable template is admitted.
No further paid experiments are scheduled. A clearer-English control, a verified second-model
replication and the agent-communication extension below are deferred possibilities, not active commitments.
The version stages below record implementation history and possible research directions.

## v0.6 practical direction

- Preserve originals by default; when compression is explicitly enabled, use English as the default candidate-generation and rule-search language.
- Keep multilingual mixing opt-in and experimental; compare it with a strong English baseline.
- Treat required output structure as part of task accuracy, including the outer JSON transport wrapper.
- Record complete preparation, verification, target response, retry and fallback costs when measurable.
- Keep unverified gateway results separate from direct-provider evidence; unknown prices remain unknown.
- Repeat on independently curated inputs and model-specific tokenizers before claiming general benefit.

The 50-input gateway study completed 300 answers across two model labels. It found
almost no incremental input saving from mixing beyond concise English, and some
strict wrapper failures in compressed GPT-labelled responses. The separate direct
Gemini 3.6 study remains incomplete at 14/150 successful requests because of a
daily free-tier quota. See [the recorded study](gateway-study.md).

## Working in version 0.1

- Local rule rewriting using an attributed upstream dependency.
- Candidate and phrase search against the complete composed prompt.
- Exact source-payload preservation, numeric/literal checks, and original fallback.
- CLI, Python API, synthetic corpora, reproducible benchmark commands, and tests.

## Historical version 0.2 development scope

- Version 0.2 added a local-model adapter and model-based semantic judging.
- Evaluate generation and judging with real models on unseen examples.
- Cache generated alternatives by input, model revision, and constraints.
- Meter candidate generation, verification, and search separately.
- Compare automatic generation methods under matched budgets.

## Research validation

Version 0.4 implements configured task-output checks and records a repeated
development experiment. Checked fallback recovered mixed-prompt losses but did not
outperform original prompts, and increased prompt usage and processing time.

- Add task-specific quality checks and repeated paired trials. The reviewer-approved
  65-token summary demo omitted a required date, so reviewer approval is insufficient.
- Independent semantic checks and hidden evaluation examples.
- Broader languages and prompt lengths, without tuning on the evaluation set.
- Target-model response checks and complete usage/cost accounting.
- Report failures, no-benefit cases, and uncertainty alongside improvements.

## Deferred master's research extension

Use the same evaluation framework for LLM-to-LLM communication. Start with ordinary
and concise language, then translation/mixing and structured messages. Shared
dictionaries or learned protocols are later hypotheses, not implemented features.
This would be a separate investigation; the Phase 1 findings do not validate its assumed savings.

Measure complete multi-agent task success and total communication cost, including
protocol setup, sender generation, receiver inputs, decoding, and retries.
