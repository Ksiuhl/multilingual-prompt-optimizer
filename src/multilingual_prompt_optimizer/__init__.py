"""Local tokenizer-aware prompt optimization."""

from .automatic import OllamaModel, auto_optimize
from .core import optimize
from .models import Candidate, OptimizationResult, Request
from .template_cache import TemplateCache, cache_context
from .tokenizers import Counter, JsonTokenizerCounter, TiktokenCounter
from .validation import AnswerCheck, execute_checked, validate_answer

__version__ = "0.6.0a1"
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
    "AnswerCheck",
    "execute_checked",
    "validate_answer",
    "TemplateCache",
    "cache_context",
]
