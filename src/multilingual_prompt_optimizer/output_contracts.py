"""Explicit output constraints belong outside the editable instruction."""

import json
from collections.abc import Sequence


def json_object_contract(fields: Sequence[str]) -> str:
    """Describe an answer-wrapped JSON object without changing returned answers.

    Pass this string as Request.output_instruction so every candidate retains it
    and the complete-prompt counter includes its overhead. It is prompt guidance,
    not a schema enforcer or a guarantee that a model will follow the format.
    """
    if not isinstance(fields, (list, tuple)) or not 1 <= len(fields) <= 64:
        raise ValueError("fields must contain 1 to 64 distinct JSON field names")
    if any(not isinstance(field, str) or not field or len(field) > 128 for field in fields):
        raise ValueError("field names must be nonempty strings of at most 128 characters")
    if len(set(fields)) != len(fields):
        raise ValueError("field names must be distinct")
    names = json.dumps(list(fields), ensure_ascii=False)
    shape = json.dumps({"answer": {field: "<task result>" for field in fields}}, ensure_ascii=False)
    return (
        'Return exactly one JSON object. Its ONLY top-level key must be "answer". '
        'The value of "answer" must be an object with exactly these keys: '
        + names
        + '. Put those fields INSIDE "answer", never at the top level. '
        "Use the actual task results and requested value types. "
        "The following is a shape example only; replace every placeholder: "
        + shape
        + ". No extra keys, Markdown fences, or text outside the JSON. Respond in English."
    )
