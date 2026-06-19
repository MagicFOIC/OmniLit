# PaddleOCR-VL cloud API setup

OmniLit calls the official PaddleOCR document layout parsing API directly. A
local PaddleOCR installation, model server, Docker container, and separate
Python environment are not required by the reader.

Open **System settings > PDF cloud parsing services**, enable PaddleOCR-VL, and
save:

- API URL: copy the endpoint shown by the **API** panel at
  `https://aistudio.baidu.com/paddleocr`
- API token: the token issued by the official online API

On Windows the token is protected with DPAPI. The following environment
variables override saved settings:

```powershell
$env:OMNILIT_PADDLEOCR_VL_API_KEY = "..."
$env:OMNILIT_PADDLEOCR_VL_URL = "https://your-issued-endpoint"
```

OmniLit performs a one-time import from
`D:\Tool\Java\API\PaddleOCR.txt` when no saved token exists. The source file is
not copied or deleted.

The API response, Markdown, and returned images are saved under the document's
PaddleOCR engine cache. Tables, formulas, and figures are normalized into the
same version 3 extraction index used by the reader. API failure falls back to
the PyMuPDF result.
