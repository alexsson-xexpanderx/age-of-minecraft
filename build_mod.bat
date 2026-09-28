@echo off
rem Age of Minecraft - builds the mod from your own Age of Empires II install.
rem Just double-click this file. It finds your game, or asks you to paste the game folder's path.
rem You can also pass the folder and options, e.g.
rem     build_mod.bat "C:\Program Files (x86)\Microsoft Games\Age of Empires II" --only militia,archer
py -3 -m pip install --quiet --user numpy
if "%~1"=="" (
  py -3 "%~dp0tools\build_mod.py"
) else (
  py -3 "%~dp0tools\build_mod.py" --game "%~1" %2 %3 %4 %5 %6
)
pause
