@echo off
echo Starting FishDex AI Server locally...
cd /d %~dp0
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate
echo Installing dependencies...
pip install fastapi==0.115.0 uvicorn[standard]==0.30.6 python-multipart==0.0.9 ^
    opencv-python==4.10.0.84 numpy==1.26.4 Pillow==10.4.0 ^
    torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cpu ^
    python-dotenv==1.0.1 pydantic==2.9.1 pydantic-settings==2.5.2 httpx==0.27.2 ^
    onnxruntime==1.19.2 scipy==1.13.1
echo.
echo Server starting at http://0.0.0.0:8000
echo Docs available at http://localhost:8000/docs
echo.
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
