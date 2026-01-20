#!/usr/bin/env python3
"""
Local Development Web Runner

Web-based UI for the ARRMS integration local development.
Provides a simple interface to send questionnaires and view webhook responses.

Usage:
    python scripts/local_web_runner.py
    python scripts/local_web_runner.py --port 8080 --env-file .env.local

Then open http://localhost:8080 in your browser.
"""

import argparse
import json
import logging
import os
import queue
import sys
import tempfile
import threading
import time
import traceback
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from local_runner import LocalARRMSClient, transform_record, load_env_file
from mock_onspring import MockOnspringClient

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("web_runner")

# Suppress noisy loggers
logging.getLogger("urllib3").setLevel(logging.WARNING)


class LogBuffer:
    """Thread-safe buffer for log messages that can be streamed via SSE."""

    def __init__(self, max_size: int = 1000):
        self.messages: List[Dict[str, Any]] = []
        self.max_size = max_size
        self.lock = threading.Lock()
        self.subscribers: List[queue.Queue] = []

    def add(self, level: str, message: str, data: Optional[Dict] = None):
        """Add a log message and notify subscribers."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            "data": data,
        }

        with self.lock:
            self.messages.append(entry)
            if len(self.messages) > self.max_size:
                self.messages = self.messages[-self.max_size:]

            # Notify all SSE subscribers
            for q in self.subscribers:
                try:
                    q.put_nowait(entry)
                except queue.Full:
                    pass

    def subscribe(self) -> queue.Queue:
        """Create a new subscriber queue for SSE."""
        q = queue.Queue(maxsize=100)
        with self.lock:
            self.subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue):
        """Remove a subscriber queue."""
        with self.lock:
            if q in self.subscribers:
                self.subscribers.remove(q)

    def get_recent(self, count: int = 50) -> List[Dict]:
        """Get recent log messages."""
        with self.lock:
            return self.messages[-count:]

    def info(self, message: str, data: Optional[Dict] = None):
        self.add("INFO", message, data)
        logger.info(message)

    def error(self, message: str, data: Optional[Dict] = None):
        self.add("ERROR", message, data)
        logger.error(message)

    def warning(self, message: str, data: Optional[Dict] = None):
        self.add("WARNING", message, data)
        logger.warning(message)

    def debug(self, message: str, data: Optional[Dict] = None):
        self.add("DEBUG", message, data)
        logger.debug(message)

    def webhook(self, message: str, data: Optional[Dict] = None):
        """Special log level for webhook events."""
        self.add("WEBHOOK", message, data)
        logger.info(f"[WEBHOOK] {message}")


# Global log buffer
log_buffer = LogBuffer()

# Cached ARRMS status (updated in background)
arrms_status_cache = {
    "connected": False,
    "error": "Not checked yet",
    "last_check": None
}


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """HTTP server that handles each request in a separate thread."""
    daemon_threads = True


class WebRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the web UI."""

    # Class-level references (set by main)
    arrms_client: Optional[LocalARRMSClient] = None
    mock_client: Optional[MockOnspringClient] = None
    web_ui_path: str = ""

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

    def send_json(self, data: Any, status: int = 200):
        """Send JSON response."""
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
        except BrokenPipeError:
            pass  # Client disconnected, ignore

    def send_html(self, content: str):
        """Send HTML response."""
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(content.encode())
        except BrokenPipeError:
            pass  # Client disconnected, ignore

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        try:
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
        except BrokenPipeError:
            pass

    def do_GET(self):
        """Handle GET requests."""
        try:
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/" or path == "/index.html":
                self.serve_ui()
            elif path == "/api/logs":
                self.serve_logs()
            elif path == "/api/logs/stream":
                self.serve_sse()
            elif path == "/api/status":
                self.serve_status()
            elif path == "/health":
                self.send_json({"status": "ok"})
            else:
                self.send_response(404)
                self.end_headers()
        except BrokenPipeError:
            pass  # Client disconnected

    def do_POST(self):
        """Handle POST requests."""
        try:
            parsed = urlparse(self.path)
            path = parsed.path

            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""

            try:
                payload = json.loads(body) if body else {}
            except json.JSONDecodeError:
                payload = {}

            if path == "/api/send":
                self.handle_send(payload)
            elif path == "/api/stats":
                self.handle_stats(payload)
            elif path == "/api/apikey":
                self.handle_apikey_update(payload)
            elif path == "/webhook/arrms":
                self.handle_webhook(payload)
            else:
                self.send_json({"error": "Not found"}, 404)
        except BrokenPipeError:
            pass  # Client disconnected

    def serve_ui(self):
        """Serve the main HTML UI."""
        html_path = os.path.join(self.web_ui_path, "index.html")
        try:
            with open(html_path, "r") as f:
                self.send_html(f.read())
        except FileNotFoundError:
            self.send_html("<h1>UI not found</h1><p>Missing: " + html_path + "</p>")

    def serve_logs(self):
        """Serve recent logs as JSON."""
        logs = log_buffer.get_recent(100)
        self.send_json({"logs": logs})

    def serve_status(self):
        """Serve current status from cache (non-blocking)."""
        try:
            arrms_url = os.environ.get("ARRMS_API_URL", "not configured")
            mock_client = WebRequestHandler.mock_client
            arrms_client = WebRequestHandler.arrms_client

            # Get masked API key (last 4 chars)
            api_key_masked = None
            if arrms_client and arrms_client.api_key:
                key = arrms_client.api_key
                if len(key) > 4:
                    api_key_masked = "****" + key[-4:]
                else:
                    api_key_masked = "****"

            status = {
                "arrms_connected": arrms_status_cache["connected"],
                "arrms_url": arrms_url,
                "arrms_error": arrms_status_cache["error"],
                "arrms_api_key_masked": api_key_masked,
                "mock_records": len(mock_client.records) if mock_client else 0,
            }
            self.send_json(status)
        except Exception as e:
            self.send_json({"arrms_connected": False, "arrms_error": str(e)})

    def serve_sse(self):
        """Serve Server-Sent Events stream for real-time logs."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        # Subscribe to log updates
        subscriber = log_buffer.subscribe()

        try:
            # Send initial connection event
            self.wfile.write(b"event: connected\ndata: {}\n\n")
            self.wfile.flush()

            while True:
                try:
                    # Wait for new log entry
                    entry = subscriber.get(timeout=30)
                    data = json.dumps(entry)
                    self.wfile.write(f"event: log\ndata: {data}\n\n".encode())
                    self.wfile.flush()
                except queue.Empty:
                    # Send keepalive
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            log_buffer.unsubscribe(subscriber)

    def handle_send(self, payload: Dict):
        """Handle send questionnaire request."""
        record_id = payload.get("record_id", 12345)
        app_id = payload.get("app_id", 100)

        print(f"[DEBUG] handle_send called: record_id={record_id}, app_id={app_id}")
        log_buffer.info(f"Starting send flow for record {record_id}")

        # Capture client references for thread
        arrms_client = self.arrms_client
        mock_client = self.mock_client

        # Run in background thread to not block
        def send_task():
            print(f"[DEBUG] send_task started")
            try:
                self._run_send_flow(record_id, app_id, arrms_client, mock_client)
            except Exception as e:
                tb = traceback.format_exc()
                print(f"[ERROR] Send flow failed: {e}\n{tb}")
                log_buffer.error(f"Send flow failed: {str(e)}", {"traceback": tb})

        thread = threading.Thread(target=send_task, daemon=True)
        thread.start()

        self.send_json({"status": "started", "record_id": record_id})

    def _run_send_flow(self, record_id: int, app_id: int, arrms_client, mock_client):
        """Execute the send questionnaire flow."""
        print(f"[DEBUG] _run_send_flow started")
        log_buffer.info(f"Fetching record {record_id} from mock Onspring")

        # Get record from mock
        record_data = mock_client.get_record(app_id=app_id, record_id=record_id)
        log_buffer.info(f"Got record: {record_data.get('fields', {}).get('Title', {}).get('value', 'Unknown')}")

        # Transform
        transformed = transform_record(record_data)
        log_buffer.debug("Transformed record data", transformed)

        # Get files
        files = mock_client.get_record_files(record_data)
        if not files:
            log_buffer.error("No files found in record")
            return

        log_buffer.info(f"Found {len(files)} files in record")

        # Download questionnaire
        questionnaire_file = files[0]
        file_content = mock_client.download_file(
            record_id=questionnaire_file["record_id"],
            field_id=questionnaire_file["field_id"],
            file_id=questionnaire_file["file_id"],
        )

        # Save to temp file
        file_name = questionnaire_file.get("file_name", "questionnaire.xlsx")
        _, file_ext = os.path.splitext(file_name)
        if not file_ext:
            file_ext = ".xlsx"

        with tempfile.NamedTemporaryFile(mode="wb", suffix=file_ext, delete=False) as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name

        log_buffer.info(f"Saved questionnaire to temp file ({len(file_content)} bytes)")

        try:
            # Check for existing questionnaire
            log_buffer.info("Checking for existing questionnaire in ARRMS...")
            existing = arrms_client.find_questionnaire_by_external_id(
                external_id=str(record_id),
                external_source="onspring",
            )

            if existing:
                arrms_id = existing.get("id")
                log_buffer.info(f"Found existing questionnaire {arrms_id}, updating...")

                result = arrms_client.update_questionnaire_file(
                    questionnaire_id=arrms_id,
                    file_path=temp_file_path,
                    external_metadata=transformed.get("external_metadata", {}),
                )
                log_buffer.info(f"Updated questionnaire {arrms_id}", {"result": result})
            else:
                log_buffer.info("No existing questionnaire, creating new...")

                result = arrms_client.upload_questionnaire(
                    file_path=temp_file_path,
                    external_id=str(record_id),
                    external_source="onspring",
                    external_metadata=transformed.get("external_metadata", {}),
                )
                arrms_id = result.get("id")
                log_buffer.info(f"Created questionnaire {arrms_id}", {"result": result})

            log_buffer.info(f"Send flow completed successfully for record {record_id}")

        finally:
            os.unlink(temp_file_path)

    def handle_stats(self, payload: Dict):
        """Handle get statistics request."""
        record_id = payload.get("record_id", 12345)

        print(f"[DEBUG] handle_stats called: record_id={record_id}")
        log_buffer.info(f"Fetching statistics for record {record_id}")

        # Capture client reference for thread
        arrms_client = self.arrms_client

        # Run in background thread to not block
        def stats_task():
            print(f"[DEBUG] stats_task started")
            try:
                stats = arrms_client.get_questionnaire_statistics(
                    external_id=str(record_id),
                    external_source="onspring",
                )
                summary = stats.get("summary", {})
                log_buffer.info(
                    f"Stats: {summary.get('approved_questions', 0)}/{summary.get('total_questions', 0)} approved, "
                    f"{summary.get('answered_questions', 0)} answered",
                    stats
                )
            except Exception as e:
                tb = traceback.format_exc()
                print(f"[ERROR] Stats failed: {e}\n{tb}")
                log_buffer.error(f"Failed to get statistics: {str(e)}", {"traceback": tb})

        thread = threading.Thread(target=stats_task, daemon=True)
        thread.start()

        self.send_json({"status": "started", "record_id": record_id})

    def handle_apikey_update(self, payload: Dict):
        """Handle API key update request."""
        new_key = payload.get("api_key", "").strip()

        if not new_key:
            self.send_json({"status": "error", "error": "No API key provided"}, 400)
            return

        arrms_client = WebRequestHandler.arrms_client
        if not arrms_client:
            self.send_json({"status": "error", "error": "ARRMS client not initialized"}, 500)
            return

        # Update the API key
        old_key_masked = "****" + arrms_client.api_key[-4:] if len(arrms_client.api_key) > 4 else "****"
        new_key_masked = "****" + new_key[-4:] if len(new_key) > 4 else "****"

        arrms_client.api_key = new_key
        arrms_client.session.headers.update({"X-API-Key": new_key})

        log_buffer.info(f"API key updated: {old_key_masked} -> {new_key_masked}")

        # Trigger immediate health check
        arrms_status_cache["error"] = "Checking..."
        arrms_status_cache["connected"] = False

        self.send_json({
            "status": "ok",
            "message": f"API key updated to {new_key_masked}",
            "api_key_masked": new_key_masked
        })

    def handle_webhook(self, payload: Dict):
        """Handle incoming ARRMS webhook."""
        event_type = payload.get("event_type", "unknown")
        questionnaire_id = payload.get("questionnaire_id")
        external_refs = payload.get("external_references", [])

        log_buffer.webhook(f"Received: {event_type}", {
            "questionnaire_id": questionnaire_id,
            "external_references": external_refs,
            "full_payload": payload,
        })

        # Find onspring reference
        onspring_ref = None
        for ref in external_refs:
            if ref.get("external_source") == "onspring":
                onspring_ref = ref
                break

        if onspring_ref:
            external_id = onspring_ref.get("external_id")
            log_buffer.info(f"Webhook for Onspring record: {external_id}")

            # Fetch and log statistics
            try:
                stats = WebRequestHandler.arrms_client.get_questionnaire_statistics(
                    external_id=external_id,
                    external_source="onspring",
                )
                summary = stats.get("summary", {})
                log_buffer.info(
                    f"ARRMS Status: {summary.get('approved_questions', 0)}/{summary.get('total_questions', 0)} approved",
                    {"summary": summary}
                )
            except Exception as e:
                log_buffer.warning(f"Could not fetch statistics: {str(e)}")

        self.send_json({"status": "received", "event_type": event_type})


def start_arrms_health_checker(arrms_client, interval: int = 5):
    """Start background thread that checks ARRMS health periodically."""
    def check_health():
        while True:
            try:
                response = arrms_client.session.get(
                    f"{arrms_client.base_url}/health",
                    timeout=3
                )
                # Consider 200 or 404 as "connected" (404 means server up but no health endpoint)
                if response.status_code in (200, 404):
                    arrms_status_cache["connected"] = True
                    arrms_status_cache["error"] = None
                else:
                    arrms_status_cache["connected"] = False
                    arrms_status_cache["error"] = f"HTTP {response.status_code}"
            except Exception as e:
                arrms_status_cache["connected"] = False
                arrms_status_cache["error"] = str(e)[:80]

            arrms_status_cache["last_check"] = datetime.now().isoformat()
            time.sleep(interval)

    thread = threading.Thread(target=check_health, daemon=True)
    thread.start()
    return thread


def main():
    parser = argparse.ArgumentParser(
        description="Web-based local development runner for ARRMS integration",
    )
    parser.add_argument("--port", type=int, default=8080, help="Port to run on (default: 8080)")
    parser.add_argument("--env-file", default=".env.local", help="Environment file (default: .env.local)")
    parser.add_argument("--no-log-bodies", action="store_true", help="Don't log HTTP bodies")

    args = parser.parse_args()

    # Load environment
    load_env_file(args.env_file)

    # Validate
    if not os.environ.get("ARRMS_API_URL"):
        logger.error("ARRMS_API_URL not set")
        sys.exit(1)
    if not os.environ.get("ARRMS_API_KEY"):
        logger.error("ARRMS_API_KEY not set")
        sys.exit(1)

    # Initialize clients
    mock_client = MockOnspringClient()
    arrms_client = LocalARRMSClient(log_bodies=not args.no_log_bodies)

    # Set up handler
    WebRequestHandler.arrms_client = arrms_client
    WebRequestHandler.mock_client = mock_client
    WebRequestHandler.web_ui_path = os.path.join(os.path.dirname(__file__), "web_ui")

    # Start background ARRMS health checker
    start_arrms_health_checker(arrms_client, interval=5)

    # Start server (threaded to handle SSE + other requests concurrently)
    server = ThreadingHTTPServer(("", args.port), WebRequestHandler)

    log_buffer.info(f"Web UI started on http://localhost:{args.port}")
    log_buffer.info(f"ARRMS URL: {os.environ.get('ARRMS_API_URL')}")
    log_buffer.info(f"Webhook endpoint: http://localhost:{args.port}/webhook/arrms")

    print(f"\n{'=' * 60}")
    print(f"  ARRMS Integration - Local Development UI")
    print(f"{'=' * 60}")
    print(f"  Web UI:   http://localhost:{args.port}")
    print(f"  Webhook:  http://localhost:{args.port}/webhook/arrms")
    print(f"  Health:   http://localhost:{args.port}/health")
    print(f"{'=' * 60}")
    print(f"  Press Ctrl+C to stop")
    print(f"{'=' * 60}\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
