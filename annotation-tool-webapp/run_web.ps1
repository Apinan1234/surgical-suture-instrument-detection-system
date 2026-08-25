# Always launch frontend/app.py through this script, never `python frontend\app.py` directly.
# PYTHONUTF8 must be set in the process environment BEFORE the interpreter starts -- it can't be
# set from inside app.py -- same fix already proven against Thai-filename upload corruption in
# yolo-frame-miner's Gradio multipart parsing; this project hits the same code path.
$env:PYTHONUTF8 = "1"
& "$PSScriptRoot\.venv\Scripts\python.exe" "$PSScriptRoot\frontend\app.py"
