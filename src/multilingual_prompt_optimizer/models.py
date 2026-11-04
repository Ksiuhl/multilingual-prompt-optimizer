"""Validated request and result objects, independent of any model provider."""

from dataclasses import asdict, dataclass, field
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Mapping


def _library_versions() -> dict[str, str]:
    found = {}
    for name in ("tiktoken", "promptminify", "tokenizers"):
        try:
            found[name] = version(name)
        except PackageNotFoundError:
            continue
    return found


@dataclass(frozen=True)
class Candidate:
    label: str
    instruction: str

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError("candidate label must be a nonempty string")
        if not isinstance(self.instruction, str) or not self.instruction.strip():
            raise ValueError("candidate instruction must be a nonempty string")


@dataclass(frozen=True)
class Request:
    instruction: str
    payload: str = ""
    output_instruction: str = "Respond in English."
    protected_literals: tuple[str, ...] = ()
    candidates: tuple[Candidate, ...] = ()
    phrase_options: tuple[Mapping[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.instruction, str) or not self.instruction.strip():
            raise ValueError("instruction must be a nonempty string")
        if not isinstance(self.payload, str) or not isinstance(self.output_instruction, str):
            raise ValueError("payload and output_instruction must be strings")
        if not isinstance(self.protected_literals, (list, tuple)) or any(
            not isinstance(s, str) or not s for s in self.protected_literals
        ):
            raise ValueError("protected_literals must contain nonempty strings")
        if not isinstance(self.candidates, (list, tuple)) or any(
            not isinstance(c, Candidate) for c in self.candidates
        ):
            raise ValueError("candidates must contain Candidate objects")
        if len({c.label for c in self.candidates}) != len(self.candidates):
            raise ValueError("candidate labels must be unique")
        if not isinstance(self.phrase_options, (list, tuple)):
            raise ValueError("phrase_options must be a sequence of language-to-text mappings")
        for options in self.phrase_options:
            if not isinstance(options, Mapping) or not options:
                raise ValueError("each phrase option must be a nonempty language-to-text mapping")
            if any(
                not isinstance(lang, str)
                or not lang.strip()
                or not isinstance(text, str)
                or not text.strip()
                for lang, text in options.items()
            ):
                raise ValueError("phrase language labels and text must be nonempty strings")
        for literal in self.protected_literals:
            if literal not in self.compose(self.instruction):
                raise ValueError(
                    f"protected literal is absent from the original prompt: {literal!r}"
                )

    def compose(self, instruction: str) -> str:
        """Join explicit sections without changing their contents or code indentation."""
        parts = [instruction]
        if self.payload:
            parts.append(self.payload)
        if self.output_instruction:
            parts.append(self.output_instruction)
        return "\n\n".join(parts)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Request":
        if not isinstance(data, Mapping):
            raise ValueError("request must be a JSON object")
        allowed = {
            "instruction",
            "payload",
            "output_instruction",
            "protected_literals",
            "candidates",
            "phrase_options",
        }
        unknown = set(data) - allowed
        if unknown:
            raise ValueError("unknown request fields: " + ", ".join(sorted(unknown)))
        if "instruction" not in data:
            raise ValueError("request is missing instruction")
        raw_candidates = data.get("candidates", [])
        if not isinstance(raw_candidates, (list, tuple)):
            raise ValueError("candidates must be a JSON array")
        candidates = []
        for item in raw_candidates:
            if not isinstance(item, Mapping) or set(item) != {"label", "instruction"}:
                raise ValueError("each candidate needs exactly label and instruction")
            candidates.append(Candidate(item["label"], item["instruction"]))
        values = dict(data)
        values["candidates"] = tuple(candidates)
        return cls(**values)


@dataclass(frozen=True)
class EvaluatedCandidate:
    label: str
    source: str
    instruction: str
    prompt: str
    tokens: int
    accepted: bool
    rejection_reasons: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()


@dataclass(frozen=True)
class OptimizationResult:
    tokenizer: str
    original_tokens: int
    selected_tokens: int
    saved_tokens: int
    reduction: float
    selected_label: str
    prompt: str
    candidates: tuple[EvaluatedCandidate, ...]
    elapsed_ms: float
    compression_enabled: bool = False
    library_versions: dict[str, str] = field(default_factory=_library_versions)
    semantic_equivalence_verified: bool = False
    automation: dict | None = None
    counting_scope: str = (
        "Complete composed user-message content; excludes provider billing wrappers"
    )
    notes: tuple[str, ...] = field(
        default_factory=lambda: (
            "Source payload and output instruction are preserved exactly.",
            "Numeric and literal checks are structural guards, not semantic verification.",
            "Token savings are not measured API cost savings.",
        )
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
