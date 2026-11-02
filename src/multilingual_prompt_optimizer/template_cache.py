"""Versioned instruction-only cache; calibration does not certify future answers."""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from .core import optimize
from .models import Candidate, Request, _library_versions


def _digest(value):
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def cache_context(request, *, tokenizer, generator, reviewer, protocol, validator, mode):
    """Payloads are intentionally excluded; model revisions/options belong in metadata."""
    if request.candidates or request.phrase_options:
        raise ValueError("cache context requires an original template without supplied candidates")
    if mode not in {"english", "mixed"}:
        raise ValueError("cache mode must be english or mixed")
    Request(
        request.instruction,
        output_instruction=request.output_instruction,
        protected_literals=request.protected_literals,
    )
    context = {
        "schema": 1,
        "instruction": request.instruction,
        "output_instruction": request.output_instruction,
        "protected_literals": list(request.protected_literals),
        "tokenizer": tokenizer,
        "tokenizer_library_versions": _library_versions(),
        "generator": generator,
        "reviewer": reviewer,
        "protocol": protocol,
        "validator": validator,
        "mode": mode,
    }
    _digest(context)
    return context


class TemplateCache:
    def __init__(self, directory):
        self.directory = Path(directory)

    @staticmethod
    def key(context):
        return _digest(context)

    def save(self, context, instruction, calibration_passes):
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError("cached instruction must be nonempty text")
        if not isinstance(calibration_passes, (list, tuple)) or any(
            type(x) is not bool for x in calibration_passes
        ):
            raise ValueError("calibration results must be Booleans")
        admitted = len(calibration_passes) >= 2 and all(calibration_passes)
        item = {
            "key": self.key(context),
            "context": context,
            "admitted": admitted,
            "instruction": instruction if admitted else context["instruction"],
            "calibration_passes": list(calibration_passes),
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        item["checksum"] = _digest(item)
        self.directory.mkdir(parents=True, exist_ok=True)
        # Atomic replacement protects readers from partially written cache files.
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self.directory, suffix=".tmp", delete=False
        ) as stream:
            json.dump(item, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            temporary = Path(stream.name)
        os.replace(temporary, self.directory / (item["key"] + ".json"))
        return item

    def load(self, context):
        path = self.directory / (self.key(context) + ".json")
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
            checksum = item.pop("checksum")
            if (
                _digest(item) != checksum
                or item.get("key") != self.key(context)
                or item.get("context") != context
                or type(item.get("admitted")) is not bool
                or not isinstance(item.get("instruction"), str)
                or not item["instruction"].strip()
            ):
                return None
            flags = item.get("calibration_passes")
            if not isinstance(flags, list) or any(type(x) is not bool for x in flags):
                return None
            if item["admitted"] != (len(flags) >= 2 and all(flags)):
                return None
            if not item["admitted"] and item["instruction"] != context["instruction"]:
                return None
            item["checksum"] = checksum
            return item
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def apply(self, context, payload, counter):
        if counter.name != context["tokenizer"]:
            raise ValueError("tokenizer does not match cache context")
        request = Request(
            context["instruction"],
            payload=payload,
            output_instruction=context["output_instruction"],
            protected_literals=tuple(context["protected_literals"]),
        )
        item = self.load(context)
        candidates = (
            (Candidate("cached", item["instruction"]),) if item and item["admitted"] else ()
        )
        result = optimize(
            Request(
                request.instruction,
                payload=request.payload,
                output_instruction=request.output_instruction,
                protected_literals=request.protected_literals,
                candidates=candidates,
            ),
            counter=counter,
            rule_modes=(),
        )
        reason = (
            "cache_miss"
            if not item
            else "calibration_rejected"
            if not item["admitted"]
            else "cache_applied"
            if result.selected_label != "original"
            else "original_retained_after_recount"
        )
        return {
            "cache_key": self.key(context),
            "cache_hit": item is not None,
            "admitted": bool(item and item["admitted"]),
            "reason": reason,
            "prompt": result.prompt,
            "original_tokens": result.original_tokens,
            "selected_tokens": result.selected_tokens,
            "saved_tokens": result.saved_tokens,
            "selected_label": result.selected_label,
        }
