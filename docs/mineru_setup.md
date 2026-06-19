# MinerU cloud API setup

OmniLit sends the selected local PDF directly to the official MinerU cloud API.
It no longer requires a local MinerU CLI, model, Python environment, or runtime
bootstrap.

Open **System settings > PDF cloud parsing services**, enable MinerU, and save:

- API URL: `https://mineru.net/api/v4`
- API token: the token created in MinerU API management

On Windows the token is protected with DPAPI before it is written to the local
settings database. It is never stored in extraction indexes or logs. The
environment variables below take precedence over saved settings:

```powershell
$env:OMNILIT_MINERU_API_TOKEN = "..."
$env:OMNILIT_MINERU_API_URL = "https://mineru.net/api/v4"
```

For compatibility with existing development machines, OmniLit performs a
one-time import from `D:\Tool\Java\API\Mineru.txt` when no MinerU token is
configured. The plaintext file is not copied into the repository or deleted.

The reader requests an upload URL, uploads the PDF, polls the batch task,
downloads the result archive, and normalizes figures, tables, and formulas into
the version 3 extraction index. API failure leaves the PyMuPDF result usable.
