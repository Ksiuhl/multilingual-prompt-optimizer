# Changelog

## 0.6.0a5 — strict frozen-English second stage

- Added a byte-checked English freeze and a translation-only job that excludes source data and the earlier original instruction.
- Recombine immutable English segments with translated segments, count full prompts, preserve numeric/literal guards and retain English on ties or growth. Ranking does not certify semantic equivalence or release task answers.
- Added boundary/provenance tests and a staged experiment that separates actual token-policy choices, forced diagnostics, translation/review overhead and target-answer accuracy. Original-only defaults and earlier evidence remain unchanged.

## 0.6.0a4 — scoped extraction admission experiment

- Added `JsonExtractionTemplate` and `validated-extract`: original fallback unless paired development/holdout accuracy, distinct coverage, target/tokenizer identity and matched cost gates pass.
- Added exact runtime answer checking, original retry, and no release after failed validation. Opt-in and original-only defaults remain unchanged.
- Recorded 64 correct responses, the prospectively audited uniqueness supplement, and reconciled gateway credit charges. Admission was rejected by development cost; no profitable template is claimed.
- This deterministic projection is a controlled admission example and can be computed locally without an LLM. Earlier studies remain unchanged.

## 0.6.0a3 — original first, compression opt-in

- `optimize`, `auto_optimize`, and cached template application now retain the original unless `allow_compression=True` is supplied.
- CLI optimization, automatic mode and benchmarks require `--enable-compression` to search shorter alternatives. Rewrite modifiers cannot implicitly enable it.
- Disabled automatic mode needs no model/service and makes no generation or judging calls; disabled cache use does not load rewrites.
- Results expose `compression_enabled`. Added default-path regression tests and retained existing search tests as explicit opt-in experiments.
- Research harnesses and documentation now state their opt-in behavior. Earlier frozen evidence and scores are unchanged; no new accuracy benefit is claimed.

## 0.6.0a2 — immutable output-contract regression fix

- Added five exact-prompt repeats on four known content-failure cases: 15/20 original versus 11/20 concise English. Keep the default-policy proposal unmerged.
- Matched all 40 gateway consumption records to response request IDs and reconciled 9,520 charged quota units with a stable key-counter delta ($0.01904 in gateway-displayed credits). English's charge reduction was 0.88%; no account balances or unrelated history are published.
- Added a prospectively frozen 50-new-input structured-task check: 299 responses from 300 planned trials; interrupted requests and five completed-answer content failures retained separately.
- Recorded unchanged English/mixed prompt pairs, local and reported full-prompt usage, retry-inclusive latency, public-price scenarios, and reproducible PNG/SVG/PDF graphs. Actual billing and accuracy-preservation criteria remain unresolved.
- Added `json_object_contract(fields)` for explicit answer-wrapped JSON guidance in immutable `Request.output_instruction`.
- All complete prompt counts include the extra contract; no response repair or native schema enforcement is implied.
- Added a CLI-ready summary example and four contract/validation regression tests.
- Retested six known summary failure inputs, all three arms, twice on both gateway labels: 72/72 strict passes, no missing wrappers.
- Kept original study scores unchanged; recorded the targeted selection, identical English/mixed prompts, and additional input overhead.
- Added frozen requests, raw receipts, unchanged-rubric offline analysis and PNG/SVG/PDF figures.

## 0.6.0a1 — English-first development preview

- Default rule search now uses English-only lite rewriting; aggressive rules also disable translation.
- Default automatic generation requests English only; one-language generation is supported.
- Translation rules and multilingual auto generation require an explicit CLI flag, language list, or API configuration.
- Added a frozen 50-input, ten-template transfer study: 300 completed answers across two unverified gateway model labels.
- Retained strict JSON-wrapper failures, identical-prompt variability, inconsistent gateway input accounting, and unavailable Grok routing.
- Added frozen data, original rubric, raw/preparation receipts, offline analysis, and PNG/SVG/PDF figures.
- Findings favor concise English on these inputs; multilingual mixing has not shown a meaningful incremental or net-cost benefit.
- This is a prerelease on a development branch; v0.5 remains the baseline pending review.

## 0.5.0 — reusable template cache and reuse projections

- Added atomic instruction-only caching with identity checks, corruption detection and original fallback.
- Added calibration admission, per-new-input full-prompt recounting and a no-preparation-call cache demo.
- Added four longer development templates, two calibration inputs and ten fresh test inputs each.
- Measured 1/10-use endpoints and labeled 100/1,000-use projections with no projected accuracy claims.
- Retained the negative result: no shorter template admitted, no prompt-token saving demonstrated.
- Suppressed spurious identical-prompt timing-jitter crossover claims; added PNG/SVG/PDF graphs.
- Added bounded generator context/output settings for longer instructions (73 engineering tests total).

## 0.4.0 — task-answer validation and graphs

- Added source-derived extraction/filtering/arithmetic validators and bounded Python-AST behavior checks.
- Added validated execution with a real original-prompt fallback and no answer when both attempts fail.
- Added `mpo validate`, a checked live demo, and 20 synthetic task fixtures with three repeated trials.
- Recorded task checks, actual fallback calls, attempted prompt usage and preparation/inference overhead.
- Exported measured overview and category graphs as PNG, SVG and PDF.
- Retained baseline, arithmetic and service failures; no accuracy/cost advantage is claimed.
- Added validator/fallback and HTTP-error regressions (61 engineering tests total).

## 0.3.0 — reviewer development study and automatic benchmark

- Added 20 synthetic labeled review pairs and a reproducible two-model comparison.
- Selected Qwen3 8B for the documented review configuration using a fixed development rule.
- Added a 30-task shared-generation comparison of English, single-language and mixed search.
- Recorded per-call local-model usage, timing, candidate decisions and protocol fingerprints.
- Shared generation and judging functions between production and research scripts.
- Added three review validation tests (44 tests total).

## 0.2.1 — first live-model check

- Bounded semantic-review explanations to avoid overlong structured output.
- Reject output-limited responses even when the returned JSON parses.
- Distinguish connection failures from malformed/model-limited responses.
- Use an IPv4 loopback default to avoid a localhost connection delay observed on Windows.
- Clarified that equivalent translations and request-politeness changes are allowed.
- Recorded a real Qwen3 4B summary-task development check with zero approved savings.
- Added two response-limit/error regression tests (41 tests total).

## 0.2.0 — automatic local-model integration

- Added Ollama-based multilingual clause generation and bounded mixed-language search.
- Added a separate semantic judging pass with optional second-model selection.
- Added original fallback on generation, connection, schema or review failures.
- Recorded available model token counts, local timing, decisions and generated options.
- Added 13 integration/control-flow tests; real-model quality is not yet evaluated.

## 0.1.0 — initial local prototype

- Added an installable package, `mpo` CLI, and Python API.
- Integrated the released PromptMin dependency with attribution.
- Added full-prompt counting, original fallback, source-payload preservation, and
  numeric/literal rejection checks.
- Added bounded supplied-phrase search and optional local tokenizer-file support.
- Added development corpora, examples, tests, and GitHub Actions configuration.

The source is published on GitHub. PyPI publishing is not configured.
