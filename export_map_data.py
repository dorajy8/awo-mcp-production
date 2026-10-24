"""
Export facility data for the web map in docs/.

Reads from the same source as the MCP server (AWO_DATA_SOURCE, or a local
data/directory.ttl), or from a source given on the command line:

    python export_map_data.py
    python export_map_data.py https://example.org/directory.ttl
"""

import json
import sys
from datetime import date
from pathlib import Path

from src.data_loader import DataLoader, resolve_source
from src.data_repository import DataRepository


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = BASE_DIR / "docs" / "facilities.json"


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else resolve_source(BASE_DIR)
    repository = DataRepository(DataLoader(source).load_all())
    facilities = repository.facility_points()

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "generated": date.today().isoformat(),
                "facilities": facilities,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )

    print(f"Wrote {len(facilities)} facilities to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
