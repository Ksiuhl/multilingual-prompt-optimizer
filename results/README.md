# Checked-in local results

Current reports and graphs display gateway quota units and percentage changes,
not money or official-provider prices. Frozen machine records retain their
original gateway-supplied currency labels and legacy conversion fields solely
for reproducibility; those fields are not used as financial results.

## Small cache/retry follow-up

`cache-followup-v060/` freezes four known cases, three repeats per arm, balanced
serial request order, all receipts, paired spend checks and matching charges.
All 24 responses passed; every response reported 4,224 cached input tokens, with
no retries. Compressed charges were 6.06% lower. Total matched debit was 5,797
quota units. This selected-case diagnostic
does not replace the prior cost failure or admit a template. See
[the report](../docs/cache-followup.md), `cache-followup-v060-summary.json` and
`figures/v060-cache-followup-*`.

## Offline extraction cost audit

`extraction-cost-audit-{summary,attempts,billing-fit}.json` retains the descriptive
audit of all 69 saved attempts. The exact observed cost gap decomposes to
-629 units on the other 31 successful pairs, +1,185 on the exceptional pair, and
+395 on five timeouts. No observations are removed from the primary result and
the template remains rejected. The cache explanation is inferred, not verified
upstream cache state. See [the report](../docs/extraction-cost-audit.md) and
`figures/v060-extraction-cost-audit-*` graphs and provenance.

## Scoped extraction admission (0.6.0a4)

`validated-extraction-v060/` retains the frozen 60-trial primary corpus and a
separately frozen four-trial supplement correcting distinct holdout coverage.
All original observations remain included: 10 distinct development payloads and
20 distinct holdout payloads across 64 trials. Every completed answer passed.
The candidate was rejected because development costs rose. Matching charged
quota reconciled to 16,787 units.
The evidence artifact remains rejected; no template was enabled by these results.
See [the audit and graph](../docs/validated-extraction.md).

## Selected-failure reliability follow-up (0.6.0a2)

`reliability-v060/` freezes four known content-failure cases, exact original and
English prompts, five repetitions per arm, the unchanged grader, and all 40 raw
responses. It also retains sanitized request-matched charge logs and a usage
counter delta. No account balances, lifetime totals, names or unrelated logs are
included. All 40 responses completed with no retries.

The follow-up passed 15/20 original versus 11/20 English checks. Six unchanged
prompt groups varied in correctness. English's matched gateway quota consumption
was 0.88% lower; the combined debit was 9,520 quota units. This is selected-case diagnosis,
not a new independent accuracy benchmark. Keep the default-policy proposal
unmerged. See [the report](../docs/reliability-followup.md),
`reliability-v060-summary.json` and `figures/v060-reliability-comparison.*`.
Earlier study scores remain unchanged.

## Frozen new-input candidate-search check (0.6.0a2)

`heldout-v060/` contains the exact frozen inputs, candidate search receipts,
requests, grader, runner, execution recovery notes, public-price snapshot and
306 API-attempt receipts. The 300 planned trials produced 299 completed answers.
Five completed GPT-labelled answers had content errors; one original request was
interrupted. No scores or prompts were repaired after target outputs.

`heldout-v060-summary.json` separates planned-trial scores, completed-answer
scores, transport failures, common-input usage, retry-inclusive latency and
explicit price scenarios. Actual billed cost is unknown. The full-prompt local
reduction is 10.27%; English and mixed policy sent identical prompts on all
50 inputs. Their differing answer scores are not a language treatment effect.
See [the report](../docs/heldout-study.md) and
`figures/v060-heldout-comparison.*`. Earlier studies remain unchanged.

## Explicit output-contract regression (0.6.0a2)

`output-contract-v060-*` retains the fixed protocol, append-only prompts, raw
receipts and summaries for 72 follow-up answers. All passed the unchanged strict
checks, including the outer `answer` wrapper. Six known problem inputs were reused
twice per arm/model; these are not 72 independent questions. Earlier study scores
remain unchanged. Contract text adds input overhead and is counted. See
[the regression protocol](../docs/output-contract-regression.md) and the
`figures/v060-output-contract-comparison.*` graphs.

## Recorded gateway transfer study (0.6.0a1)

`gateway-v060-summary.json` contains primary strict scores and separately labelled
diagnostics. The gzip raw and preparation files retain successful, failed and
discarded attempts without credentials. `gateway-v060-requests.json` retains the
exact frozen prompt strings. Graphs are in `figures/v060-gateway-comparison.*`.

