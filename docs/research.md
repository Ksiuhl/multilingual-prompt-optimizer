# Research scope and evidence

The later reviewer and automatic-generation development experiments are documented
in [the reviewer study](reviewer-study.md). They extend the earlier manual and
rule-based work below; they do not replace independent semantic/task evaluation.

## Question

Can selecting semantically equivalent wording across languages reduce the target
tokenizer's full prompt count beyond concise English, while preserving task quality
and reducing end-to-end cost?

This repository is infrastructure for testing that question. It does not establish
that the broad idea is new or that the proposed system is economically beneficial.

## Completed development work

A manual pilot used GPT-5.4 mini selected on Duck.ai. The user ran each prompt in a
fresh chat and pasted the responses for scoring. All 26 reported responses passed
the relevant checks across eight distinct tasks. Twenty-four were the core
original/English/mixed comparison; two additional responses repeated English text
under the best-single-language condition.

| Version | Local content tokens across eight tasks |
| --- | ---: |
| Original | 629 |
| Concise English | 541 |
| Mixed language | 537 |

Mixing saved four tokens, or 0.74%, beyond concise English in this small sample.
These are local `o200k_base` content counts. The backend snapshot, provider usage,
latency, generation overhead, and total cost were not measured. Scoring was not
blinded or independently reviewed. These results do not prove general accuracy
preservation. Most of the reduction came from concise wording.

Separately, PromptMin 0.3.0 was run on 30 synthetic English/Chinese development
prompts and six Spanish technical coverage examples across GPT, Qwen and Llama
tokenizers. Instruction-only translation mode had zero net reduction on the general
set and roughly 11–13% on the deliberately supported Spanish diagnostic. That
comparison used authored alternatives, not an equally automated competing generator.

## Engineering findings

The pinned PromptMin release's full-text cleanup removed Python indentation in a
source-code example and removed a word from source material to be translated.
Another example grew from 69 to 70 content tokens after processing. These are
specific reproduced cases, not a claim about every release or downstream accuracy.

This package therefore rewrites instructions separately, preserves payloads and
output instructions, and recounts final prompts before selection. Numeric strings
and explicitly protected literals receive additional checks. Structural checks
cannot prove that a rewritten instruction means the same thing.

## Related work

| Work | Relevant method | Status in this project |
| --- | --- | --- |
| [PromptMin](https://github.com/DelvyG/promptmin) | Rule compaction and Spanish-to-English phrase substitutions | Released dependency executed; credited and licensed |
| [Cross-Lingual Token Arbitrage](https://arxiv.org/abs/2606.03618) | Local-model English rewriting for coding tasks | Paper/reference source inspected; model stage not run |
| [Sigo](https://github.com/twigglits/Sigo) | Local English-to-Chinese translation with token accounting | Source inspected; model stage not run |
| [In-context Mixing, ACL 2024](https://aclanthology.org/2024.acl-long.228/) | Few-shot code-mixed prompting for multilingual task performance | Related work, not a reproduced cost baseline |

Whole-prompt translation, phrase substitution, and code mixing already exist.
A research contribution would require a specific improvement or a rigorous new
evaluation, supported against these baselines. No absence-of-prior-work claim is made.

## Next evaluation

1. Freeze the automatic generator, search budget, and scoring rules.
2. Create new task instances, including longer text, code, negation, exact literals,
   dates, and cases where no answer qualifies.
3. Compare original, concise English, protected PromptMin, translation, and mixing
   using matched generation/validation budgets.
4. Repeat paired trials and use independent or blinded scoring where possible.
5. Include generator/validator usage, target input/output, retries, and latency in
   total cost. Keep local compute assumptions explicit.

No automated queries to Duck.ai or other consumer chat websites are implemented.
