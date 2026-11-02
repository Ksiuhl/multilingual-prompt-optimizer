# Dataset provenance

`development.json` contains 30 original synthetic task examples: 15 English-source
and 15 Chinese-source prompts. The broad categories were informed by
[OpenAI's usage research](https://openai.com/index/how-people-are-using-chatgpt/).
They are not a measured ranking of the 30 most-used prompts and were not extracted
from private conversations.

The English, Chinese, and Japanese clause alternatives were authored by the
assistant during development. They have not all received independent bilingual
review. Source payloads are synthetic, including the names, order numbers, dates,
code, and other example facts. Project-authored data is available under the MIT
license in this repository.

`spanish-coverage.json` contains six additional synthetic technical examples with
English, Spanish, and Chinese alternatives. These deliberately exercise a language
and domain supported by PromptMin. Keep the diagnostic separate from the general
development set; do not report it as unbiased or held-out validation.

The CLI ignores top-level description/provenance fields for optimization but saves
candidate provenance in its report. Each item consists of an ID and the same
request fields accepted by the Python API.

No model responses or actual API billing measurements are included in these files.

`reviewer-development.json` adds ten equivalent rewrites and ten deliberate meaning
changes across ten task templates. It is synthetic, assistant-authored development
data under MIT, not independently reviewed bilingual ground truth. Positive and
negative members share task templates, so the 20 records are not 20 independent
tasks. Reviewers see no expected labels. The set was used to choose a review model;
future validation must use fresh examples.

`task-quality-development.json` adds 20 synthetic fixtures: five per extraction,
filtering, arithmetic and code category. Several share templates. Their configured
oracles are derived from the source JSON or finite code test vectors, and are not
sent to the models. They are assistant-authored MIT development data, not held-out
or independently audited ground truth. Three repeated outputs per fixture do not
make 60 independent tasks. See `docs/task-quality-study.md` for the scored protocol.
