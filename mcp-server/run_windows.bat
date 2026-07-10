@echo off
echo ====================================================
echo  FishDex MCP Server — para Make.com
echo ====================================================
cd /d %~dp0
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate
echo Installing dependencies...
pip install mcp>=1.0.0 starlette>=0.37.0 uvicorn[standard]>=0.30.0
echo.
echo Starting MCP server on http://0.0.0.0:8001
echo SSE endpoint: http://0.0.0.0:8001/mcp
echo.
echo To expose to Make.com, run in another terminal:
echo   cloudflared tunnel --url http://localhost:8001
echo.
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
pause
