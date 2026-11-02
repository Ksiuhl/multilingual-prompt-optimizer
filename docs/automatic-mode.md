# Automatic multilingual mode (0.2)

The new module `automatic.py` provides `OllamaModel` and `auto_optimize`. It adds
candidate generation and judging to the existing tokenizer search. It requires a
running Ollama service and an installed local multilingual model. The program does
not install Ollama or download model weights itself.

## Run

After the normal Python installation and Ollama setup:

```bash
ollama pull qwen3:4b
mpo auto --input examples/automatic.json --model qwen3:4b --output results/local/auto.json
```

The model example is from the official [Ollama model library](https://ollama.com/library/qwen3:4b).
Its listed download size is approximately 2.5 GB. It is an example setup choice,
not a measured winner for this project. Use `ollama list` to find installed models.

The integration uses [Ollama's structured generation endpoint](https://docs.ollama.com/api/generate).
It requests JSON schemas, non-streamed output and deterministic temperature. It
uses `think=false`, so choose a model supporting non-thinking operation. Reported
input/output counts describe the local generator/judge model, not the target
tokenizer or a target provider's billed tokens.

## Sequence

1. Ask the generator to split the complete instruction into equivalent clauses in
   each requested language. Clause count is bounded before generation.
2. Validate the returned JSON, language coverage and combination budget. Do not
   silently truncate away instruction clauses.
3. Search all generated combinations, plus rule and supplied complete candidates,
   counting complete prompts and enforcing numeric/literal guards.
4. Judge distinct shorter candidates in ascending token count. The default budget
   is eight judging calls. A shorter candidate can still omit meaning, so token
   count alone is insufficient.
5. Select the first approved candidate; otherwise return the original. Reject
   candidates not reviewed within budget. On connection/schema/judging errors,
   return the original with an error report.

The default languages are `en,zh,ja`; supported codes also include `es,fr,de,ko`.
Use `--languages en,zh,es`, `--verification-budget 4`, `--timeout 120`, or
`--ollama-url http://127.0.0.1:11434` to adjust configuration. At most four languages,
eight clauses and 32 judging calls are allowed. The default search budget remains
256 combinations. Search is exhaustive within the generated pool, not across all
possible translations of a language.

Only the instruction, protected literals and unchanged output constraint go to
Ollama; the source payload is preserved and excluded from generation/judging
requests. Keep documents and code in `payload`. A custom local Ollama installation
must itself be configured to use local inference.

## Meaning and accuracy limits

The judge checks requirements, negation, quantities, entities, formatting, scope and
tone, and is instructed to reject uncertainty. This is a fallible model opinion.
The same model is used by default in separate calls; a different installed model
can be selected with `--verifier-model`. Shared biases and instruction injection
remain possible. Language labels and semantic equivalence are not independently
certified. Some instructions will produce no useful compression.

The result intentionally keeps `semantic_equivalence_verified=false`; the
`automation` report separately states whether the judge approved a candidate.
Actual task accuracy requires target-model responses and independent scoring.
The model is not used to execute the user's target task here.

## Validation of this release

The 41-test suite includes deterministic model doubles and a real loopback HTTP
test server. It checks response format, usage recording, ranking, preservation,
judge rejection, malformed outputs, offline behavior and bounded validation.
Those automated tests do not evaluate actual model translations. A separate live
development check was then run with Ollama 0.40.13 and Qwen3 4B Q4_K_M on an NVIDIA
RTX 5070 Ti. The first attempt reached the review response limit; version 0.2.1
bounds review explanations and rejects truncated responses explicitly.

The final summary example generated multilingual clauses but the model reviewer
rejected all shorter candidates, including some on superficial wording/language
grounds. The original was retained: 69 original and 69 selected `o200k_base`
content tokens. Task checks for three bullets and the supplied dates/counts passed,
but the selected prompt was unchanged. This gives no evidence of accuracy under
compression or total-cost savings. See the checked-in live development records in
`results/live-summary-ollama.json` and `results/live-summary-task-check.json`.

The generator/reviewer instructions were adjusted during this development check,
so it is not a held-out evaluation. The model judge remains overly conservative
in this example. Broader real-model quality and end-to-end savings are unmeasured.

Generation and review can require up to nine inference calls by default. Local
model elapsed time and available token counts are recorded per call, with overall
optimization elapsed time. There is no monetary cost estimate, target-task latency
or hidden accuracy score. The existing authored development benchmarks remain
historical results of the earlier selector, not evidence for the new generator.
