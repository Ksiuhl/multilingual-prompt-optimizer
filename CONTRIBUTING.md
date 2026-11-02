# Contributing

Start with an issue describing the task, tokenizer, constraints, and expected behavior.
Use synthetic or openly licensed examples and identify their source.

```bash
python -m pip install -e ".[dev,hf]"
ruff check .
python -m unittest discover -s tests -v
python -m build
```

For a compression change, report complete-prompt counts and check source payloads,
numbers, exact literals, and output constraints. Include cases where an alternative
grows or changes a requirement. Keep a concise-English baseline in model evaluations.

Do not describe token reduction as monetary savings without recording generator,
validator, target input/output, retries, and applicable prices. State which parts of
quality evaluation were automatic, manual, blinded, or independently reviewed.

Keep new datasets separate from development data until configurations are frozen.
Preserve attribution and upstream licenses when reusing code or data.
