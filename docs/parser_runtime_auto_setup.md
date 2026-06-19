# PDF parser service configuration

The literature reader exposes three explicit modes:

- **PyMuPDF** performs fast local extraction and never uploads the PDF.
- **MinerU** calls the configured MinerU cloud API and merges its figure, table,
  and formula results with the PyMuPDF base index.
- **PaddleOCR-VL** calls the configured official layout parsing API and merges
  its result with the PyMuPDF base index.

The cloud engines are selected manually and never invoke each other. If the
selected API is unavailable, rejects the request, exceeds its quota, times out,
or is cancelled, OmniLit retains the local PyMuPDF result.

Configure both APIs under **System settings > PDF cloud parsing services**.
Tokens are encrypted with the operating system credential protection on
Windows, can be cleared independently, and are always redacted from logs and
status messages. Environment variables take precedence over saved settings.

Cloud results carry the cache marker `cloud-api-v1`. Older local CLI/runtime
results are ignored when a cloud engine is selected, while existing PyMuPDF
caches remain valid.
