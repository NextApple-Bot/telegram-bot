#!/usr/bin/env python
import subprocess
import sys


def run_migrations():
    """Запускает alembic upgrade head."""
    subprocess.run(["alembic", "upgrade", "head"])


def show_help():
    print("Usage: python manage.py [command]")
    print("Commands:")
    print("  migrate   - Run database migrations")
    print("  help      - Show this help")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        show_help()
        sys.exit(1)

    command = sys.argv[1]
    if command == "migrate":
        run_migrations()
    else:
        show_help()
