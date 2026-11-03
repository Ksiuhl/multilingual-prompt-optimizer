"""Bounded candidate search with full-message counting and original fallback."""

import itertools
import math
import re
import time
from collections import Counter as Multiset
from typing import Any, Mapping

from . import rules
from .models import Candidate, EvaluatedCandidate, OptimizationResult, Request
from .tokenizers import Counter, TiktokenCounter


def _numbers(text: str) -> Multiset[str]:
    return Multiset(re.findall(r"\d+(?:[.-]\d+)*", text))


def _count(counter: Counter, text: str) -> int:
    value = counter.count(text)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("token counter must return a nonnegative integer")
    return value


def optimize(
    request: Request | Mapping[str, Any],
    *,
    counter: Counter | None = None,
    rule_modes: tuple[str, ...] = ("lite",),
    max_combinations: int = 256,
) -> OptimizationResult:
    """Choose the smallest candidate passing structural checks, including original.

    Translations are supplied as candidates/phrase options. This function does
    not claim that shorter candidates preserve meaning or improve task accuracy.
    """
    start = time.perf_counter()
    req = request if isinstance(request, Request) else Request.from_dict(request)
    if (
        isinstance(max_combinations, bool)
        or not isinstance(max_combinations, int)
        or max_combinations < 1
    ):
        raise ValueError("max_combinations must be a positive integer")
    if any(mode not in rules.MODES for mode in rule_modes):
        raise ValueError("rule_modes must contain lite, translate, or aggressive")
    combinations = (
        math.prod(len(options) for options in req.phrase_options) if req.phrase_options else 0
    )
    if combinations > max_combinations:
        raise ValueError(
            f"phrase search needs {combinations} combinations; limit is {max_combinations}"
        )
    active = counter if counter is not None else TiktokenCounter()
    original = req.compose(req.instruction)
    before = _count(active, original)
    specs: list[tuple[Candidate, str, tuple[str, ...]]] = [
        (Candidate("original", req.instruction), "original", ()),
    ]
    specs.extend((c, "promptmin", ()) for c in rules.generate(req.instruction, active, rule_modes))
    specs.extend(
        (Candidate("supplied:" + c.label, c.instruction), "supplied", ()) for c in req.candidates
    )
    if req.phrase_options:
        for choices in itertools.product(
            *(tuple(options.items()) for options in req.phrase_options)
        ):
            languages = tuple(lang for lang, _ in choices)
            instruction = " ".join(text for _, text in choices)
            label = "phrases:" + "/".join(languages)
            specs.append((Candidate(label, instruction), "phrase_search", languages))
    evaluated = []
    numbers = _numbers(req.instruction)
    for spec, source, languages in specs:
        prompt = req.compose(spec.instruction)
        tokens = _count(active, prompt)
        reasons = []
        if tokens > before:
            reasons.append("full_prompt_token_increase")
        if numbers - _numbers(spec.instruction):
            reasons.append("instruction_number_changed")
        for literal in req.protected_literals:
            # Payload is immutable, but literals occurring in the instruction
            # must also retain their original instruction-side multiplicity.
            if spec.instruction.count(literal) < req.instruction.count(literal):
                reasons.append("protected_literal_changed:" + literal)
        evaluated.append(
            EvaluatedCandidate(
                spec.label,
                source,
                spec.instruction,
                prompt,
                tokens,
                not reasons,
                tuple(reasons),
                languages,
            )
        )
    # Original is first; equal-token alternatives leave it unchanged.
    selected = min((c for c in evaluated if c.accepted), key=lambda c: c.tokens)
    return OptimizationResult(
        tokenizer=active.name,
        original_tokens=before,
        selected_tokens=selected.tokens,
        saved_tokens=before - selected.tokens,
        reduction=(before - selected.tokens) / before if before else 0.0,
        selected_label=selected.label,
        prompt=selected.prompt,
        candidates=tuple(evaluated),
        elapsed_ms=(time.perf_counter() - start) * 1000,
    )
