"""Export deterministic JSON Schema documents for common integration contracts."""

import json
from pathlib import Path

from app.schemas.integration import export_contract_schemas


def main() -> None:
    output = Path(__file__).resolve().parents[1] / "schemas"
    for filename, schema in export_contract_schemas().items():
        (output / filename).write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
