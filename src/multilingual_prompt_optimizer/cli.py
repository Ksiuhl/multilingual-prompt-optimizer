"""Command-line interface for optimization and local development benchmarks."""

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from .core import optimize
from .models import Request
from .tokenizers import JsonTokenizerCounter, TiktokenCounter


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(value, output: Path | None, *, plain: bool = False) -> None:
    text = value if plain else json.dumps(value, ensure_ascii=False, indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def _counter(args):
    return (
        JsonTokenizerCounter(args.tokenizer_json)
        if args.tokenizer_json
        else TiktokenCounter(args.encoding)
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mpo", description="Local tokenizer-aware prompt optimization"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ["optimize", "benchmark"]:
        cmd = sub.add_parser(name)
        cmd.add_argument("--input", type=Path, required=True, help="UTF-8 request or corpus JSON")
        cmd.add_argument("--output", type=Path)
        enc = cmd.add_mutually_exclusive_group()
        enc.add_argument("--encoding", default="o200k_base")
        enc.add_argument("--tokenizer-json", type=Path, help="Local Hugging Face tokenizer.json")
        cmd.add_argument("--max-combinations", type=int, default=256)
        cmd.add_argument(
            "--aggressive", action="store_true", help="Also generate aggressive rule candidates"
        )
        if name == "optimize":
            cmd.add_argument(
                "--no-rules", action="store_true", help="Use supplied alternatives only"
            )
            cmd.add_argument("--text", action="store_true", help="Output just the selected prompt")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        counter = _counter(args)
        modes = ("lite", "translate", "aggressive") if args.aggressive else ("lite", "translate")
        raw = _read(args.input)
        if args.command == "optimize":
            result = optimize(
                Request.from_dict(raw),
                counter=counter,
                rule_modes=() if args.no_rules else modes,
                max_combinations=args.max_combinations,
            )
            _write(result.prompt if args.text else result.to_dict(), args.output, plain=args.text)
        else:
            if (
                not isinstance(raw, dict)
                or not isinstance(raw.get("items"), list)
                or not raw["items"]
            ):
                raise ValueError("benchmark corpus needs a nonempty items array")
            records = []
            seen = set()
            for item in raw["items"]:
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("id"), str)
                    or not item["id"]
                ):
                    raise ValueError("each corpus item needs a nonempty string id")
                ident = item["id"]
                if ident in seen:
                    raise ValueError("duplicate corpus id: " + ident)
                seen.add(ident)
                req = Request.from_dict({k: v for k, v in item.items() if k != "id"})
                automatic = optimize(
                    replace(req, candidates=(), phrase_options=()),
                    counter=counter,
                    rule_modes=modes,
                )
                supplied = optimize(
                    req, counter=counter, rule_modes=(), max_combinations=args.max_combinations
                )
                hybrid = optimize(
                    req, counter=counter, rule_modes=modes, max_combinations=args.max_combinations
                )
                records.append(
                    {
                        "id": ident,
                        "automatic_rules": automatic.to_dict(),
                        "supplied_search": supplied.to_dict(),
                        "hybrid": hybrid.to_dict(),
                    }
                )
            totals = {
                name: sum(r[name]["selected_tokens"] for r in records)
                for name in ["automatic_rules", "supplied_search", "hybrid"]
            }
            totals["original"] = sum(r["hybrid"]["original_tokens"] for r in records)
            _write(
                {
                    "tokenizer": counter.name,
                    "items": len(records),
                    "totals": totals,
                    "scope": "Local content-token comparison; no task-quality or API-cost evaluation",
                    "candidate_provenance": raw.get("candidate_provenance", "Not specified"),
                    "records": records,
                },
                args.output,
            )
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"mpo: {exc}", file=sys.stderr)
        return 2
