"""Deterministic, task-specific answer checks and validated fallback execution."""

import ast
import math
import operator
from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class AnswerCheck:
    passed: bool
    reason: str


def _equal(actual, expected):
    if isinstance(expected, bool) or expected is None:
        return type(actual) is type(expected) and actual == expected
    if isinstance(expected, (int, float, Decimal)):
        if isinstance(actual, bool) or not isinstance(actual, (int, float, Decimal)):
            return False
        return math.isfinite(float(actual)) and abs(
            Decimal(str(actual)) - Decimal(str(expected))
        ) <= Decimal("0.000000001")
    if isinstance(expected, dict):
        return (
            isinstance(actual, dict)
            and set(actual) == set(expected)
            and all(_equal(actual[k], v) for k, v in expected.items())
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(_equal(a, b) for a, b in zip(actual, expected))
        )
    return type(actual) is type(expected) and actual == expected


def expected_answer(case):
    import json

    source = json.loads(case["request"]["payload"])
    spec = case["oracle"]
    if case["kind"] == "extraction":
        result = {}
        for key, path in spec["fields"].items():
            value = source
            for part in path:
                value = value.get(part) if isinstance(value, dict) else None
            result[key] = value
        return result
    if case["kind"] == "filtering":

        def condition(row, c):
            value = row.get(c["field"])
            if c["op"] == "missing":
                return value is None
            other = c["value"]
            ops = {
                "eq": operator.eq,
                "ne": operator.ne,
                "ge": operator.ge,
                "gt": operator.gt,
                "le": operator.le,
                "lt": operator.lt,
            }
            return ops[c["op"]](value, other)

        combine = all if spec.get("combine", "all") == "all" else any
        values = [
            r[spec["output_field"]]
            for r in source
            if combine(condition(r, c) for c in spec["conditions"])
        ]
        if spec.get("order") in {"ascending", "descending"}:
            values = sorted(values, reverse=spec["order"] == "descending")
        return values
    if case["kind"] == "arithmetic":

        def d(value):
            return Decimal(str(value))

        op = spec["operation"]
        if op == "invoice":
            value = (
                sum((d(r["quantity"]) * d(r["unit_price"]) for r in source["lines"]), Decimal(0))
                - d(source.get("discount", 0))
                + d(source.get("shipping", 0))
            )
        elif op == "discount":
            value = d(source["price"]) * (Decimal(1) - d(source["percent"]) / 100)
        elif op == "mean":
            value = sum(map(d, source["values"]), Decimal(0)) / len(source["values"])
        elif op == "weighted_mean":
            value = sum(d(r["value"]) * d(r["weight"]) for r in source["values"]) / sum(
                d(r["weight"]) for r in source["values"]
            )
        elif op == "percent_change":
            value = (d(source["new"]) - d(source["old"])) / d(source["old"]) * 100
        else:
            raise ValueError("unsupported arithmetic operation")
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    raise ValueError("unsupported task kind")


class UnsupportedCode(ValueError):
    pass


_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}
_COMPARE = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
}
_CALLS = {"sum": sum, "len": len, "min": min, "max": max, "abs": abs}


def _bounded(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value) or abs(value) > 1e12:
            raise UnsupportedCode("numeric bound exceeded")
    return value


def _expr(node, env):
    if isinstance(node, ast.Constant) and (
        node.value is None or isinstance(node.value, (int, float, bool))
    ):
        return _bounded(node.value)
    if isinstance(node, ast.Name) and node.id in env:
        return env[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left, right = _expr(node.left, env), _expr(node.right, env)
        if type(left) not in (int, float) or type(right) not in (int, float):
            raise UnsupportedCode("numeric operands required")
        return _bounded(_BINARY[type(node.op)](left, right))
    if isinstance(node, ast.UnaryOp):
        value = _expr(node.operand, env)
        if isinstance(node.op, ast.Not):
            return not value
        if isinstance(node.op, ast.USub):
            return _bounded(-value)
        if isinstance(node.op, ast.UAdd):
            return _bounded(+value)
    if isinstance(node, ast.Compare):
        left = _expr(node.left, env)
        for op, right in zip(node.ops, node.comparators):
            right = _expr(right, env)
            if type(op) not in _COMPARE or not _COMPARE[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.IfExp):
        return _expr(node.body if _expr(node.test, env) else node.orelse, env)
    if isinstance(node, ast.BoolOp):
        value = _expr(node.values[0], env)
        for child in node.values[1:]:
            if (isinstance(node.op, ast.And) and not value) or (
                isinstance(node.op, ast.Or) and value
            ):
                return value
            value = _expr(child, env)
        return value
    if isinstance(node, ast.Subscript):
        value, index = _expr(node.value, env), _expr(node.slice, env)
        if not isinstance(value, list) or type(index) is not int or abs(index) > 100:
            raise UnsupportedCode("bounded list indexing required")
        return value[index]
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _CALLS
        and not node.keywords
    ):
        return _bounded(_CALLS[node.func.id](*[_expr(a, env) for a in node.args]))
    raise UnsupportedCode("expression outside supported Python subset")


