# Fresh-input paid quota/cache study: completed after resumption

**All 120 planned requests are now recorded.** The remaining 88 were sent in the
original frozen order after the user requested completion of the stopped run.
The first 32 results were retained unchanged and are verified against a saved,
hashed prefix. There are **20 distinct new payloads**, each tested three times
with both existing prompt versions. This is one JSON projection schema, not
60 independent questions or a general multilingual benchmark.

| Arm | Exact passes / 60 planned | Completed responses | HTTP attempts | Reported input tokens | Reported output tokens |
|---|---:|---:|---:|---:|---:|
| Original | 60/60 | 60 | 60 | 283,473 | 2,131 |
| Compressed | 60/60 | 60 | 60 | 279,633 | 2,108 |

Reported input usage was **1.35% lower** with compression.
All first repetitions and retries are included. There were 0
incomplete HTTP attempts; answer-quality errors among completed responses were
0 original and 0 compressed. Unsent requests: **0**.

All saved attempt charges reconcile with the whole-study key-counter increase: **29,819 gateway quota units**. Compressed charges were **5.90% lower** (15,363 original versus 14,456 compressed). These are observed gateway quota units, not independently audited upstream prices.

For transparency about the pause, the recovered ledger separates the initial
16 pairs from the resumed 44 pairs:

| Segment | Pairs | Original known quota | Compressed known quota |
|---|---:|---:|---:|
| Initial | 16 | 4,090 | 3,868 |
| Resumed | 44 | 11,273 | 10,588 |

These are descriptive ledger groupings, not independent experiments or controlled
cache treatments. Coverage status is recorded for each segment in the summary.

Median client request time, including retry waits, was
2.82 seconds original and
2.60 seconds compressed. Timing
excludes pauses between request pairs and is descriptive only.

| Repetition | Original exact passes / 20 planned | Compressed exact passes / 20 planned |
|---|---:|---:|
| 1 | 20/20 | 20/20 |
| 2 | 20/20 | 20/20 |
| 3 | 20/20 | 20/20 |

## Cache, ordering and repeat observations

Full planned order was preserved: ten original-first and ten compressed-first
pairs per repetition (30 each overall). Repetition two reverses each case's
first arm from repetition one. There were 47/60 pairs
with equal known reported cache counts. Cache categories are:

| Arm | Positive reported cache | Reported zero | Unknown |
|---|---:|---:|---:|
| Original | 60 | 0 | 0 |
| Compressed | 60 | 0 | 0 |

There were 0 case/arm groups with
varying correctness across their three repetitions. Pair differences and
first-arm groupings in the summary are descriptive observations, not causal
evidence about cache, request order or latency. Unknown cache fields are not
treated as zero.

![Observed cache counts, all matched charges and exact answers](../results/figures/v060-fresh-cache-comparison.png)

## Frozen design and declared resumption amendment

Before the initial inference, `protocol.json` froze the dataset, all 120 full
prompt strings, expected answers, grader, template and runner by SHA-256.
Canonical payloads are distinct and disjoint from the earlier extraction study,
its uniqueness supplement and the four-input cache follow-up. Expected answers
were independently assembled and cross-checked against deterministic projection.
Inputs cover multilingual names, whitespace and escapes, missing paths, nulls,
empty strings, booleans, numeric strings and numbers, with archived values and
instruction-like source notes as distractors.

The instructions and immutable output contract were reused exactly. There was
no new candidate generation, translation, tuning, answer repair or judging call.
Only the preplanned target requests and their bounded retries were sent. The
unverified `gpt-6.1-sol` gateway label used default sampling/reasoning, streaming,
a 4096-token output cap, serial concurrency, a 60-second deadline and at most
two attempts for transient failures.

The original execution stopped at 32 responses when quota metadata persistently
returned HTTP 429. The partial answer checks had already been graded and
published before the user requested resumption. `resume-amendment.json` records
that fact and was written before request 33. This continuation is not a newly
blinded or independent study. Candidate wording, expected answers, grader,
request order and model configuration did not change.

**Operational amendment:** the original plan checked the quota meter after every
pair; the resumed segment checked after each ten pairs (20 requests), a final
shorter batch, and before resumption. The same whole-study 75,000-unit soft stop
remained, using the original baseline. This was not a guaranteed ceiling, and
more calls could occur between checks. Metadata retries did not rerun inference.
No alternate key was used to work around limits.

The pause after request 32 lasted approximately 14.3 minutes and can alter cache state, server load and timing, including
the rest of repetition one. There was no cache reset, cache busting or free
warm-up; the first repetition is not called cold. `partial-*.json` preserves the
stopped-run snapshots, and `resume-prefix-results.json.gz` preserves all original
32 response/attempt records. The analyzer verifies prefix identity and amendment
hashes. The [original partial report](https://github.com/Ksiuhl/multilingual-prompt-optimizer/blob/d87c0275f4a705497bafd2f26b76a1d64fb19c0e/docs/fresh-cache-followup.md)
remains in Git history.

## Interpretation and reproduction

This is controlled compression/accounting research; the projection itself can
be computed locally without an LLM. Gateway model identity, cache metadata and
accounting are not independently authenticated. No significance test or
confidence interval is claimed. The descriptive analysis plan was written after
initial inference began, before the first grading, and extended to verify the
declared continuation. Results do not establish a multilingual advantage,
replace prior negative studies, admit the rejected template, or change
original-only defaults. Manual authoring time and deployment overhead were not
measured, so API quota reduction is not an end-to-end production-profitability claim.

```bash
python -m pip install -e ".[dev,plots]"
python research/analyze_fresh_cache.py results/fresh-cache-v060 --out results/local/fresh-cache-v060
```

This makes no inference or billing calls. The earlier frozen extraction and
cache-follow-up bundles are required for identity/disjointness checks. All raw
attempts, first repetitions, failures and attributable charges are retained.
