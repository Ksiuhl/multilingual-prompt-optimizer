"""Thin adapter around unmodified PromptMin 0.3.0; see THIRD_PARTY_NOTICES.md."""

from threading import RLock

from .models import Candidate
from .tokenizers import Counter

MODES = {
    "lite": {"mode": "lite", "translate": False, "domains": []},
    "translate": {
        "mode": "lite",
        "translate": True,
        "domains": ["ai", "backend", "data", "devops", "web"],
    },
    "aggressive": {
        "mode": "aggressive",
        "translate": True,
        "domains": ["ai", "backend", "data", "devops", "web"],
    },
}
_LOCK = RLock()
_COUNTER_NAME = "multilingual_prompt_optimizer_active_counter"


def generate(instruction: str, counter: Counter, modes: tuple[str, ...]) -> list[Candidate]:
    if not modes:
        return []
    from promptmin import minify
    from promptmin.tokens import register

    # PromptMin's public registry is process-wide. Keep registration and use
    # together so concurrent requests cannot use each other's token counter.
    with _LOCK:
        register(_COUNTER_NAME, exact=True, family=counter.name)(counter.count)
        return [
            Candidate(
                "promptmin:" + mode,
                minify(instruction, tokenizer=_COUNTER_NAME, **MODES[mode])["minified"]
                or instruction,
            )
            for mode in modes
        ]