def _body(statements, env):
    for statement in statements:
        if isinstance(statement, ast.Return):
            return True, _expr(statement.value, env) if statement.value else None
        if isinstance(statement, ast.If):
            returned, value = _body(
                statement.body if _expr(statement.test, env) else statement.orelse, env
            )
            if returned:
                return True, value
        elif (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            continue
        else:
            raise UnsupportedCode("statement outside supported Python subset")
    return False, None


def check_code(code, spec):
    """Interpret a small bounded AST subset. Never use exec/eval or run model code."""
    if not isinstance(code, str) or len(code) > 8000:
        return AnswerCheck(False, "invalid_code_text")
    try:
        tree = ast.parse(code)
        if (
            len(list(ast.walk(tree))) > 200
            or len(tree.body) != 1
            or not isinstance(tree.body[0], ast.FunctionDef)
        ):
            raise UnsupportedCode("one bounded function required")
        fn = tree.body[0]
        if (
            fn.name != spec["function"]
            or [a.arg for a in fn.args.args] != spec["parameters"]
            or fn.decorator_list
            or fn.args.defaults
            or fn.args.vararg
            or fn.args.kwarg
            or fn.args.kwonlyargs
            or fn.args.posonlyargs
            or fn.returns
            or any(a.annotation for a in fn.args.args)
        ):
            raise UnsupportedCode("function signature is outside supported subset")
        # Reject unsupported syntax even in branches not reached by fixture inputs.
        allowed = (
            ast.Module,
            ast.FunctionDef,
            ast.arguments,
            ast.arg,
            ast.Return,
            ast.If,
            ast.Expr,
            ast.Constant,
            ast.Name,
            ast.Load,
            ast.BinOp,
            ast.UnaryOp,
            ast.Compare,
            ast.IfExp,
            ast.BoolOp,
            ast.Subscript,
            ast.Call,
            ast.Not,
            ast.USub,
            ast.UAdd,
            ast.And,
            ast.Or,
            *_BINARY.keys(),
            *_COMPARE.keys(),
        )
        for node in ast.walk(tree):
            if not isinstance(node, allowed):
                raise UnsupportedCode("unsupported syntax")
            if isinstance(node, ast.Call) and (
                not isinstance(node.func, ast.Name) or node.func.id not in _CALLS
            ):
                raise UnsupportedCode("unsupported call")
        for trial in spec["tests"]:
            if len(trial["args"]) != len(spec["parameters"]):
                raise ValueError("invalid fixture argument count")
            env = dict(zip(spec["parameters"], trial["args"]))
            _, actual = _body(fn.body, env)
            if not _equal(actual, trial["expected"]):
                return AnswerCheck(False, "behavior_mismatch")
        return AnswerCheck(True, "all_fixture_tests_passed")
    except (
        SyntaxError,
        ValueError,
        TypeError,
        ArithmeticError,
        IndexError,
        KeyError,
        RecursionError,
    ) as exc:
        return AnswerCheck(
            False, "unsupported_code" if isinstance(exc, UnsupportedCode) else "code_error"
        )


def validate_answer(case, answer):
    if (
        not isinstance(case, dict)
        or case.get("kind") not in {"extraction", "filtering", "arithmetic", "code"}
        or not isinstance(case.get("oracle"), dict)
    ):
        raise ValueError("case needs a supported kind and an oracle object")
    if not isinstance(answer, dict):
        return AnswerCheck(False, "answer_is_not_object")
    if case["kind"] == "code":
        if set(answer) != {"code"}:
            return AnswerCheck(False, "wrong_transport_fields")
        return check_code(answer["code"], case["oracle"])
    if set(answer) != {"answer"}:
        return AnswerCheck(False, "wrong_transport_fields")
    expected = expected_answer(case)
    return AnswerCheck(
        _equal(answer["answer"], expected),
        "matches_oracle" if _equal(answer["answer"], expected) else "wrong_answer",
    )


def answer_schema(kind):
    field = "code" if kind == "code" else "answer"
    value = {
        "type": {
            "extraction": "object",
            "filtering": "array",
            "arithmetic": "number",
            "code": "string",
        }[kind]
    }
    if kind == "filtering":
        value["items"] = {"type": "string"}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [field],
        "properties": {field: value},
    }


def execute_checked(original_prompt, candidate_prompt, execute, validate):
    """Validate a candidate answer, retry original when needed, release only a pass.

    Validator/oracle is supplied by the application. This is not general semantic
    validation and incurs real fallback inference when the candidate fails.
    """
    attempts = []
    prompts = [("candidate", candidate_prompt)]
    if candidate_prompt != original_prompt:
        prompts.append(("original_fallback", original_prompt))
    for source, prompt in prompts:
        try:
            answer = execute(prompt)
            check = validate(answer)
            attempt = {"source": source, "answer": answer, "validation": asdict(check)}
        except (RuntimeError, ValueError, OSError) as exc:
            attempt = {
                "source": source,
                "answer": None,
                "validation": {"passed": False, "reason": "execution_error"},
                "error": str(exc),
            }
        attempts.append(attempt)
        if attempt["validation"]["passed"]:
            return {
                "validated": True,
                "answer": attempt["answer"],
                "selected_source": source,
                "released_prompt": prompt,
                "attempts": attempts,
            }
    return {
        "validated": False,
        "answer": None,
        "selected_source": "no_valid_answer",
        "released_prompt": None,
        "attempts": attempts,
    }
