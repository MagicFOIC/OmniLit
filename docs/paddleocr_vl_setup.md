# PaddleOCR-VL cloud API setup

OmniLit calls the official PaddleOCR document layout parsing API directly. A
local PaddleOCR installation, model server, Docker container, and separate
Python environment are not required by the reader.

Open **System settings > PDF cloud parsing services**, enable PaddleOCR-VL, and
save:

- API URL: `https://paddleocr.aistudio-app.com/api/v2/ocr/jobs`
- API token: the token issued by the official online API

On Windows the token is protected with DPAPI. The following environment
variables override saved settings:

```powershell
$env:OMNILIT_PADDLEOCR_VL_API_KEY = "..."
$env:OMNILIT_PADDLEOCR_VL_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
```

For managed deployments, set these variables in the launcher or service
configuration before starting OmniLit. Do not place the token in the source
tree or application package. If no environment token is present, users can
still save their own encrypted token in system settings.

OmniLit uploads the PDF as multipart form data with model
`PaddleOCR-VL-1.6`, polls the returned job, then downloads its JSONL, Markdown,
and images into the document's PaddleOCR engine cache. Tables, formulas, and
figures are normalized into the same version 3 extraction index used by the
reader. API failure falls back to the PyMuPDF result.
