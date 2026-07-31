"""Dispatcher for app.commands submodules."""
import sys
from typing import NoReturn


def main() -> NoReturn:
    """
    Print the available operational commands and exit.

    Terminates the process with ``sys.exit`` rather than returning, so the
    exit status is the command's only output channel.
    """
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
