@echo off
REM Project-local Python launcher.
REM Points at the embedded Python 3.12.7 and adds the project root to PYTHONPATH.
set PYTHON_EXE=E:\HEX_HIVE\python.exe
set PYTHONPATH=%~dp0
set PYTHONPATH=%PYTHONPATH:~0,-1%
"%PYTHON_EXE%" %*