Two gateway labels completed 150 answers each; Grok returned 403 and has no score.
Mixing added only five Gemini-labelled input-token savings beyond concise English.
Most mixed-policy templates are entirely English; GPT-labelled input accounting
varied on six identical prompt pairs. Actual billed cost and model identities are
unverified. [Protocol, uncertainty and offline reproduction](../docs/gateway-study.md).

## Template reuse (0.5.0)

`template-reuse-v050.json` records four longer templates with two calibration and
ten fresh test inputs each. No shortened template was admitted, so all 40 test
prompts per policy were originals and all policies attempted 12,242 content tokens.
The 1/10-use endpoints are measured; 100/1,000-use endpoints are conditional
projections without accuracy forecasts. See `docs/template-reuse-study.md` and the
`v050-*` PNG/SVG/PDF figures. No cache-induced quality, token or time advantage is
claimed from identical-prompt answer/timing variation.

## Task-answer validation (0.4.0)

`task-quality-v040.json` records 20 fixtures × 3 repeats. Original passed 33/60,
English-only 31/60, mixed 27/60, and checked mixed 33/60 configured task checks.
Checked mixed used 21 extra original fallback calls and returned no validated answer on 27 requests;
it attempted 22.8% more content tokens than original. Baseline arithmetic and a code
service error are retained as failures. See `docs/task-quality-study.md` and
`results/figures/` for measured PNG/SVG/PDF charts and provenance. No net-cost or
general-accuracy advantage is demonstrated.

## Reviewer and automatic-search study (0.3.0)

The 20-pair synthetic reviewer comparison is in `reviewer-comparison.json`. Qwen3
8B matched all 20 development labels; 4B matched 10, rejecting all equivalent cases.
This is a small model-selection set, not independent validation.

Two 30-task runs are retained in `automatic-benchmark-first-run.json` and
`automatic-benchmark.json`. They ignore authored alternatives and use local-model
generation. Mixed search saved 19–24 content tokens beyond English-only and 17
beyond single-language search, with additional review overhead. No task accuracy
or monetary advantage was demonstrated. See `docs/reviewer-study.md` for full
methodology, timing, usage and limitations, and `research/README.md` to reproduce.

The separate `live-summary-8b-review.json` / `live-summary-8b-task-check.json` pair
records 69 to 65 content tokens but a missing review date in the compressed task
output. It is a retained quality failure, not a successful accuracy benchmark.

## Live local-model development check (0.2.1)

`live-summary-ollama.json` records automatic Qwen3 4B generation and review using
Ollama 0.40.13. All shorter candidates were rejected, so the original was retained:
69 to 69 `o200k_base` content tokens (zero savings). The warm run took about 2.85
seconds, with seven generation/review calls totaling 1,549 local-model input tokens
and 427 output tokens. This overhead saved no target-input tokens in this example.

`live-summary-task-check.json` contains paired target-model responses and six
specific format/fact checks, all passing. Because the selected prompt was unchanged,
these results do not show that compression preserves accuracy. The example and
review prompts were used during development, not held out. See
`docs/automatic-mode.md` for the response-limit fix and model-review limitations.

## Earlier selector benchmark (0.1.0)

Generated from the installed version 0.1.0 package on 3 November 2026 using
`o200k_base` and the commands in the main README.

| Corpus | Items | Original | Automatic rules | Supplied search | Combined pool |
| --- | ---: | ---: | ---: | ---: | ---: |
| Synthetic EN/ZH development | 30 | 1,574 | 1,573 | 1,378 | 1,378 |
| Spanish technical coverage | 6 | 330 | 294 | 228 | 228 |

Numbers are sums of complete user-message content tokens. Every method can fall
back to the original. The automatic pool combines PromptMin's lite and translation
modes; this differs from the earlier translation-only reproduction described in
`docs/research.md`. Supplied search uses alternatives authored in advance. It is
not an equally automated translation system or an independent evaluation set.

The detailed JSON records include rejected candidates, library versions, selection
labels, and local optimization elapsed time. Timing depends on the machine and
cache; it excludes candidate authoring, target-model inference and network time.
These files contain no measured task accuracy, API bills, or end-to-end latency.

Local release checks: 26 tests passed on Windows/Python 3.12, dependency consistency
passed, lint passed, and source/wheel distributions built successfully. GitHub's
Windows/Linux CI matrix is configured but has not run on GitHub yet.
