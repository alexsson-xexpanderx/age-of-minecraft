@echo off
rem Age of Minecraft - crash test 1: the trains' rails, with the old horse cart look, and nothing else of the mod.
rem Just double-click this file. It finds your game like build_mod.bat does.
rem Afterwards, double-click build_mod.bat to get the whole mod back.
py -3 -m pip install --quiet --user numpy
py -3 "%~dp0tools\build_mod.py" --only rails
pause
