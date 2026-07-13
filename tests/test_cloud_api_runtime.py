from __future__ import annotations

import signal
import threading
import unittest
from unittest.mock import patch

from services.cloud_api.__main__ import _serve_until_stopped


class _FakeServer:
    def __init__(self) -> None:
        self.serving = threading.Event()
        self.stopped = threading.Event()
        self.closed = False

    def serve_forever(self, poll_interval: float) -> None:
        self.serving.set()
        if not self.stopped.wait(timeout=2):
            raise TimeoutError("shutdown signal was not handled")

    def shutdown(self) -> None:
        self.stopped.set()

    def server_close(self) -> None:
        self.closed = True


class CloudApiRuntimeTests(unittest.TestCase):
    def test_sigterm_requests_graceful_server_shutdown_and_restores_handlers(self) -> None:
        server = _FakeServer()
        handlers: dict[signal.Signals, object] = {}
        restored: list[tuple[signal.Signals, object]] = []

        def install(signum: signal.Signals, handler: object) -> None:
            if callable(handler):
                handlers[signum] = handler
            else:
                restored.append((signum, handler))

        def request_stop() -> None:
            self.assertTrue(server.serving.wait(timeout=1))
            handler = handlers[signal.SIGTERM]
            assert callable(handler)
            handler(signal.SIGTERM, None)

        trigger = threading.Thread(target=request_stop, daemon=True)
        trigger.start()
        with patch("services.cloud_api.__main__.signal.getsignal", return_value="previous"), patch("services.cloud_api.__main__.signal.signal", side_effect=install):
            _serve_until_stopped(server)
        trigger.join(timeout=1)

        self.assertTrue(server.stopped.is_set())
        self.assertTrue(server.closed)
        self.assertEqual(set(restored), {(signal.SIGINT, "previous"), (signal.SIGTERM, "previous")})


if __name__ == "__main__":
    unittest.main()
