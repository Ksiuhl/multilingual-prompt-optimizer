"""Local tokenizer-aware prompt optimization."""

from .automatic import OllamaModel, auto_optimize
from .core import optimize
from .models import Candidate, OptimizationResult, Request
from .tokenizers import Counter, JsonTokenizerCounter, TiktokenCounter

__version__ = "0.2.1"
__all__ = [
    "Candidate",
    "Counter",
    "JsonTokenizerCounter",
    "OptimizationResult",
    "OllamaModel",
    "Request",
    "TiktokenCounter",
    "optimize",
    "auto_optimize",
]
