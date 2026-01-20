#!/usr/bin/env python3
"""
Local Development Runner

Run the ARRMS integration locally with mocked Onspring data and real ARRMS API calls.
Provides detailed HTTP request/response logging for debugging.

Usage:
    # Set environment variables
    export ARRMS_API_URL="https://your-arrms-instance.com"
    export ARRMS_API_KEY="your-api-key"

    # Run the local runner
    python scripts/local_runner.py

    # Or with a .env file
    python scripts/local_runner.py --env-file .env.local

    # Start webhook listener to receive callbacks from local ARRMS
    python scripts/local_runner.py --listen --port 8080
"""

import argparse
import json
import logging
import os
import sys
import tempfile
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, Optional
from unittest.mock import patch, MagicMock

import requests
from requests import Response

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("local_runner")


class HTTPLogger:
    """
    HTTP request/response logger that wraps requests.Session.

    Logs all HTTP traffic for debugging ARRMS API interactions.
    """

    def __init__(self, session: requests.Session, log_bodies: bool = True, max_body_length: int = 2000):
        self.session = session
        self.log_bodies = log_bodies
        self.max_body_length = max_body_length
        self.request_count = 0

    def _truncate(self, text: str) -> str:
        """Truncate long text for logging."""
        if len(text) > self.max_body_length:
            return text[: self.max_body_length] + f"\n... [truncated, {len(text)} total chars]"
        return text

    def _log_request(self, method: str, url: str, **kwargs):
        """Log outgoing request details."""
        self.request_count += 1
        logger.info("=" * 80)
        logger.info(f"REQUEST #{self.request_count}: {method} {url}")
        logger.info("=" * 80)

        # Log headers (mask API key)
        headers = kwargs.get("headers", {})
        safe_headers = {
            k: ("***" if k.lower() in ("x-api-key", "authorization") else v) for k, v in headers.items()
        }
        logger.info(f"Headers: {json.dumps(safe_headers, indent=2)}")

        # Log body
        if self.log_bodies:
            if "json" in kwargs:
                logger.info(f"JSON Body:\n{self._truncate(json.dumps(kwargs['json'], indent=2))}")
            elif "data" in kwargs:
                data = kwargs["data"]
                if isinstance(data, dict):
                    # Mask any sensitive fields
                    safe_data = {k: v for k, v in data.items()}
                    logger.info(f"Form Data:\n{json.dumps(safe_data, indent=2)}")
                else:
                    logger.info(f"Data: {self._truncate(str(data))}")

            if "files" in kwargs:
                files = kwargs["files"]
                for name, file_tuple in files.items():
                    if isinstance(file_tuple, tuple):
                        filename = file_tuple[0] if len(file_tuple) > 0 else "unknown"
                        content_type = file_tuple[2] if len(file_tuple) > 2 else "unknown"
                        # Handle both bytes and file objects
                        if len(file_tuple) > 1:
                            file_content = file_tuple[1]
                            if isinstance(file_content, bytes):
                                size = len(file_content)
                            elif hasattr(file_content, 'seek') and hasattr(file_content, 'tell'):
                                # File object - get size by seeking to end
                                current_pos = file_content.tell()
                                file_content.seek(0, 2)  # Seek to end
                                size = file_content.tell()
                                file_content.seek(current_pos)  # Restore position
                            else:
                                size = "unknown"
                        else:
                            size = 0
                        logger.info(f"File '{name}': {filename} ({content_type}, {size} bytes)")

    def _log_response(self, response: Response):
        """Log response details."""
        logger.info("-" * 80)
        logger.info(f"RESPONSE: {response.status_code} {response.reason}")
        logger.info("-" * 80)

        # Log response headers
        logger.info(f"Response Headers: {dict(response.headers)}")

        # Log response body
        if self.log_bodies:
            try:
                body = response.json()
                logger.info(f"Response JSON:\n{self._truncate(json.dumps(body, indent=2))}")
            except (json.JSONDecodeError, ValueError):
                logger.info(f"Response Text:\n{self._truncate(response.text)}")

        logger.info(f"Response Time: {response.elapsed.total_seconds():.3f}s")
        logger.info("=" * 80 + "\n")

    def request(self, method: str, url: str, **kwargs) -> Response:
        """Make HTTP request with logging."""
        self._log_request(method, url, **kwargs)

        response = self.session.request(method, url, **kwargs)

        self._log_response(response)
        return response

    def get(self, url: str, **kwargs) -> Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs) -> Response:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs) -> Response:
        return self.request("DELETE", url, **kwargs)

    def patch(self, url: str, **kwargs) -> Response:
        return self.request("PATCH", url, **kwargs)


