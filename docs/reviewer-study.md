# Reviewer development study and automatic benchmark (0.3.0)

The larger reviewer improved decisions on a small synthetic set. Automatic mixed
search then reduced target-content tokens, but its marginal benefit was small and
required additional inference. These experiments do not establish task accuracy,
general semantic reliability, novelty or net monetary savings.

## Reviewer comparison

`data/reviewer-development.json` contains ten task templates, each with an
equivalent rewrite and a deliberately changed rewrite. Examples cover output
counts, output-only requirements, translation language, numeric thresholds, null
values, negation, empty-input behavior, exact strings and AND/OR logic. The
assistant authored the cases and labels; they have no independent bilingual review.

The production review prompt was frozen before this comparison. Both models used
that same prompt, JSON schema, non-thinking mode and temperature zero. Expected
labels were not sent to either model. One trial was recorded per pair/model.

| Reviewer | Equivalent accepted / 10 | Changed rejected / 10 | False approvals | Errors | Correct / 20 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qwen3 4B Q4_K_M | 0 | 10 | 0 | 0 | 10 |
| Qwen3 8B Q4_K_M | 10 | 10 | 0 | 0 | 20 |

The predetermined selection rule first required zero false approvals and zero
errors on this set, then preferred more correct approvals, with ties favoring the
smaller model. It selected Qwen3 8B. This is model selection on development data,
not a held-out estimate. Ten successful negative cases cannot establish safety
against meaning changes generally.

Raw decisions, reasons, call usage, model digests and the review-protocol fingerprint
are in `results/reviewer-comparison.json`.

## Thirty-task automatic comparison

The earlier 15-English/15-Chinese development corpus was reused. Its authored
alternatives were discarded. Qwen3 4B generated one aligned English/Chinese/Japanese
clause pool per task. Qwen3 8B reviewed candidates. Complete prompts, including the
unchanged payload and output constraint, were counted using `o200k_base`.

Each arm retained the original as fallback and received up to eight fresh review
calls. English-only used the English clauses in the generated pool. Single-language
search compared the three complete monolingual instructions. Mixed search examined
all clause combinations, up to 256. PromptMin rules were excluded from these arms.
Each standalone-arm timing/usage summary includes shared generation once; generation
was only performed once per task during the actual experiment.

Two development runs are retained. The first used the initial source layout; the
second was made after formatting so the generator source fingerprint matched the
published source. Prompt content and experiment settings were unchanged. Results
varied despite temperature zero, so neither run should be presented as an exact
deterministic prediction. The first report's raw generator source hash reflects the
earlier whitespace layout. Both review-protocol fingerprints match the final code.

| Content-token total across 30 tasks | First run | Final-source run |
| --- | ---: | ---: |
| Original | 1,574 | 1,574 |
| Generated English-only | 1,470 | 1,472 |
| Best reviewed single language | 1,468 | 1,465 |
| Reviewed mixed search | 1,451 | 1,448 |
| Mixed saving beyond English-only | 19 (1.29%) | 24 (1.63%) |
| Mixed saving beyond single-language search | 17 (1.16%) | 17 (1.16%) |

Mixed search saved 7.81–8.01% against the original across these two runs. That is
content-token reduction, not a measured API discount or independent quality score.
Most of the reduction was already available in concise single-language wording.

## Overhead and limitations

For the final-source run:

| Arm | Review calls | Generator + reviewer input tokens | Generator + reviewer output tokens | Time including generation, all 30 tasks |
| --- | ---: | ---: | ---: | ---: |
| English-only | 22 | 11,289 | 5,833 | 33.59 s |
| Single language | 26 | 12,236 | 5,956 | 34.51 s |
| Mixed search | 43 | 16,299 | 6,485 | 39.00 s |

These local-model token counts use Qwen's tokenizer; the prompt totals above use
`o200k_base`. They cannot be subtracted as interchangeable billing units. The local
compute and extra reviews saved only 17 target-content tokens beyond single-language
search. No total-cost advantage was demonstrated. Reusable or cached alternatives
could change the economics, but are not evaluated here.

There were no generation/review errors in either 30-task run. This does not imply
that all selected instructions preserve meaning. Target-task responses and accuracy
were not evaluated in this benchmark. Model judging is fallible, and the reviewer
selection set is small and partly overlaps the benchmark's task types. English-only
was drawn from multilingual generation, not an independently tuned English prompt
compressor. Actual call counts differ despite matched maximum review budgets.
Timings include warm-up/cache effects and a fixed arm order, not repeated timing
trials. No API billing, power use or monetary costs were measured.

The experiments used Ollama 0.40.13, a local NVIDIA RTX 5070 Ti, and the model digests
in the reports. Runtime provenance for these existing reports was captured after
the experiments; reproduction scripts capture it before new runs.

## Reproduce and continue

One separate paired summary check used the documented 4B-generator/8B-reviewer
configuration. It selected a 65-token prompt instead of the 69-token original.
The original task response passed all six fact/format checks; the compressed task
response passed five, omitting the review date (9 November 2026). The reviewer had
approved the rewritten instruction. Records are in `results/live-summary-8b-review.json`
and `results/live-summary-8b-task-check.json`.

This is a concrete task-quality failure observation, not a general accuracy rate.
There was one run per condition, so it cannot establish that compression caused the
difference rather than inference variation. It nevertheless prevents claiming that
the observed token reduction preserves task accuracy. A model-equivalence judgment
and a successful engineering test suite are not substitutes for target-task checks.

See `research/README.md` for commands. Full traces are in
`results/automatic-benchmark-first-run.json` and `results/automatic-benchmark.json`.
Use fresh task instances and independently reviewed semantic labels for the next
evaluation. Freeze settings before examining those results. Compare against a
dedicated concise-English generator and score target-model task outputs, including
failure cases, generation overhead, retries, latency and applicable total cost.
