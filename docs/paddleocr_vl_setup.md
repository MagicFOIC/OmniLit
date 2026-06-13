# PaddleOCR-VL setup for OmniLit

OmniLit does not install PaddleOCR-VL, PaddlePaddle, vLLM, or related model
dependencies in the main application environment. The main app calls
PaddleOCR-VL through an external Python worker, so the app can still start and
tests can still pass when PaddleOCR-VL is not installed.

## Enable the adapter

Set these environment variables before starting OmniLit:

```powershell
$env:OMNILIT_PADDLEOCR_VL_ENABLED = "1"
$env:OMNILIT_PADDLEOCR_VL_MODE = "service"
$env:OMNILIT_PADDLEOCR_VL_URL = "http://127.0.0.1:8118/v1"
$env:OMNILIT_PADDLEOCR_VL_MODEL = "PaddlePaddle/PaddleOCR-VL-1.6"
$env:OMNILIT_PADDLEOCR_VL_PIPELINE_VERSION = "v1.6"
$env:OMNILIT_PADDLEOCR_VL_PYTHON = "D:\Tool\Python\project\OmniLit\.venv_paddleocr\Scripts\python.exe"
$env:OMNILIT_PADDLEOCR_VL_TIMEOUT = "900"
```

`OMNILIT_PADDLEOCR_VL_MODE` can be `service` or `subprocess`.

## CPU/local Python environment

```powershell
python -m venv .venv_paddleocr
.venv_paddleocr\Scripts\activate
python -m pip install paddlepaddle==3.2.1 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
python -m pip install -U "paddleocr[doc-parser]"
```

Then point OmniLit at that interpreter:

```powershell
$env:OMNILIT_PADDLEOCR_VL_ENABLED = "1"
$env:OMNILIT_PADDLEOCR_VL_MODE = "subprocess"
$env:OMNILIT_PADDLEOCR_VL_PYTHON = "D:\Tool\Python\project\OmniLit\.venv_paddleocr\Scripts\python.exe"
```

## GPU/vLLM service example

```powershell
python -m venv .venv_vlm
.venv_vlm\Scripts\activate
python -m pip install "paddleocr[doc-parser]"
paddleocr install_genai_server_deps vllm
paddleocr genai_server --model_name PaddleOCR-VL-1.6-0.9B --backend vllm --port 8118
```

Then run OmniLit with:

```powershell
$env:OMNILIT_PADDLEOCR_VL_ENABLED = "1"
$env:OMNILIT_PADDLEOCR_VL_MODE = "service"
$env:OMNILIT_PADDLEOCR_VL_URL = "http://127.0.0.1:8118/v1"
$env:OMNILIT_PADDLEOCR_VL_PYTHON = "D:\Tool\Python\project\OmniLit\.venv_vlm\Scripts\python.exe"
```

The worker command OmniLit runs is equivalent to:

```powershell
python -m omnilit_qt.tools.paddleocr_vl_worker --input paper.pdf --output out --server-url http://127.0.0.1:8118/v1 --model PaddlePaddle/PaddleOCR-VL-1.6 --pipeline-version v1.6 --engine server --merge-tables --relevel-titles
```