class LocalARRMSClient:
    """
    ARRMS Client for local development.

    Reads API key directly from environment variable instead of AWS Secrets Manager.
    Wraps all HTTP calls with detailed logging.
    """

    def __init__(self, log_bodies: bool = True):
        self.base_url = os.environ.get("ARRMS_API_URL")
        self.api_key = os.environ.get("ARRMS_API_KEY")

        if not self.base_url:
            raise ValueError("ARRMS_API_URL environment variable not set")
        if not self.api_key:
            raise ValueError("ARRMS_API_KEY environment variable not set")

        logger.info(f"Initializing ARRMS client for: {self.base_url}")

        self.session = self._create_session()
        self.http = HTTPLogger(self.session, log_bodies=log_bodies)

    def _create_session(self) -> requests.Session:
        """Create requests session with default headers."""
        session = requests.Session()
        session.headers.update(
            {
                "X-API-Key": self.api_key,
                "Accept": "application/json",
            }
        )
        return session

    def health_check(self) -> bool:
        """Perform health check."""
        try:
            response = self.http.get(f"{self.base_url}/health", timeout=10)
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"Health check failed: {e}")
            return False

    def upload_questionnaire(
        self,
        file_path: str,
        external_id: str,
        external_source: str = "onspring",
        external_metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Upload questionnaire file to ARRMS."""
        url = f"{self.base_url}/api/v1/integrations/questionnaires/upload"

        with open(file_path, "rb") as f:
            files = {
                "file": (
                    os.path.basename(file_path),
                    f,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            }

            # Build form data
            data = {
                "external_id": external_id,
                "external_source": external_source,
                "external_metadata": json.dumps(external_metadata or {}),
            }

            # Add optional fields
            for key, value in kwargs.items():
                if value is not None:
                    data[key] = value

            response = self.http.post(url, files=files, data=data, timeout=120)
            response.raise_for_status()

        return response.json()

    def upload_document(
        self,
        questionnaire_id: str,
        file_content: bytes,
        file_name: str,
        content_type: str,
        external_id: Optional[str] = None,
        source_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Upload document to ARRMS questionnaire."""
        url = f"{self.base_url}/api/v1/questionnaires/{questionnaire_id}/documents"

        files = {"file": (file_name, file_content, content_type)}
        data = {
            "external_id": external_id or "",
            "external_source": "onspring",
            "source_metadata": json.dumps(source_metadata or {}),
        }

        response = self.http.post(url, files=files, data=data, timeout=120)
        response.raise_for_status()

        return response.json()

    def parse_external_reference(
        self, response_data: Dict[str, Any], external_source: str = "onspring"
    ) -> Optional[Dict[str, Any]]:
        """Extract external reference from ARRMS response."""
        refs = response_data.get("external_references", [])
        for ref in refs:
            if ref.get("external_source") == external_source:
                return ref
        return None

    def find_questionnaire_by_external_id(
        self, external_id: str, external_source: str = "onspring"
    ) -> Optional[Dict[str, Any]]:
        """
        Find an existing questionnaire in ARRMS by external system ID.

        Returns:
            Questionnaire data if found, None if not found
        """
        url = f"{self.base_url}/api/v1/integrations/questionnaires/find"
        params = {"external_id": external_id, "external_source": external_source}

        try:
            response = self.http.get(url, params=params, timeout=30)

            # 404 means not found - return None
            if response.status_code == 404:
                logger.info(f"No existing questionnaire found for external_id {external_id}")
                return None

            response.raise_for_status()
            data = response.json()
            logger.info(f"Found existing questionnaire {data.get('id')} for external_id {external_id}")
            return data

        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                logger.info(f"No existing questionnaire found for external_id {external_id}")
                return None
            raise

    def update_questionnaire_file(
        self,
        questionnaire_id: str,
        file_path: str,
        external_metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Update the source file for an existing questionnaire in ARRMS.

        This replaces the questionnaire file while maintaining the same questionnaire ID.
        """
        url = f"{self.base_url}/api/v1/integrations/questionnaires/{questionnaire_id}/file"

        with open(file_path, "rb") as f:
            files = {
                "file": (
                    os.path.basename(file_path),
                    f,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            }

            data = {
                "external_metadata": json.dumps(external_metadata or {}),
            }

            # Add optional fields
            for key, value in kwargs.items():
                if value is not None:
                    data[key] = value

            response = self.http.put(url, files=files, data=data, timeout=120)
            response.raise_for_status()

        return response.json()

    def get_questionnaire_statistics(
        self, external_id: str, external_source: str = "onspring"
    ) -> Dict[str, Any]:
        """
        Retrieve detailed questionnaire statistics from ARRMS.
        """
        url = f"{self.base_url}/api/v1/integrations/questionnaires/{external_id}/statistics"
        params = {"external_source": external_source}

        response = self.http.get(url, params=params, timeout=30)
        response.raise_for_status()

        return response.json()


def load_env_file(filepath: str):
    """Load environment variables from a file."""
    if not os.path.exists(filepath):
        logger.warning(f"Env file not found: {filepath}")
        return

    logger.info(f"Loading environment from: {filepath}")
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                # Remove quotes if present
                value = value.strip().strip("\"'")
                os.environ[key.strip()] = value
                if "KEY" in key.upper() or "SECRET" in key.upper():
                    logger.debug(f"  {key}=***")
                else:
                    logger.debug(f"  {key}={value}")


def transform_record(onspring_record: Dict[str, Any], onspring_client=None) -> Dict[str, Any]:
    """
    Transform Onspring questionnaire record to ARRMS format.

    This is a standalone copy of the transform logic to avoid AWS Lambda Powertools dependency.
    Updated to match production handler with fieldData array format and new field mappings.

    Args:
        onspring_record: Raw record from Onspring
        onspring_client: Optional Onspring client for resolving reference fields
    """
    field_data = onspring_record.get("fieldData", [])
    fields = onspring_record.get("fields", {})  # Legacy fallback

    # Helper to extract field value by field ID (new format)
    def get_field_value_by_id(field_id: int, default=None):
        for field in field_data:
            if field.get("fieldId") == field_id:
                return field.get("value", default)
        return default

    # Helper to extract field value by name (legacy format fallback)
    def get_field_value(field_name: str, default=None):
        field_info = fields.get(field_name, {})
        return field_info.get("value", default)

    # Resolve External Requestor Company Name (reference field)
    # Field 14947 contains recordId pointing to app 249
    # Field 14949 in app 249 contains the company name string
    requester_name = None
    company_record_id = get_field_value_by_id(14947)
    if company_record_id and onspring_client:
        try:
            requester_name = onspring_client.resolve_reference_field(
                referenced_app_id=249,
                referenced_record_id=int(company_record_id),
                field_id=14949,
            )
            logger.debug(f"Resolved company name: {requester_name}")
        except Exception as e:
            logger.warning(f"Failed to resolve company name for record {company_record_id}: {str(e)}")

    transformed = {
        "title": get_field_value("Title", "Untitled Questionnaire"),
        "client_name": get_field_value("Client"),
        "description": get_field_value("Description"),
        # New field mappings matching production
        "due_date": get_field_value_by_id(14872),  # Field 14872: Request Due Back to External Requestor
        "notes": get_field_value_by_id(14888),  # Field 14888: Scope Summary -> Questionnaire.notes
        "requester_name": requester_name,
        "external_id": str(onspring_record.get("recordId")),
        "external_source": "onspring",
        "external_metadata": {
            "app_id": onspring_record.get("appId"),
            "onspring_status": get_field_value("Status"),
            "onspring_url": f"https://app.onspring.com/record/{onspring_record.get('recordId')}",
            "field_ids": {
                "title": 101,
                "client": 102,
                "due_date": 14872,
                "status": 104,
                "description": 105,
                "scope_summary": 14888,
                "company_reference": 14947,
                "questionnaire_link": 15083,
            },
            "synced_at": datetime.utcnow().isoformat(),
            "sync_type": "local_test",
        },
    }

    return transformed


def run_webhook_flow(mock_client, arrms_client, record_id: int = 12345, app_id: int = 100):
    """
    Simulate the webhook flow: receive webhook -> fetch from Onspring -> sync to ARRMS.
    """

    logger.info("=" * 80)
    logger.info(f"SIMULATING WEBHOOK FLOW: Record {record_id}, App {app_id}")
    logger.info("=" * 80)

    # 1. Get record from mock Onspring
    record_data = mock_client.get_record(app_id=app_id, record_id=record_id)
    logger.info(f"Fetched record from Onspring: {record_data.get('recordId')}")

    # 2. Transform record (pass mock_client for reference field resolution)
    transformed = transform_record(record_data, onspring_client=mock_client)
    logger.info(f"Transformed record: {json.dumps(transformed, indent=2, default=str)}")

    # 3. Get files from record
    files = mock_client.get_record_files(record_data)
    if not files:
        logger.error("No files found in record")
        return None

    logger.info(f"Found {len(files)} files in record")

    # 4. Download questionnaire file
    questionnaire_file = files[0]
    file_content = mock_client.download_file(
        record_id=questionnaire_file["record_id"],
        field_id=questionnaire_file["field_id"],
        file_id=questionnaire_file["file_id"],
    )

    # 5. Save to temp file
    file_name = questionnaire_file.get("file_name", "questionnaire.xlsx")
    _, file_ext = os.path.splitext(file_name)
    if not file_ext:
        file_ext = ".xlsx"

    with tempfile.NamedTemporaryFile(mode="wb", suffix=file_ext, delete=False) as temp_file:
        temp_file.write(file_content)
        temp_file_path = temp_file.name

    logger.info(f"Saved questionnaire to: {temp_file_path}")

    # 6. Check if questionnaire already exists in ARRMS
    try:
        existing_questionnaire = arrms_client.find_questionnaire_by_external_id(
            external_id=str(record_id),
            external_source="onspring",
        )

        if existing_questionnaire:
            # Update existing questionnaire file
            arrms_id = existing_questionnaire.get("id")
            logger.info(f"Found existing questionnaire {arrms_id}, updating file...")

            result = arrms_client.update_questionnaire_file(
                questionnaire_id=arrms_id,
                file_path=temp_file_path,
                external_metadata=transformed.get("external_metadata", {}),
                requester_name=transformed.get("requester_name"),
                urgency=transformed.get("urgency"),
                assessment_type=transformed.get("assessment_type"),
                due_date=transformed.get("due_date"),
                notes=transformed.get("notes") or transformed.get("description"),
            )
            logger.info(f"Successfully updated questionnaire {arrms_id}")
        else:
            # Create new questionnaire
            logger.info("No existing questionnaire found, creating new one...")

            result = arrms_client.upload_questionnaire(
                file_path=temp_file_path,
                external_id=str(record_id),
                external_source="onspring",
                external_metadata=transformed.get("external_metadata", {}),
                requester_name=transformed.get("requester_name"),
                urgency=transformed.get("urgency"),
                assessment_type=transformed.get("assessment_type"),
                due_date=transformed.get("due_date"),
                notes=transformed.get("notes") or transformed.get("description"),
            )

            arrms_id = result.get("id")
            logger.info(f"Successfully created questionnaire {arrms_id}")

        # 7. Upload additional files (non-fatal if endpoint doesn't exist)
        additional_files = files[1:]
        files_uploaded = 0
        files_failed = 0
        for file_info in additional_files:
            try:
                file_content = mock_client.download_file(
                    record_id=file_info["record_id"],
                    field_id=file_info["field_id"],
                    file_id=file_info["file_id"],
                )

                arrms_client.upload_document(
                    questionnaire_id=arrms_id,
                    file_content=file_content,
                    file_name=file_info["file_name"],
                    content_type=file_info["content_type"],
                    external_id=str(file_info["file_id"]),
                    source_metadata={
                        "onspring_record_id": record_id,
                        "onspring_field_id": file_info["field_id"],
                        "onspring_file_id": file_info["file_id"],
                        "uploaded_at": datetime.utcnow().isoformat(),
                    },
                )
                files_uploaded += 1
                logger.info(f"Uploaded additional file: {file_info['file_name']}")
            except Exception as e:
                files_failed += 1
                logger.warning(f"Failed to upload additional file '{file_info['file_name']}': {e}")

        if additional_files:
            logger.info(f"Additional files: {files_uploaded} uploaded, {files_failed} failed")

        return result

    finally:
        # Cleanup
        os.unlink(temp_file_path)


def run_batch_sync(mock_client, arrms_client, app_id: int = 100, batch_size: int = 10):
    """
    Simulate batch sync flow: fetch multiple records from Onspring -> sync to ARRMS.
    """

    logger.info("=" * 80)
    logger.info(f"SIMULATING BATCH SYNC: App {app_id}, Batch Size {batch_size}")
    logger.info("=" * 80)

    # Get records from mock Onspring
    records = mock_client.get_records(app_id=app_id, page_size=batch_size)
    logger.info(f"Retrieved {len(records)} records from Onspring")

    results = {"successful": 0, "failed": 0, "errors": []}

    for record in records:
        record_id = record.get("recordId")
        try:
            logger.info(f"\nProcessing record {record_id}...")
            result = run_webhook_flow(mock_client, arrms_client, record_id=record_id, app_id=app_id)
            if result:
                results["successful"] += 1
            else:
                results["failed"] += 1
                results["errors"].append({"record_id": record_id, "error": "No files found"})
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({"record_id": record_id, "error": str(e)})
            logger.error(f"Failed to sync record {record_id}: {e}")

    logger.info("\n" + "=" * 80)
    logger.info("BATCH SYNC COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Successful: {results['successful']}")
    logger.info(f"Failed: {results['failed']}")
    if results["errors"]:
        logger.info(f"Errors: {json.dumps(results['errors'], indent=2)}")

    return results


class WebhookHandler(BaseHTTPRequestHandler):
    """
    HTTP request handler for receiving ARRMS webhook callbacks.

    Handles POST requests to /webhook/arrms and logs the payload.
    """

    # Class-level callback for processing webhooks
    webhook_callback = None

    def log_message(self, format, *args):
        """Override to use our logger instead of stderr."""
        logger.info(f"[HTTP] {args[0]}")

    def do_GET(self):
        """Handle GET requests - health check endpoint."""
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "listener": "active"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        """Handle POST requests - webhook endpoint."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")

        logger.info("=" * 80)
        logger.info(f"WEBHOOK RECEIVED: {self.path}")
        logger.info("=" * 80)
        logger.info(f"Headers: {dict(self.headers)}")

        try:
            payload = json.loads(body) if body else {}
            logger.info(f"Payload:\n{json.dumps(payload, indent=2)}")

            # Extract key information from ARRMS webhook
            event_type = payload.get("event_type", "unknown")
            questionnaire_id = payload.get("questionnaire_id")
            external_refs = payload.get("external_references", [])

            logger.info("-" * 40)
            logger.info(f"Event Type: {event_type}")
            logger.info(f"Questionnaire ID: {questionnaire_id}")
            if external_refs:
                for ref in external_refs:
                    logger.info(f"External Reference: {ref.get('external_source')}:{ref.get('external_id')}")

            # Call the callback if set
            if WebhookHandler.webhook_callback:
                try:
                    WebhookHandler.webhook_callback(payload)
                except Exception as e:
                    logger.error(f"Webhook callback error: {e}")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "received", "event_type": event_type}).encode())

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON payload: {e}")
            logger.error(f"Raw body: {body[:500]}")
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode())

        logger.info("=" * 80 + "\n")


