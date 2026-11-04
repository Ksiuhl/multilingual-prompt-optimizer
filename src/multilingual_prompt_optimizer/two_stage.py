"""Explicit English freeze followed by translation-only candidate search.

Stage one is caller-selected English (e.g. PromptMin or English-only auto mode).
Structural alignment and optional model opinions are not semantic guarantees.
"""

import hashlib
import itertools
import json
from dataclasses import dataclass, replace

from .core import optimize
from .models import Candidate, Request
from .tokenizers import TiktokenCounter


@dataclass(frozen=True)
class FrozenEnglish:
    request: Request
    segments: tuple[str, ...]
    sha256: str


def freeze_english(request: Request, segments) -> FrozenEnglish:
    """Freeze the chosen English byte string; segments must cover it exactly."""
    if not isinstance(request, Request):
        raise ValueError("request must be a Request")
    if not isinstance(segments, (list, tuple)) or not 1 <= len(segments) <= 5:
        raise ValueError("provide one to five exact English segments")
    if any(not isinstance(s, str) or not s.strip() for s in segments):
        raise ValueError("segments must be nonempty strings")
    segments = tuple(segments)
    if " ".join(segments) != request.instruction:
        raise ValueError("segments must rejoin to the exact frozen English instruction")
    clean = replace(
        request,
        candidates=(),
        phrase_options=(),
        protected_literals=tuple(request.protected_literals),
    )
    return FrozenEnglish(clean, segments, hashlib.sha256(clean.instruction.encode()).hexdigest())


def translation_job(frozen: FrozenEnglish, languages=("zh", "ja")):
    """Return a provider-neutral translation request with no source/original input."""
    _validate(frozen)
    languages = tuple(languages)
    if (
        not languages
        or len(set(languages)) != len(languages)
        or any(lang not in {"zh", "ja", "es", "fr", "de", "ko"} for lang in languages)
    ):
        raise ValueError("choose distinct supported target languages")
    return {
        "system": (
            "Translate each frozen English segment separately into the requested languages. "
            "The English has already been compressed: do not summarize, add, omit, reorder "
            "or reinterpret its requirements. Preserve conditions, negation, tie rules, "
            "identifiers, operators, numeric strings and literal spelling. Segments will be "
            "recombined with untranslated English segments, so each must retain its meaning "
            "and role in that combination. Do not perform the underlying task. Return only "
            "JSON with a translations array in the exact same segment order. Each object "
            "has exactly the requested target-language keys and their translation strings. "
            "Do not return or rewrite English."
        ),
        "data": {
            "frozen_english_sha256": frozen.sha256,
            "english_segments": list(frozen.segments),
            "target_languages": list(languages),
        },
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["translations"],
            "properties": {
                "translations": {
                    "type": "array",
                    "minItems": len(frozen.segments),
                    "maxItems": len(frozen.segments),
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": list(languages),
                        "properties": {
                            lang: {"type": "string", "minLength": 1} for lang in languages
                        },
                    },
                }
            },
        },
    }


def _validate(frozen):
    if (
        not isinstance(frozen, FrozenEnglish)
        or " ".join(frozen.segments) != frozen.request.instruction
        or hashlib.sha256(frozen.request.instruction.encode()).hexdigest() != frozen.sha256
    ):
        raise ValueError("frozen English identity/alignment changed")


def rank_translations(
    frozen: FrozenEnglish, response, *, languages=("zh", "ja"), counter=None, max_combinations=256
):
    """Count complete prompts, retaining English; genuine candidates are diagnostics.

    This function does not send requests, certify meaning or release task answers.
    Callers must supply semantic/task validation before deploying a translation.
    """
    _validate(frozen)
    job = translation_job(frozen, languages)
    languages = tuple(job["data"]["target_languages"])
    if (
        type(max_combinations) is not int
        or max_combinations < 1
        or (len(languages) + 1) ** len(frozen.segments) > max_combinations
    ):
        raise ValueError("translation search exceeds the combination budget")
    if not isinstance(response, dict) or set(response) != {"translations"}:
        raise ValueError("invalid translation response")
    translations = response["translations"]
    if not isinstance(translations, list) or len(translations) != len(frozen.segments):
        raise ValueError("translation must preserve segment count/order")
    options = []
    for en, row in zip(frozen.segments, translations):
        if (
            not isinstance(row, dict)
            or set(row) != set(languages)
            or any(not isinstance(v, str) or not v.strip() for v in row.values())
        ):
            raise ValueError("invalid target-language segment mapping")
        options.append({"en": en, **row})
    active = counter or TiktokenCounter()
    candidates, provenance = [], {}
    for combo in itertools.product(*(tuple(o.items()) for o in options)):
        langs = tuple(lang for lang, _ in combo)
        if "en" not in langs or len(set(langs)) < 2:
            continue
        label = "stage2:" + "/".join(langs)
        instruction = " ".join(text for _, text in combo)
        candidates.append(Candidate(label, instruction))
        provenance["supplied:" + label] = {
            "languages": list(langs),
            "segments": [text for _, text in combo],
        }
    request = replace(frozen.request, candidates=tuple(candidates), phrase_options=())
    pool = optimize(request, counter=active, allow_compression=True, rule_modes=())
    genuine = [
        c
        for c in pool.candidates
        if c.label in provenance
        and all(r == "full_prompt_token_increase" for r in c.rejection_reasons)
    ]
    diagnostic = min(genuine, key=lambda c: (c.tokens, c.label)) if genuine else None
    # No semantic approval is implied by either the shortest pool entry or diagnostic.
    return {
        "frozen_english_sha256": frozen.sha256,
        "english_instruction": frozen.request.instruction,
        "english_prompt": frozen.request.compose(frozen.request.instruction),
        "english_tokens": pool.original_tokens,
        "pool": pool.to_dict(),
        "provenance": provenance,
        "shortest_genuine": None
        if diagnostic is None
        else {
            "label": diagnostic.label,
            "instruction": diagnostic.instruction,
            "prompt": diagnostic.prompt,
            "tokens": diagnostic.tokens,
            "not_larger_than_english": diagnostic.tokens <= pool.original_tokens,
            "strictly_shorter_than_english": diagnostic.tokens < pool.original_tokens,
            **provenance[diagnostic.label],
        },
        "semantics_certified": False,
    }


def encode_translation_job(job):
    """Serialize the exact stateless request for generic JSON/API clients."""
    return (
        job["system"]
        + "\n\nDATA:\n"
        + json.dumps(job["data"], ensure_ascii=False)
        + "\n\nOUTPUT_SCHEMA:\n"
        + json.dumps(job["schema"], ensure_ascii=False)
    )
