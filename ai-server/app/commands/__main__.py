"""Dispatcher for app.commands submodules."""
import sys


def main():
    print("Usage:")
    print("  python -m app.commands.audit_embeddings [--strict] [--json-output PATH]")
    print("  python -m app.commands.rebuild_embeddings --dry-run [--species SLUG]")
    print("  python -m app.commands.rebuild_embeddings --execute [--species SLUG] [--backup]")
    print("")
    print("  --execute validates fingerprint config, checkpoint SHA, dimensions,")
    print("  and TTA match the derived model_version before inserting anything.")
    sys.exit(0)


if __name__ == "__main__":
    main()
