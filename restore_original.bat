@echo off
rem Age of Minecraft - undoes build_mod_direct.bat: puts your original graphics back.
py -3 "%~dp0tools\build_mod.py" --restore %*
pause
