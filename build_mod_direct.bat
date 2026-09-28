@echo off
rem Age of Minecraft - puts the Minecraft sprites straight into your normal game (no mod exe needed).
rem Your original Data\graphics.drs is backed up first; double-click restore_original.bat to undo.
py -3 -m pip install --quiet --user numpy
py -3 "%~dp0tools\build_mod.py" --mode direct %*
pause
