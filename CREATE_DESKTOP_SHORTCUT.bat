@echo off
rem Creates an "AURA" shortcut on your desktop (run this once).
powershell -NoProfile -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\AURA.lnk');" ^
  "$s.TargetPath='%~dp0AURA.vbs';" ^
  "$s.WorkingDirectory='%~dp0';" ^
  "$s.IconLocation='%~dp0frontend\electron\aura.ico';" ^
  "$s.Description='AURA — your AI companion';" ^
  "$s.Save()"
if errorlevel 1 (
    echo Could not create the shortcut.
) else (
    echo Done - AURA is on your desktop. Double-click her anytime.
)
pause
