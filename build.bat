@echo off
rem Builds dist\installer\Attendance Manager Setup.exe  (see scripts\build.ps1 for options)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build.ps1" %*
exit /b %ERRORLEVEL%
