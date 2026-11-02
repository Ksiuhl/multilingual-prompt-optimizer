# Roadmap

## Working in version 0.1

- Local rule rewriting using an attributed upstream dependency.
- Candidate and phrase search against the complete composed prompt.
- Exact source-payload preservation, numeric/literal checks, and original fallback.
- CLI, Python API, synthetic corpora, reproducible benchmark commands, and tests.

## Next development stage

- Version 0.2 adds a local-model adapter and model-based semantic judging.
- Evaluate generation and judging with real models on unseen examples.
- Cache generated alternatives by input, model revision, and constraints.
- Meter candidate generation, verification, and search separately.
- Compare automatic generation methods under matched budgets.

## Research validation

- Independent semantic checks and hidden evaluation examples.
- Broader languages and prompt lengths, without tuning on the evaluation set.
- Target-model response checks and complete usage/cost accounting.
- Report failures, no-benefit cases, and uncertainty alongside improvements.

## Planned masters research extension

Use the same evaluation framework for LLM-to-LLM communication. Start with ordinary
and concise language, then translation/mixing and structured messages. Shared
dictionaries or learned protocols are later hypotheses, not implemented features.

Measure complete multi-agent task success and total communication cost, including
protocol setup, sender generation, receiver inputs, decoding, and retries.
