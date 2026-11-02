"""Avoid attributing identical-prompt timing variation to compression speedups."""

import math


def break_even_uses(preparation_ms, baseline_ms, policy_ms, has_distinct_prompt):
    if not all(math.isfinite(x) and x >= 0 for x in (preparation_ms, baseline_ms, policy_ms)):
        raise ValueError("times must be finite and nonnegative")
    if not has_distinct_prompt or baseline_ms <= policy_ms:
        return None
    return math.ceil(preparation_ms / (baseline_ms - policy_ms))
