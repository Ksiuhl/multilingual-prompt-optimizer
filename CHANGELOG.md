# Changelog

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
