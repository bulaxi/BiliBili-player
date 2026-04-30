$ErrorActionPreference = 'Stop'

$python = 'C:\mini\envs\bili-player311\python.exe'

& $python -m pip install pyinstaller
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --name 'BiliMusicPlayer' `
  --paths '.' `
  --add-data 'downloads;downloads' `
  run_app.py

exit $LASTEXITCODE
