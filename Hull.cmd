@echo off
setlocal
where py >nul 2>nul
if not errorlevel 1 (
  py -3.13 "%~dp0hull.py" %*
  exit /b
)
if exist "C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe" (
  "C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe" "%~dp0hull.py" %*
  exit /b
)
python "%~dp0hull.py" %*
