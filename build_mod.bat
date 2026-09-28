@echo off
rem Age of Minecraft - builds the mod from your own Age of Empires II install.
rem Drag your "Age of Empires II" folder onto this file, or run:
rem     build_mod.bat "C:\Program Files (x86)\Microsoft Games\Age of Empires II"
rem Extra options go after the folder, e.g.  --only militia,archer   or   --mode direct
if "%~1"=="" (
  echo Drag your Age of Empires II folder onto build_mod.bat, or pass its path.
  pause
  exit /b 1
)
py -3 -m pip install --quiet --user numpy
py -3 "%~dp0tools\build_mod.py" --game "%~1" %2 %3 %4 %5 %6
pause
