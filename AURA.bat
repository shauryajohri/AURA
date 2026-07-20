@echo off
rem ============================================================
rem  AURA launcher — double-click and she wakes up.
rem  Builds the face once if needed, then starts Electron,
rem  which boots the Python brain itself (see electron/main.cjs).
rem ============================================================
title AURA
cd /d "%~dp0frontend"

rem first run (or after UI changes): build the production face
if not exist "dist\index.html" (
    echo [AURA] First launch - building the face, one moment...
    call npm run build
    if errorlevel 1 (
        echo.
        echo [AURA] Build failed. Run "npm install" inside the frontend folder once, then try again.
        pause
        exit /b 1
    )
)

set AURA_PROD=1
start "" "%~dp0frontend\node_modules\electron\dist\electron.exe" .
exit /b 0
