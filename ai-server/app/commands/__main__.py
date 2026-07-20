"""Dispatcher for app.commands submodules."""
import sys


def main():
    print("Usage:")
    print("  python -m app.commands.audit_embeddings [--strict] [--json-output PATH]")
    print("  python -m app.commands.rebuild_embeddings [--dry-run] [--species SLUG] [--backup]")
    sys.exit(0)


if __name__ == "__main__":
    main()
