@echo off
setlocal
cd /d "%~dp0.."
set "PATH=C:\Program Files\Git\cmd;C:\Program Files\GitHub CLI;%PATH%"

"C:\Program Files\GitHub CLI\gh.exe" auth status
if errorlevel 1 (
  echo.
  echo Run first: gh auth login
  exit /b 1
)

git remote get-url origin >nul 2>&1
if errorlevel 1 (
  echo Creating private GitHub repo parlayvu-core ...
  "C:\Program Files\GitHub CLI\gh.exe" repo create parlayvu-core --private --source=. --remote=origin --description "ParlayVU.ai core"
)

echo Pushing main ...
git push -u origin main
if errorlevel 1 exit /b 1

echo.
echo Done. Remote:
git remote -v
