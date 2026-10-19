@echo off
rem sp.cmd - the launcher on Windows: runs sp.py (see it for the commands).
rem   sp up [--dev] ^| down ^| restart ^| status ^| logs ^| terminal on^|off ^| run [--prod]
rem   sp open ^| autostart on^|off ^| shortcut [off]
rem The exit code is sp.py's own: a script can tell "not running" from "running".
setlocal
cd /d "%~dp0"
where py >nul 2>nul && goto :py
rem "python" may be the Microsoft Store alias, which opens the Store instead
rem of running anything: hand over only when it really runs Python.
where python >nul 2>nul && python -c "import sys" >nul 2>nul && goto :python
echo [sp] ERROR: Python 3.11+ not found - install it from https://www.python.org 1>&2
exit /b 1
:py
py -3 sp.py %*
exit /b %errorlevel%
:python
python sp.py %*
exit /b %errorlevel%
