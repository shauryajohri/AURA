@echo off
rem ============================================================
rem  AURA WEB launcher - double-click to serve the website.
rem
rem  Starts web_api.py, the sandboxed public demo (FastAPI on
rem  127.0.0.1:8770), and opens the site in your default browser.
rem  It never starts server.py, so none of the private desktop
rem  API is served. Closing this window stops the server.
rem
rem  Runs alongside the desktop app: AURA.bat uses port 8760.
rem ============================================================
title AURA Web
cd /d "%~dp0"

if exist "venv\Scripts\activate.bat" (
    call "venv\Scripts\activate.bat"
) else (
    echo [AURA web] No venv found - using the system Python.
)

echo.
echo   AURA web  -  http://127.0.0.1:8770/
echo   demo API  -  http://127.0.0.1:8770/web/api/session
echo   Close this window to stop the server.
echo.

rem give uvicorn a moment to bind before the browser knocks
start "" /b cmd /c "timeout /t 3 /nobreak >nul & start """" http://127.0.0.1:8770/"

python web_api.py

echo.
echo [AURA web] Server stopped.
pause
