"""Run the disposable appointment API with ``python -m app``."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from tempfile import gettempdir

from .api import DEFAULT_HOST, DEFAULT_PORT, create_app
from .service import seed_demo_data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the localhost appointment API pilot")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(
            os.environ.get("APPOINTMENT_API_DB", Path(gettempdir()) / "appointment-pilot.sqlite3")
        ),
        help="SQLite database path (default: a temporary-directory fixture)",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=None,
        help="JSONL log path (default: next to --db)",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="loopback host only")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--no-demo-data",
        action="store_true",
        help="do not insert the synthetic actor/client/patient/provider fixture",
    )
    arguments = parser.parse_args(argv)
    application = create_app(arguments.db, log_path=arguments.log)
    if not arguments.no_demo_data:
        seed_demo_data(arguments.db)
    try:
        application.serve(arguments.host, arguments.port)
    except KeyboardInterrupt:
        return 0
    finally:
        application.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
