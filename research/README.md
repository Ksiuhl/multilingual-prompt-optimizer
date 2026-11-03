# Reproduce the development studies

## Fresh-input paid follow-up (offline)

```bash
python research/analyze_fresh_cache.py results/fresh-cache-v060 --out results/local/fresh-cache-v060
```

This verifies all 120 frozen request identities/order, 20 new distinct inputs,
disjointness from prior corpora, exact answers and attributable charges. It
checks that the first 32 responses are unchanged against their saved prefix,
and records the declared meter-polling amendment and long resumption gap.
No model or billing calls are made. Read the [completed report](../docs/fresh-cache-followup.md)
for coverage, reconciliation and cache/timing limits. Earlier evidence and
admission decisions are unchanged.

## Small cache/retry follow-up (offline)

```bash
python research/analyze_cache_followup.py results/cache-followup-v060 --out results/local/cache-followup-v060
```

This verifies the frozen 24-request serial order, exact earlier prompts, raw
answer checks and all matched charges. It makes no model/billing calls. Cache
state was observed, not reset or controlled. The earlier extraction bundle is
required for identity checks. [Result and limits](../docs/cache-followup.md).

## Extraction cost audit (offline)

```bash
python research/audit_extraction_costs.py results/validated-extraction-v060 --out results/local/extraction-cost-audit
```

This audits all saved attempts, matched charges, cache metadata and local token
counts. It makes no inference or billing calls. The cached tiktoken encoding is
needed for a fully offline run. The 951-unit cost increase is unchanged; subset
and billing-fit calculations are descriptive diagnostics. [Findings](../docs/extraction-cost-audit.md).

## Scoped extraction admission (offline)

```bash
python research/analyze_validated_extraction.py results/validated-extraction-v060 --out results/local/validated-extraction-v060
```

This independently regrades the frozen primary run and separately frozen
uniqueness supplement, audits matching charges, counts distinct coverage, and
regenerates the admission evidence and graph. It makes no API calls. All answers
passed; the candidate was cost-rejected. [Methods and limits](../docs/validated-extraction.md).

The a3 application preserves originals by default. Research benchmark harnesses
explicitly enable compression for their experiments. Add `--enable-compression`
to `run_checked_case.py` or `run_cached_template.py` when testing rewrites. Offline
analyses below use frozen answers and graders, so the new policy does not alter
their scores. [Policy and migration](../docs/original-policy.md).

## Selected-failure reliability and charge audit (offline)

```bash
python research/analyze_reliability_v060.py results/reliability-v060 --out results/local/reliability-v060
```

This regrades 40 responses from five repeats of both arms on four selected known
failure cases. It checks identity with the earlier frozen prompts and cases,
then matches sanitized consumption-log records to response request IDs and
reconciles their sum with the key's interval quota debit. Neither credentials
nor network calls are needed. The earlier `results/heldout-v060/` bundle must
remain present. [Results and release decision](../docs/reliability-followup.md).

## Frozen new-input check (offline)

```bash
python research/analyze_heldout_v060.py results/heldout-v060 --out results/local/heldout-v060
```

This verifies the frozen dataset, candidate preparation, requests and grader,
then regrades the raw answers and generates comparison figures without API
calls. The study contains 50 newly authored inputs across ten new structured
task templates. EN/ZH/JA candidate clauses were written before target calls;
local `o200k_base` search chose identical English/mixed-policy prompts for all
50 inputs. This is a synthetic candidate-search check, with a proxy tokenizer,
rather than a test of automatic translation or authenticated provider models.

For a **new, separately recorded API execution**, set `GATEWAY_GPT_KEY` and
`GATEWAY_GEMINI_KEY` for the third-party `https://gpt-api.cc` service, then run:

```bash
node research/run_heldout_v060.mjs results/heldout-v060 results/local/new-heldout-run
```

This sends 150 frozen requests per route, with two concurrent requests per
route and up to two attempts per request for transport/server errors. The
published run is preserved. Keys stay in environment variables; no credentials
are needed for the offline analysis. Rates, availability and model identities
are properties of that gateway and are not verified by this repository.

## Output-contract regression (offline)

```bash
python research/analyze_output_contract.py
```

This verifies append-only prompt changes and regrades the 72 follow-up responses
using the original frozen rubric. It writes summaries and figures under
`results/local/output-contract-v060/` without any API calls. The six inputs were
selected from earlier format failures; this is targeted regression evidence, not
an independent accuracy benchmark. See [the protocol](../docs/output-contract-regression.md).

