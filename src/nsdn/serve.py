"""Static file server."""

from __future__ import annotations

import http.server
import logging
import os
import signal
import socketserver
import sys
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that logs to our logger instead of stderr."""

    def log_message(self, format: str, *args: object) -> None:
        logger.info("%s - - %s", self.address_string(), format % args)


def run_serve(directory: str, port: int = 8080, host: str = "0.0.0.0") -> None:
    """Run a static HTTP server."""
    dir_path = Path(directory)
    if not dir_path.is_dir():
        logger.error("Directory not found: %s", dir_path)
        return

    os.chdir(dir_path)

    handler = QuietHandler
    handler.directory = str(dir_path)

    # Allow address reuse
    socketserver.TCPServer.allow_reuse_address = True

    with socketserver.TCPServer((host, port), handler) as httpd:
        logger.info("Serving %s on http://%s:%d", dir_path, host, port)
        logger.info("Press Ctrl+C to stop")

        # Handle graceful shutdown
        def shutdown(signum: int, frame: object) -> None:
            logger.info("Shutting down...")
            httpd.shutdown()
            sys.exit(0)

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Server stopped")
