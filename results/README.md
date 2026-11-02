# Checked-in local results

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