## v0.6 gateway study (offline)

After installing the package and `.[plots]`, run:

```bash
python research/analyze_gateway_study.py
```

No credentials or model calls are needed. The script verifies the exact frozen
rubric and prompt hashes, rechecks all 300 completed answers, and writes scores,
usage, latency, diagnostics and figures to `results/local/gateway-v060/`.
The gateway labels are not independently authenticated. Grok has no accuracy
score because its route was paused. See [the full protocol](../docs/gateway-study.md).

Earlier studies below retain their recorded versions and explicit language modes.

For the longer-template reuse study:

```bash
python research/evaluate_template_reuse.py --output results/local/template-reuse.json --cache-dir results/local/template-cache --refresh
python research/plot_template_reuse.py --input results/local/template-reuse.json --output-dir results/local/figures
python research/run_cached_template.py --study results/local/template-reuse.json --cache-dir results/local/template-cache --template code
```

Install `.[dev,plots]` and both local models first. Cache admission sees only the two
calibration inputs per template, never the ten test inputs. Fresh execution still
uses full-prompt recounting and task checks. Existing caches require `--refresh` for
a new measured preparation run. The graphs distinguish measured 1/10-use endpoints
from conditional 100/1,000-use projections; no higher-use accuracy is inferred.

For the later answer-validation experiment and graphs:

```bash
python -m pip install -e ".[dev,plots]"
python research/evaluate_task_quality.py --output results/local/task-quality.json
python research/plot_task_quality.py --input results/local/task-quality.json --output-dir results/local/figures
python research/run_checked_case.py --id F03 --output results/local/checked-demo.json
```

Use local Ollama with both Qwen3 models installed. The task fixture file fixes three
target repeats. Preparation is shared across repeats, fallback makes real extra
calls, and no invalid answer is released by the checked policy under its configured
oracle. Unsupported code syntax fails validation; model code is never executed.
The task-quality study documents the observed failures and limits.

From the repository root, install the package and pull both local models:

```bash
python -m pip install -e ".[dev]"
ollama pull qwen3:4b
ollama pull qwen3:8b
python research/evaluate_reviewers.py --output results/local/reviewer-comparison.json
python research/benchmark_automatic.py --reviewer-results results/local/reviewer-comparison.json --output results/local/automatic-benchmark.json
python research/check_summary_task.py --output results/local/summary-task-check.json
```

Run Ollama first. The scripts use the same local generation and review helpers as
the optimizer. They do not download models, use consumer chat websites or call
paid inference APIs. The documented local machine has 32 GB RAM and a 16 GB NVIDIA
GPU; model loading, performance and concurrent residency vary by hardware.

The reviewer set contains 20 assistant-authored development pairs, ten equivalent
and ten deliberately changed. Expected labels are withheld from model inputs.
One trial is recorded per pair/model. The selection rule is fixed in the script:
among models with no false approvals and no errors on this set, maximize correct
approvals; ties favor the first model. If neither qualifies, retain the first model
and record a warning. This small set is not an independent or held-out test.

The 30-task benchmark ignores the corpus's authored alternatives. It generates one
EN/ZH/JA clause pool per task, then compares English-only, the best monolingual
choice, and mixed combinations. Each arm gets up to eight fresh reviewing calls
and includes the original as fallback. PromptMin rules are excluded to isolate
candidate search. Generation is shared during the experiment; summaries charge it
once per arm to describe a hypothetical standalone execution.

English-only uses the English wording produced alongside translations. It is not
an independently tuned English compression system. Local generator and reviewer
counts are not the `o200k_base` target-content counts. Do not subtract these token
units or turn them into monetary savings. Target task accuracy and API bills are
not measured by this runner. Model approval alone is insufficient accuracy evidence.

Reports are saved after each completed task/model. `complete=false` denotes an
interrupted experiment. Model generation or review errors retain the original and
are reported. Fixed arm order, warm-up, caching and inference nondeterminism can
affect results, including at temperature zero. Preserve repeats and no-benefit cases.

The summary checker runs one paired target-task example with six specific
fact/format checks. It exits with code 1 when a check fails and still saves the
responses. In the checked-in development run, compression omitted the review date.
Do not rerun until a pass and discard the failure. Repeat paired trials under a
declared protocol for a useful quality estimate.

See `docs/reviewer-study.md` for the checked-in results and interpretation.
