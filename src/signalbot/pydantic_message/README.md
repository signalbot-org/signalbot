json-models.json downloaded from signal-cli.

For now from this branch https://github.com/AsamK/signal-cli/pull/1952

```bash
uv run datamodel-codegen \
--input ./json-models.json \
--input-file-type openapi \
--output-model-type pydantic_v2.BaseModel \
--formatters ruff-check ruff-format \
--snake-case-field \
--output model.py
```
