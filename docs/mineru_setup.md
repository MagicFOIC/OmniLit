# MinerU setup for OmniLit

OmniLit treats MinerU as an optional external parser. The main application
environment does not install `mineru` or its model dependencies. When MinerU is
not configured, OmniLit still starts normally and the extraction pipeline falls
back to PyMuPDF.

## Install in a separate environment

```powershell
python -m venv .venv_mineru
.venv_mineru\Scripts\activate
python -m pip install -U pip
python -m pip install uv
python -m uv pip install -U "mineru[all]"
```

Smoke test the CLI:

```powershell
mineru -p sample.pdf -o output
```

CPU fallback:

```powershell
mineru -p sample.pdf -o output -b pipeline
```

## Configure OmniLit

When the MinerU environment is separate from OmniLit's main environment, point
OmniLit at that Python runtime:

```powershell
$env:OMNILIT_MINERU_ENABLED = "1"
$env:OMNILIT_MINERU_MODE = "cli"
$env:OMNILIT_MINERU_PYTHON = "D:\Tool\Python\project\OmniLit\.venv_mineru\Scripts\python.exe"
$env:OMNILIT_MINERU_BACKEND = "pipeline"
$env:OMNILIT_MINERU_TIMEOUT = "900"
```

If `mineru` is directly available on `PATH`, a Python worker is optional:

```powershell
$env:OMNILIT_MINERU_ENABLED = "1"
$env:OMNILIT_MINERU_COMMAND = "mineru"
$env:OMNILIT_MINERU_BACKEND = "pipeline"
```

## API mode placeholder

MinerU also provides a FastAPI server:

```powershell
mineru-api --host 0.0.0.0 --port 8000
```

The OmniLit adapter keeps `OMNILIT_MINERU_MODE=api` and
`OMNILIT_MINERU_API_URL=http://127.0.0.1:8000` reserved for a later API
implementation. PR 3 implements the CLI/worker path.
