"""
FishDex MCP Server
==================
Exposes the FishDex codebase to Make.com via MCP (Model Context Protocol).
Lets you use Make's AI credits (Claude Opus 4.5) to search, read, and
analyze your codebase.

Quick start on your Windows machine:
    pip install mcp uvicorn
    python server.py          # runs on http://0.0.0.0:8001

Then tunnel with Cloudflare Tunnel:
    cloudflared tunnel --url http://localhost:8001

In Make.com, connect MCP Client to: https://<tunnel-url>
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
GRAPHIFY_OUT = BASE_DIR / "graphify-out"
GRAPH_REPORT = GRAPHIFY_OUT / "GRAPH_REPORT.md"
GRAPH_DB = GRAPHIFY_OUT / "graph.json"

mcp = FastMCP("FishDex Codebase", instructions="""
I can search, read, and analyze the FishDex codebase.
- read_file: read any source file
- search_code: search with regex across all files
- project_structure: view directory tree
- query_graph: ask via the knowledge graph
- list_files: find files by glob pattern
""")


@mcp.tool()
def read_file(path: str, max_chars: int = 100_000) -> str:
    """Read a file from the FishDex codebase.
    
    Args:
        path: Relative path from project root (e.g. 'ai-server/app/main.py')
        max_chars: Maximum characters to return
    """
    full = _resolve(path)
    if full is None:
        return f"Error: path '{path}' is outside the project directory"
    if not full.exists() or not full.is_file():
        return f"Error: file not found: {path}"
    try:
        content = full.read_text(encoding="utf-8")
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n... (truncated, file is {len(content)} chars)"
        return content
    except Exception as e:
        return f"Error reading {path}: {e}"


@mcp.tool()
def search_code(pattern: str, include: str = "*", path: Optional[str] = None) -> str:
    """Search the codebase using ripgrep or grep.

    Args:
        pattern: Regex or literal string to search for
        include: File glob (e.g. '*.py', '*.dart')
        path: Subdirectory to search in (e.g. 'ai-server', 'fishdex/lib')
    """
    search_dir = BASE_DIR
    if path:
        search_dir = search_dir / path
        if not search_dir.is_dir():
            return f"Error: directory not found: {path}"

    out = _run(["rg", "-n", "--no-heading", pattern, "-g", include, "."], search_dir, 30)
    if not out:
        out = _run(["grep", "-rn", pattern, "--include", include, "."], search_dir, 30)
    if not out:
        return f"No matches for '{pattern}' in {include} files"
    if len(out) > 80_000:
        out = out[:80_000] + f"\n\n... (truncated)"
    return out


@mcp.tool()
def project_structure(depth: int = 3, path: Optional[str] = None) -> str:
    """Get the project directory tree.

    Args:
        depth: How deep to traverse (default 3)
        path: Subdirectory to inspect
    """
    target = BASE_DIR
    if path:
        target = target / path
        if not target.is_dir():
            return f"Error: directory not found: {path}"

    out = _run([
        "find", ".", "-maxdepth", str(depth),
        "-not", "-path", "*/node_modules/*",
        "-not", "-path", "*/.git/*",
        "-not", "-path", "*/__pycache__/*",
        "-not", "-path", "*/.dart_tool/*",
        "-not", "-path", "*/build/*",
        "-not", "-path", "*/venv/*",
        "-not", "-path", "*/graphify-out/*",
    ], target, 10)
    return out or "No files found"


@mcp.tool()
def list_files(pattern: str, path: Optional[str] = None) -> str:
    """Find files matching a glob pattern.

    Args:
        pattern: Glob like '**/*.py' or '**/*.dart'
        path: Subdirectory to search in
    """
    search_dir = BASE_DIR
    if path:
        search_dir = search_dir / path

    matches = sorted(search_dir.glob(pattern))
    matches = [m for m in matches if not any(
        p.name in ("node_modules", ".git", "__pycache__", ".dart_tool", "build", "venv")
        for p in m.relative_to(search_dir).parents
    )]
    if not matches:
        return f"No files matching '{pattern}'"
    lines = [str(m.relative_to(BASE_DIR)) for m in matches]
    if len(lines) > 500:
        lines = lines[:500] + [f"\n... ({len(matches)} total, showing 500)"]
    return "\n".join(lines)


@mcp.tool()
def query_graph(question: str) -> str:
    """Query the graphify knowledge graph about the codebase.

    Args:
        question: Natural language question (e.g. 'how does offline sync work?')
    """
    out = _run(["graphify", "query", question], BASE_DIR, 30)
    if out:
        return out
    if GRAPH_DB.exists():
        try:
            data = json.loads(GRAPH_DB.read_text())
            return (
                f"Graph has {len(data.get('nodes', []))} nodes, "
                f"{len(data.get('communities', []))} communities.\n"
                "Try a simpler query or use search_code."
            )
        except (ValueError, OSError) as exc:
            logger.warning("Could not read graph database %s: %s", GRAPH_DB, exc)
    return "graphify not available. Use search_code or read_file instead."


@mcp.tool()
def get_graph_report() -> str:
    """Read the full graphify architecture report."""
    if GRAPH_REPORT.exists():
        content = GRAPH_REPORT.read_text(encoding="utf-8")
        if len(content) > 100_000:
            content = content[:100_000] + "\n\n... (truncated)"
        return content
    return "No GRAPH_REPORT.md. Run 'graphify update .' first."


@mcp.tool()
def get_file_info(path: str) -> str:
    """Get metadata about a file or directory.

    Args:
        path: Relative path from project root
    """
    full = _resolve(path)
    if full is None:
        return f"Error: path '{path}' is outside the project directory"
    if not full.exists():
        return f"Error: not found: {path}"

    if full.is_dir():
        dirs = sum(1 for _ in full.iterdir() if _.is_dir())
        files = sum(1 for _ in full.iterdir() if _.is_file())
        return f"📁 {path}/ — {dirs} dirs, {files} files"

    stat = full.stat()
    suffix = full.suffix.lower()
    if suffix in (".py", ".dart", ".js", ".ts", ".md", ".yaml", ".yml", ".json", ".sql", ".html", ".css"):
        lines = full.read_text(encoding="utf-8").count("\n") + 1
    else:
        lines = "N/A"

    size = stat.st_size
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            size_str = f"{size:.1f} {unit}"
            break
        size /= 1024
    else:
        size_str = f"{size:.1f} GB"

    return f"File: {path}\nSize: {size_str}\nLines: {lines}"


# ── Helpers ───────────────────────────────────────────────────────────

def _resolve(path: str) -> Optional[Path]:
    """
    Resolve a repository-relative path, refusing traversal and secret files.

    Args:
        path: Path relative to the project root.

    Returns:
        The absolute path, or None when it escapes the project root or names a
        file that may hold credentials.
    """
    try:
        full = (BASE_DIR / path).resolve()
        full.relative_to(BASE_DIR.resolve())
    except (ValueError, OSError):
        return None

    if _is_sensitive(full):
        logger.warning("Refused MCP read of sensitive path: %s", path)
        return None
    return full


# Filenames and directories that may contain credentials. Path traversal is
# already blocked, but that only stops reads *outside* the repository — the
# repository itself contains .env files and key material.
_SENSITIVE_NAMES = frozenset(
    {
        "credentials.json",
        "id_rsa",
        "id_ed25519",
        "service-account.json",
        "secrets.yaml",
        "secrets.yml",
    }
)
_SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".keystore", ".jks")
_SENSITIVE_DIRS = frozenset({".git", "node_modules", ".venv", "venv"})


def _is_sensitive(full: Path) -> bool:
    """
    Report whether a path should never be served to an MCP client.

    Args:
        full: Absolute, already-resolved path.

    Returns:
        True when the path looks like credential material or private plumbing.
        ``.env.example`` is allowed because it holds only placeholders.
    """
    name = full.name.lower()

    if name.startswith(".env") and not name.endswith((".example", ".sample", ".template")):
        return True
    if name in _SENSITIVE_NAMES:
        return True
    if name.endswith(_SENSITIVE_SUFFIXES):
        return True
    return any(part in _SENSITIVE_DIRS for part in full.parts)


def _run(cmd: list[str], cwd: Path, timeout: int) -> str:
    """
    Run a helper command and return its stdout.

    Args:
        cmd: Argument vector. Passed as a list, never through a shell, so a
            hostile pattern cannot inject additional commands.
        cwd: Working directory.
        timeout: Seconds before the command is killed.

    Returns:
        Trimmed stdout, or an empty string when the command failed or is absent.
    """
    try:
        result = subprocess.run(  # noqa: S603 — argument vector, shell=False
            cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        logger.warning("Command timed out after %ds: %s", timeout, cmd[0])
        return ""
    except FileNotFoundError:
        logger.info("Command not installed, skipping: %s", cmd[0])
        return ""
    except OSError as exc:
        logger.warning("Command %s failed: %s", cmd[0], exc)
        return ""

    if result.returncode != 0 and result.stderr:
        logger.debug("%s exited %d: %s", cmd[0], result.returncode, result.stderr[:200])
    return result.stdout.strip()


# ── Entrypoint ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import os

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    parser = argparse.ArgumentParser(description="FishDex MCP codebase server")
    parser.add_argument(
        "--host",
        # SECURITY: bind to loopback by default. This server grants read access to
        # every file in the repository and has no authentication of its own, so it
        # must not listen on all interfaces. Expose it through an authenticated
        # tunnel (e.g. `cloudflared tunnel --url http://localhost:8001`) instead.
        default=os.environ.get("FISHDEX_MCP_HOST", "127.0.0.1"),
        help="Interface to bind (default: 127.0.0.1; set 0.0.0.0 only behind a "
        "trusted, authenticated proxy)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("FISHDEX_MCP_PORT", "8001")),
        help="Port to listen on (default: 8001)",
    )
    args = parser.parse_args()

    if args.host not in ("127.0.0.1", "localhost", "::1"):
        logger.warning(
            "MCP server is binding to %s. It exposes the whole repository with no "
            "authentication — make sure an authenticated proxy sits in front of it.",
            args.host,
        )

    logger.info("Starting FishDex MCP Server on http://%s:%d", args.host, args.port)
    logger.info("Tunnel it with: cloudflared tunnel --url http://localhost:%d", args.port)
    mcp.run(transport="sse", host=args.host, port=args.port)
