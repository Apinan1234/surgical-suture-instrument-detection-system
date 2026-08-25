# Setup

This is a plain source copy — no virtualenv is included (venvs are large and regenerable, so they
aren't duplicated across copies of this project).

One-time setup:

```powershell
python -m venv .venv
.venv\Scripts\pip install -e .
```

To run the app, **always use `run_web.ps1`**, never `python frontend\app.py` directly:

```powershell
.\run_web.ps1
```

`run_web.ps1` sets `$env:PYTHONUTF8 = "1"` before launching Python, which is required for correct
handling of Thai filenames/text in video uploads — this can't be set correctly from inside
`app.py` itself, since it must be in place before the interpreter starts.

The app serves at `http://127.0.0.1:7860`.
