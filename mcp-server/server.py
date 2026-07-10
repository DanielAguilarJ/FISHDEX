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
        except Exception:
            pass
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
    try:
        full = (BASE_DIR / path).resolve()
        full.relative_to(BASE_DIR.resolve())
        return full
    except (ValueError, OSError):
        return None


def _run(cmd: list[str], cwd: Path, timeout: int) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)
        return r.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


# ── Entrypoint ────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Starting FishDex MCP Server on http://0.0.0.0:8001 ...")
    print("Make.com MCP Client URL → http://<your-ip>:8001")
    mcp.run(transport="sse", host="0.0.0.0", port=8001)
