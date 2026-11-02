# Project brief

## Aim

Tokenizer-Aware Multilingual Prompt Compression studies whether equivalent
instructions can be represented more efficiently across languages. The unit of
optimization is the complete prompt sent to the target model.

Phase 1 is a user-to-LLM optimizer. Its success requires preserving task quality
and reducing total processing cost after generation and validation overhead.
Phase 2, planned for master's research, extends the same question to communication
between LLMs or agents, and potentially learned shared protocols.

## Research questions

- Does mixing languages improve on concise English and the best single language?
- How do the preferred representations differ across GPT, Qwen and Llama tokenizers?
- Which task types lose meaning or accuracy after compression?
- When do generation, verification and output costs outweigh input-token savings?
- Do reusable alternatives or cached translations improve the break-even point?

## Version 0.1 scope

The current MVP is a local candidate selector and benchmark tool. It provides
automatic rule-based candidates and accepts authored translations or reformulations.
It searches bounded combinations and keeps the shortest structurally acceptable
complete prompt. It preserves a separate source payload exactly.

Automatic multilingual generation, independent semantic validation, model-response
evaluation, latency measurement across services and API billing are future work.
Morse code is excluded from the current scope.

## Architecture

1. Read and validate the instruction, immutable payload, output instruction and
   optional constraints.
2. Generate rule candidates through the credited PromptMin dependency and combine
   supplied phrase alternatives within a fixed search budget.
3. Compose each complete prompt with the unchanged payload and output instruction.
4. Count with the selected tokenizer and reject growth or protected-string loss.
5. Select the minimum count, keeping the original on a tie.
6. Emit the prompt and an auditable record of counts, decisions and limitations.

`models.py` defines the input/output contract; `rules.py` wraps the upstream rules;
`tokenizers.py` supplies counting adapters; `core.py` searches and selects; `cli.py`
provides optimization and corpus benchmarking commands.

## Experiment design

Compare original prompts, concise English, single-language translations, mixed
language search and an automatic rule baseline on the same tasks. Count complete
messages with each target tokenizer. Separate development data from unseen
evaluation examples, and compare generators under matched budgets.

Measure task accuracy, constraint adherence, translation/verification overhead,
target input and output usage, retries, total latency and total cost. Report
no-benefit cases and failures. See the research notes and roadmap for current
evidence and the next implementation stages.
