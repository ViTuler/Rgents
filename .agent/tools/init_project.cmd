@echo off
REM Initialize local git for an Rgents project (no remote). See init_project.py.
set SCRIPT_DIR=%~dp0
python "%SCRIPT_DIR%init_project.py" %*
