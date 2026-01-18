"""
ARRMS API Client

Adapter for interacting with ARRMS (Asureti Risk & Resilience Management System) API.
Handles authentication, request/response processing, and error handling.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import boto3
import requests
from aws_lambda_powertools import Logger
from botocore.exceptions import ClientError
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils.exceptions import ARRMSAPIError, AuthenticationError

logger = Logger(child=True)


class ARRMSClient:
    """
    Client for ARRMS API operations.

    Provides methods for creating, updating, and managing records
    in the ARRMS platform.
    """

    def __init__(self):
        """Initialize ARRMS client with configuration from environment."""
        self.base_url = os.environ.get("ARRMS_API_URL")
        self.api_key_secret_name = os.environ.get("ARRMS_API_KEY_SECRET")

        if not self.base_url:
            raise ValueError("ARRMS_API_URL environment variable not set")

        if not self.api_key_secret_name:
            raise ValueError("ARRMS_API_KEY_SECRET environment variable not set")

        self.api_key = self._get_api_key()
        self.session = self._create_session()

    def _get_api_key(self) -> str:
        """
        Retrieve API key from AWS Secrets Manager.

        Returns:
            API key string

        Raises:
            AuthenticationError: If unable to retrieve API key
        """
        try:
            secrets_client = boto3.client("secretsmanager")
            response = secrets_client.get_secret_value(SecretId=self.api_key_secret_name)

            # Handle both string and JSON secrets
            if "SecretString" in response:
                secret = response["SecretString"]
                try:
                    secret_dict = json.loads(secret)
                    return secret_dict.get("api_key", secret)
                except json.JSONDecodeError:
                    return secret
            else:
                raise AuthenticationError("Secret not found in expected format")

        except ClientError as e:
            logger.error(f"Failed to retrieve ARRMS API key: {str(e)}")
            raise AuthenticationError(f"Could not retrieve API key: {str(e)}")

    def _create_session(self) -> requests.Session:
        """
        Create requests session with retry logic and default headers.

        Returns:
            Configured requests.Session
        """
        session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        # Set default headers
        session.headers.update(
            {
                "X-API-Key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

        return session

    def health_check(self) -> bool:
        """
        Perform health check by pinging ARRMS API.

        Returns:
            True if API is reachable

        Raises:
            ARRMSAPIError: If health check fails
        """
        try:
            # Adjust endpoint based on actual ARRMS API structure
            response = self.session.get(f"{self.base_url}/health", timeout=10)
            response.raise_for_status()
            logger.info("ARRMS health check passed")
            return True
        except requests.RequestException as e:
            logger.error(f"ARRMS health check failed: {str(e)}")
            raise ARRMSAPIError(f"Health check failed: {str(e)}")

    def upload_questionnaire(
        self,
        file_path: str,
        external_id: str,
        external_source: str = "onspring",
        external_metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Upload questionnaire file to ARRMS with external system tracking.

        Response includes external_references array:
        {
            "id": "uuid",
            "name": "Questionnaire Name",
            "external_references": [
                {
                    "id": "ref-uuid",
                    "external_id": "12345",
                    "external_source": "onspring",
                    "external_metadata": {...},
                    "sync_status": null,
                    "last_synced_at": null
                }
            ]
        }

        Args:
            file_path: Path to questionnaire file (Excel format)
            external_id: Onspring record ID
            external_source: Source system identifier (default: "onspring")
            external_metadata: Additional metadata about the source record
            **kwargs: Additional form fields (requester_name, urgency, etc.)

        Returns:
            Questionnaire response with external_references array

        Raises:
            ARRMSAPIError: If API request fails
        """
        try:
            import os

            url = f"{self.base_url}/api/v1/questionnaires/upload"
            logger.info(f"Uploading questionnaire from {file_path} with external_id {external_id}")

            # Prepare multipart form data
            with open(file_path, "rb") as f:
                files = {
                    "file": (
                        os.path.basename(file_path),
                        f,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                }

                # Form data with external system tracking
                data = {
                    "external_id": external_id,
                    "external_source": external_source,
                    "external_metadata": json.dumps(external_metadata or {}),
                    **kwargs,  # Additional fields like requester_name, urgency, etc.
                }

                response = self.session.post(url, files=files, data=data, timeout=120)
                response.raise_for_status()

            result = response.json()
            logger.info(f"Uploaded questionnaire to ARRMS with ID {result.get('id')}")

            return result

        except requests.HTTPError as e:
            logger.error(f"HTTP error uploading questionnaire: {str(e)}")
            if e.response is not None:
                logger.error(f"Response body: {e.response.text}")
            raise ARRMSAPIError(f"Failed to upload questionnaire: {str(e)}")
        except requests.RequestException as e:
            logger.error(f"Request error uploading questionnaire: {str(e)}")
            raise ARRMSAPIError(f"Request failed: {str(e)}")
        except IOError as e:
            logger.error(f"File error: {str(e)}")
            raise ARRMSAPIError(f"Failed to read questionnaire file: {str(e)}")

    def parse_external_reference(
        self, response_data: Dict[str, Any], external_source: str = "onspring"
    ) -> Optional[Dict[str, Any]]:
        """
        Extract external reference from ARRMS response.

        Response format:
        {
            "id": "uuid",
            "external_references": [
                {
                    "id": "ref-uuid",
                    "external_id": "12345",
                    "external_source": "onspring",
                    "external_metadata": {...},
                    "sync_status": null,
                    "last_synced_at": null
                }
            ]
        }

        Args:
            response_data: ARRMS API response
            external_source: Source system to filter by (default: "onspring")

        Returns:
            External reference dict if found, None otherwise
        """
        refs = response_data.get("external_references", [])

        # Find reference matching our source
        for ref in refs:
            if ref.get("external_source") == external_source:
                return ref

        return None

    def delete_record(self, record_id: str) -> bool:
        """
        Delete a record from ARRMS.

        Args:
            record_id: Record ID to delete

        Returns:
            True if successful

        Raises:
            ARRMSAPIError: If API request fails
        """
        try:
            url = f"{self.base_url}/records/{record_id}"
            logger.info(f"Deleting ARRMS record {record_id}")

            response = self.session.delete(url, timeout=30)
            response.raise_for_status()

            logger.info(f"Deleted ARRMS record {record_id}")

            return True

        except requests.HTTPError as e:
            logger.error(f"HTTP error deleting ARRMS record: {str(e)}")
            if e.response is not None:
                logger.error(f"Response body: {e.response.text}")
            raise ARRMSAPIError(f"Failed to delete record {record_id}: {str(e)}")
        except requests.RequestException as e:
            logger.error(f"Request error deleting ARRMS record: {str(e)}")
            raise ARRMSAPIError(f"Request failed: {str(e)}")

    def get_record(self, record_id: str) -> Dict[str, Any]:
        """
        Retrieve a single record from ARRMS.

        Args:
            record_id: Record ID to retrieve

        Returns:
            Record data dictionary

        Raises:
            ARRMSAPIError: If API request fails
        """
        try:
            url = f"{self.base_url}/records/{record_id}"
            logger.info(f"Retrieving ARRMS record {record_id}")

            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            data = response.json()
            logger.debug(f"Retrieved ARRMS record {record_id}", extra={"data": data})

            return data

        except requests.HTTPError as e:
            logger.error(f"HTTP error retrieving ARRMS record: {str(e)}")
            raise ARRMSAPIError(f"Failed to retrieve record {record_id}: {str(e)}")
        except requests.RequestException as e:
            logger.error(f"Request error retrieving ARRMS record: {str(e)}")
            raise ARRMSAPIError(f"Request failed: {str(e)}")

    def batch_create(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Create multiple records in ARRMS in a single batch operation.

        Args:
            records: List of record data to create

        Returns:
            Batch operation result

        Raises:
            ARRMSAPIError: If API request fails
        """
        try:
            url = f"{self.base_url}/records/batch"
            logger.info(f"Creating {len(records)} records in ARRMS (batch)")

            payload = {
                "records": records,
                "source": "onspring",
                "created_at": datetime.utcnow().isoformat(),
            }

            response = self.session.post(url, json=payload, timeout=120)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Batch created {len(records)} records")

            return result

        except requests.HTTPError as e:
            logger.error(f"HTTP error in batch create: {str(e)}")
            if e.response is not None:
                logger.error(f"Response body: {e.response.text}")
            raise ARRMSAPIError(f"Failed to batch create records: {str(e)}")
        except requests.RequestException as e:
            logger.error(f"Request error in batch create: {str(e)}")
            raise ARRMSAPIError(f"Request failed: {str(e)}")

    def upload_document(
        self,
        questionnaire_id: str,
        file_content: bytes,
        file_name: str,
        content_type: str,
        external_id: Optional[str] = None,
        source_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Upload document to ARRMS questionnaire with external system metadata.

        Args:
            questionnaire_id: ARRMS questionnaire ID to attach document to
            file_content: File content as bytes
            file_name: Name of the file
            content_type: MIME type of the file
            external_id: Optional Onspring file ID
            source_metadata: Optional metadata from Onspring

        Returns:
            Upload response with document ID

        Raises:
            ARRMSAPIError: If API request fails
        """
        try:
            url = f"{self.base_url}/api/v1/questionnaires/{questionnaire_id}/documents"
            logger.info(
                f"Uploading document '{file_name}' to ARRMS questionnaire {questionnaire_id} "
                f"(size: {len(file_content)} bytes)"
            )

            # Prepare multipart form data
            files = {"file": (file_name, file_content, content_type)}

            # Form data with external system tracking
            data = {
                "external_id": external_id or "",
                "external_source": "onspring",
                "source_metadata": json.dumps(source_metadata or {}),
            }

            response = self.session.post(url, files=files, data=data, timeout=120)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Uploaded document '{file_name}' to questionnaire {questionnaire_id}")

            return result

        except requests.HTTPError as e:
            logger.error(f"HTTP error uploading document to ARRMS: {str(e)}")
            if e.response is not None:
                logger.error(f"Response body: {e.response.text}")
            raise ARRMSAPIError(f"Failed to upload document: {str(e)}")
        except requests.RequestException as e:
            logger.error(f"Request error uploading document to ARRMS: {str(e)}")
            raise ARRMSAPIError(f"Request failed: {str(e)}")
