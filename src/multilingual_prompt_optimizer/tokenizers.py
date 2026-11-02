"""Token counters. No prompts are sent to an inference service."""

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Protocol


class Counter(Protocol):
    name: str

    def count(self, text: str) -> int: ...


@lru_cache(maxsize=8)
def _encoding(name: str):
    import tiktoken

    return tiktoken.get_encoding(name)


class TiktokenCounter:
    def __init__(self, encoding: str = "o200k_base") -> None:
        self.encoding = encoding
        self.name = encoding

    def count(self, text: str) -> int:
        # User text resembling a special-token marker remains ordinary text.
        return len(_encoding(self.encoding).encode_ordinary(text))


class JsonTokenizerCounter:
    """Use a user-supplied Hugging Face tokenizer.json without downloading weights."""

    def __init__(self, path: str | Path) -> None:
        try:
            from tokenizers import Tokenizer
        except ImportError as exc:
            raise RuntimeError(
                "Install the optional tokenizer support: pip install '.[hf]'"
            ) from exc
        source = Path(path)
        raw = source.read_bytes()
        self.name = "tokenizer-json:sha256:" + hashlib.sha256(raw).hexdigest()
        self._tokenizer = Tokenizer.from_str(raw.decode("utf-8"))

    def count(self, text: str) -> int:
        return len(self._tokenizer.encode(text, add_special_tokens=False).ids)
