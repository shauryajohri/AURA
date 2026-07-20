' AURA silent launcher — runs AURA.bat with no console window.
' Point your desktop shortcut here (or run CREATE_DESKTOP_SHORTCUT.bat once).
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\") - 1)
sh.Run """" & sh.CurrentDirectory & "\AURA.bat""", 0, False
