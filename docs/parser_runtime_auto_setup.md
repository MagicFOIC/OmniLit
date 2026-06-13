# OmniLit Parser Runtime Auto Setup

OmniLit keeps the main `OmniLit` conda environment lightweight. The built-in fast parser uses PyMuPDF and is always the default safe fallback.

## Default Behavior

- Fast parsing uses PyMuPDF inside the main app environment.
- Auto parsing first looks for a running PaddleOCR-VL service, then local PaddleOCR-VL runtimes or CLI tools.
- If PaddleOCR-VL is not initialized, OmniLit falls back to MinerU.
- MinerU is initialized on first deep parse by creating an isolated runtime under the user app-data directory and installing `mineru[all]` there with `uv`.
- If all deep engines fail, OmniLit keeps the PyMuPDF result so the reader remains usable.

## Managed Runtime Location

Windows:

```text
%LOCALAPPDATA%\OmniLit\parser_runtimes\
```

macOS:

```text
~/Library/Application Support/OmniLit/parser_runtimes/
```

Linux:

```text
~/.local/share/OmniLit/parser_runtimes/
```

MinerU is installed into:

```text
parser_runtimes/mineru/.venv/
```

The main `environment.yml` does not install MinerU or PaddleOCR-VL directly.

## PaddleOCR-VL

PaddleOCR-VL is not auto-installed on first app start because it is large and may need GPU, CUDA, Docker, vLLM, or a dedicated service. OmniLit auto-detects:

- `OMNILIT_PADDLEOCR_VL_URL`
- `http://127.0.0.1:8118/v1`
- managed runtime metadata
- `paddleocr` on `PATH`
- Docker availability

Advanced users can still set environment variables, for example:

```powershell
set OMNILIT_PADDLEOCR_VL_MODE=service
set OMNILIT_PADDLEOCR_VL_URL=http://127.0.0.1:8118/v1
set OMNILIT_PADDLEOCR_VL_PYTHON=D:\Tool\anaconda3\envs\OmniLit-PaddleOCRVL\python.exe
```

API keys are read only from the environment and are not saved by OmniLit.

## Offline Use

If the computer is offline, MinerU auto-install may fail. In that case OmniLit shows a friendly fallback message and keeps the fast PyMuPDF result.

To prepare MinerU manually:

```powershell
conda create -n OmniLit-MinerU python=3.10 -y
conda activate OmniLit-MinerU
python -m pip install -U pip
python -m pip install uv
python -m uv pip install -U "mineru[all]"
```

Then either add `mineru` to `PATH` or configure the MinerU Python path in the app's parser engine settings.
