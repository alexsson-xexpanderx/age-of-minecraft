@echo off
rem Age of Minecraft - crash test 2: the new train look, without rails, and nothing else of the mod.
rem Just double-click this file. It finds your game like build_mod.bat does.
rem Afterwards, double-click build_mod.bat to get the whole mod back.
py -3 -m pip install --quiet --user numpy
py -3 "%~dp0tools\build_mod.py" --only trade_cart
pause