def run_webhook_listener(port: int = 8080, callback=None):
    """
    Start HTTP server to listen for ARRMS webhooks.

    Args:
        port: Port to listen on (default: 8080)
        callback: Optional callback function to process webhooks
    """
    WebhookHandler.webhook_callback = callback

    server_address = ("", port)
    httpd = HTTPServer(server_address, WebhookHandler)

    logger.info("=" * 80)
    logger.info(f"WEBHOOK LISTENER STARTED")
    logger.info("=" * 80)
    logger.info(f"Listening on http://localhost:{port}")
    logger.info(f"Webhook endpoint: http://localhost:{port}/webhook/arrms")
    logger.info(f"Health check: http://localhost:{port}/health")
    logger.info("")
    logger.info("Configure your local ARRMS to send webhooks to this URL.")
    logger.info("Press Ctrl+C to stop.")
    logger.info("=" * 80 + "\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("\nShutting down webhook listener...")
        httpd.shutdown()


def run_listener_with_sync(port: int, arrms_client, mock_onspring_client=None):
    """
    Run webhook listener that also syncs data back to mock Onspring.

    When a webhook is received, fetches statistics from ARRMS and logs
    what would be synced back to Onspring.

    Args:
        port: Port to listen on
        arrms_client: ARRMS client for fetching statistics
        mock_onspring_client: Optional mock Onspring client
    """

    def on_webhook(payload):
        """Process incoming webhook and fetch statistics."""
        event_type = payload.get("event_type", "")
        external_refs = payload.get("external_references", [])

        # Find onspring external reference
        onspring_ref = None
        for ref in external_refs:
            if ref.get("external_source") == "onspring":
                onspring_ref = ref
                break

        if not onspring_ref:
            logger.warning("No Onspring external reference found in webhook")
            return

        external_id = onspring_ref.get("external_id")
        logger.info(f"\nProcessing webhook for Onspring record: {external_id}")

        # Fetch statistics from ARRMS
        try:
            stats = arrms_client.get_questionnaire_statistics(
                external_id=external_id,
                external_source="onspring",
            )

            summary = stats.get("summary", {})
            logger.info("-" * 40)
            logger.info("ARRMS Statistics:")
            logger.info(f"  Total Questions: {summary.get('total_questions', 0)}")
            logger.info(f"  Answered: {summary.get('answered_questions', 0)}")
            logger.info(f"  Approved: {summary.get('approved_questions', 0)}")
            logger.info(f"  Unanswered: {summary.get('unanswered_questions', 0)}")

            confidence = summary.get("confidence_distribution", {})
            if confidence:
                logger.info("  Confidence Distribution:")
                logger.info(f"    Very High (>80%): {confidence.get('very_high', 0)}")
                logger.info(f"    High (>50%): {confidence.get('high', 0)}")
                logger.info(f"    Medium (>25%): {confidence.get('medium', 0)}")
                logger.info(f"    Low (<25%): {confidence.get('low', 0)}")

            # Calculate Onspring field values (matching handler logic)
            total = summary.get("total_questions", 0)
            complete = summary.get("approved_questions", 0)
            open_questions = total - complete  # Calculated, not from unanswered_questions

            logger.info("-" * 40)
            logger.info("Calculated Onspring Field Values:")
            logger.info(f"  Total Assessment Questions: {total}")
            logger.info(f"  Complete Assessment Questions: {complete}")
            logger.info(f"  Open Assessment Questions: {open_questions}")
            if confidence:
                logger.info(f"  High Confidence Questions: {confidence.get('very_high', 0)}")
                logger.info(f"  Medium-High Confidence: {confidence.get('high', 0)}")
                logger.info(f"  Medium-Low Confidence: {confidence.get('medium', 0)}")
                logger.info(f"  Low Confidence Questions: {confidence.get('low', 0)}")

            # Calculate what status would be set in Onspring
            answered = summary.get("answered_questions", 0)
            has_document = stats.get("metadata", {}).get("source_document") is not None

            if answered == 0:
                status = "Not Started"
            elif complete == total and has_document:
                status = "Ready for Validation"
            else:
                status = "Request in Process"

            logger.info("-" * 40)
            logger.info(f"Calculated Onspring Status: {status}")
            logger.info(f"(Would update Onspring record {external_id})")

        except Exception as e:
            logger.error(f"Failed to fetch statistics: {e}")

    run_webhook_listener(port=port, callback=on_webhook)


def main():
    parser = argparse.ArgumentParser(
        description="Run ARRMS integration locally with mocked Onspring",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with environment variables
    export ARRMS_API_URL="https://demo.preview.asureti.com"
    export ARRMS_API_KEY="your-api-key"
    python scripts/local_runner.py

    # Run with env file
    python scripts/local_runner.py --env-file .env.local

    # Run health check only
    python scripts/local_runner.py --health-check

    # Run single webhook simulation
    python scripts/local_runner.py --webhook --record-id 12345

    # Run batch sync simulation
    python scripts/local_runner.py --batch --batch-size 5

    # Start webhook listener to receive ARRMS callbacks
    python scripts/local_runner.py --listen --port 8080

    # Start listener with auto-sync (fetches stats on webhook)
    python scripts/local_runner.py --listen --port 8080 --auto-sync
        """,
    )

    parser.add_argument(
        "--env-file",
        default=".env.local",
        help="Path to environment file (default: .env.local)",
    )
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Only run health check",
    )
    parser.add_argument(
        "--webhook",
        action="store_true",
        help="Simulate webhook flow for a single record",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Simulate batch sync flow",
    )
    parser.add_argument(
        "--record-id",
        type=int,
        default=12345,
        help="Record ID for webhook simulation (default: 12345)",
    )
    parser.add_argument(
        "--app-id",
        type=int,
        default=100,
        help="App ID for Onspring (default: 100)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Batch size for sync (default: 10)",
    )
    parser.add_argument(
        "--no-log-bodies",
        action="store_true",
        help="Don't log request/response bodies",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Get statistics for a questionnaire by external_id (use with --record-id)",
    )
    parser.add_argument(
        "--listen",
        action="store_true",
        help="Start HTTP server to listen for ARRMS webhook callbacks",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for webhook listener (default: 8080)",
    )
    parser.add_argument(
        "--auto-sync",
        action="store_true",
        help="When listening, automatically fetch ARRMS statistics on webhook receipt",
    )

    args = parser.parse_args()

    # Load environment
    load_env_file(args.env_file)

    # Listener-only mode doesn't require ARRMS credentials (unless auto-sync)
    if args.listen and not args.auto_sync:
        logger.info("Starting webhook listener (no ARRMS connection required)")
        run_webhook_listener(port=args.port)
        return

    # Validate required env vars for modes that need ARRMS
    if not os.environ.get("ARRMS_API_URL"):
        logger.error("ARRMS_API_URL not set. Set it via environment or --env-file")
        sys.exit(1)
    if not os.environ.get("ARRMS_API_KEY"):
        logger.error("ARRMS_API_KEY not set. Set it via environment or --env-file")
        sys.exit(1)

    # Import mock client
    from mock_onspring import MockOnspringClient

    # Initialize clients
    mock_client = MockOnspringClient()
    arrms_client = LocalARRMSClient(log_bodies=not args.no_log_bodies)

    # Run requested operation
    if args.health_check:
        logger.info("Running health check...")
        if arrms_client.health_check():
            logger.info("ARRMS health check: PASSED")
        else:
            logger.error("ARRMS health check: FAILED")
            sys.exit(1)

    elif args.stats:
        logger.info(f"Fetching statistics for external_id: {args.record_id}")
        try:
            stats = arrms_client.get_questionnaire_statistics(
                external_id=str(args.record_id),
                external_source="onspring",
            )
            logger.info(f"Statistics:\n{json.dumps(stats, indent=2)}")
        except requests.HTTPError as e:
            logger.error(f"Failed to get statistics: {e}")
            sys.exit(1)

    elif args.listen:
        # auto_sync mode (plain listen handled above before client init)
        run_listener_with_sync(port=args.port, arrms_client=arrms_client, mock_onspring_client=mock_client)

    elif args.webhook:
        run_webhook_flow(mock_client, arrms_client, record_id=args.record_id, app_id=args.app_id)

    elif args.batch:
        run_batch_sync(mock_client, arrms_client, app_id=args.app_id, batch_size=args.batch_size)

    else:
        # Default: run health check then single webhook
        logger.info("Running default flow: health check + single webhook simulation")
        if arrms_client.health_check():
            logger.info("ARRMS health check: PASSED\n")
            run_webhook_flow(mock_client, arrms_client, record_id=args.record_id, app_id=args.app_id)
        else:
            logger.error("ARRMS health check failed, aborting")
            sys.exit(1)


if __name__ == "__main__":
    main()
