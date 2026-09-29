"""One-shot CLI entrypoint for help-center ingest."""

from __future__ import annotations

import logging
import sys

from env_loader import load_app_env
from ingest_runner import execute_ingest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)


def main() -> None:
    """CLI entrypoint."""
    load_app_env()
    result = execute_ingest()
    sys.exit(0 if result.status == "success" else 1)


if __name__ == "__main__":
    main()
