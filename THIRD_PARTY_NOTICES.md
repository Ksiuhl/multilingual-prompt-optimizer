# Third-party notices

## PromptMin / promptminify

- Author: DelvyG.
- Project: https://github.com/DelvyG/promptmin
- Package: https://pypi.org/project/promptminify/0.3.0/
- Version used: 0.3.0.
- License: MIT; the upstream license is retained in
  [third_party/PROMPTMIN_LICENSE](third_party/PROMPTMIN_LICENSE).
- Release source commit: `08201a20ff5e58a0fc8d053934034873a7e7382b`.
- Published wheel SHA256:
  `985c4bfb0541e8a265b99e00c3d29cc70adcc3e54c034d20137905567fc795dc`.

The project uses the released dependency through its public `minify` and counter
registration functions. Its source is not modified or vendored in this repository.
The instruction/payload boundary, complete-prompt fallback, candidate search, CLI,
tests, and research records are this project's additions. These additions are not a
claim of academic novelty.

## Tokenizer libraries

- [tiktoken](https://github.com/openai/tiktoken), OpenAI, MIT license.
- [Hugging Face Tokenizers](https://github.com/huggingface/tokenizers), Apache 2.0,
  optional dependency for local tokenizer files.

Libraries are installed as dependencies. Their source and model tokenizer
vocabularies are not bundled here. A user-supplied tokenizer file remains subject
to its publisher's license.

## Research references

Matplotlib is an optional plotting dependency, installed through `.[plots]`. Its
source is not vendored; its licenses are available in the
[upstream license directory](https://github.com/matplotlib/matplotlib/tree/main/LICENSE).
The checked-in figures are this project's measured-data exports.

The bibliography in [docs/research.md](docs/research.md) identifies related work.
No source code from Sigo or Cross-Lingual Token Arbitrage is included in this
repository, and their model stages have not been reproduced by this package.
