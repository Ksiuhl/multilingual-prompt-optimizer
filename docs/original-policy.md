# Original-preserving policy (0.6.0a3)

The default returns `request.compose(request.instruction)` unchanged. It keeps
the instruction, source payload, output constraint, Unicode, indentation and
trailing spaces. It reports full composed-content tokens and zero saved tokens.
The existing section separators remain part of `Request.compose`.

This policy covers rules, caller-supplied candidates, phrase combinations,
automatic generation and cached rewrites. A model name, language list, rule mode
or previously admitted cache entry does not grant permission to rewrite.

## Explicit experiments

```python
from multilingual_prompt_optimizer import Request, optimize

request = Request("Please summarize the supplied text.", payload="SOURCE")
unchanged = optimize(request)
experiment = optimize(request, allow_compression=True)
```

`allow_compression` must be an actual Boolean. `auto_optimize` and
`TemplateCache.apply` use the same keyword and default. Disabled automatic mode
needs no generator and never touches a supplied generator or verifier. Disabled
cache application never loads or applies a cached rewrite. English rewriting is
the initial search mode only after compression has been enabled.

```bash
mpo optimize --input examples/summary.json
mpo auto --input examples/automatic.json
mpo optimize --enable-compression --input examples/summary.json
mpo auto --enable-compression --input examples/automatic.json --model qwen3:4b
mpo benchmark --enable-compression --input data/development.json
```

The first two commands retain the original; the automatic command needs no
Ollama service in that mode. Enabled automatic generation requires `--model`.
`--experimental-multilingual`, `--aggressive`, `--languages` and `--no-rules`
require `--enable-compression`; they never silently grant it. Without opt-in,
benchmark records retain original prompts across all comparison columns.

`compression_enabled` records the effective policy, including when an enabled
search falls back to the original. Disabled automatic reports use status
`compression_disabled`, policy `original_only`, and an empty model-call list.

## Validation remains separate

Opt-in enables an experiment; it does not approve a rewrite. Numeric/literal
guards and a language-model equivalence judge do not prove preserved accuracy.
Callers should validate a specific transformation against representative task
inputs before using it, and use `execute_checked` with a configured task oracle
when available. Historical cache calibration does not validate a new payload.
No universal validator or validated-template registry is introduced here.

The [five-repeat follow-up](reliability-followup.md) passed 15/20 original versus
11/20 English checks on four known failure cases, for only 0.88% lower gateway
credit usage. That motivates the default change. Those results and all earlier
studies remain separate and unchanged; they tested experimental compression,
not this original-only default.

Research benchmark harnesses explicitly opt into compression for their stated
experiments. The checked-case and cached-template demo scripts also require
`--enable-compression` to rewrite. Their target-task execution can still make
model calls even when instruction rewriting is disabled.
