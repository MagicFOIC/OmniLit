from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from omnilit_qt.paths import AppPaths

from .http_server import create_local_agent_server


def main() -> int:
    parser = argparse.ArgumentParser(description="OmniLit loopback-only Local Agent")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--origin", action="append", default=[])
    parser.add_argument("--web-root", default="")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    server = create_local_agent_server(data_root=AppPaths.discover().data_root, host=args.host, port=args.port, token=os.getenv("OMNILIT_LOCAL_AGENT_TOKEN") or None, allowed_origins=set(args.origin), web_root=Path(args.web_root) if args.web_root else None)
    logging.getLogger("omnilit.local_agent").info("local_agent_ready host=%s port=%s", server.server_address[0], server.server_address[1])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
