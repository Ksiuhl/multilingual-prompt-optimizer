# Checked-in local results

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
