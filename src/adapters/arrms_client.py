"""
ARRMS API Client

Adapter for interacting with ARRMS (Asureti Risk & Resilience Management System) API.
Handles authentication, request/response processing, and error handling.
"""

import os
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from aws_lambda_powertools import Logger
import boto3
from botocore.exceptions import ClientError

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
            response = secrets_client.get_secret_value(
                SecretId=self.api_key_secret_name
            )

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

    def create_questionnaire(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create questionnaire in ARRMS with external system fields.

        Args:
            data: Questionnaire data including external_id and external_source

        Returns:
            Created questionnaire response

        Raises:
            ARRMSAPIError: If API request fails
        """
        try:
            url = f"{self.base_url}/api/v1/questionnaires"
            logger.info("Creating questionnaire in ARRMS")

            # Payload includes external system tracking fields
            payload = {
                "title": data.get("title"),
                "client_name": data.get("client_name"),
                "description": data.get("description"),
                "due_date": data.get("due_date"),
                # External system tracking
                "external_id": data.get("external_id"),
                "external_source": data.get("external_source", "onspring"),
                "external_metadata": data.get("external_metadata", {}),
            }

            response = self.session.post(url, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Created ARRMS questionnaire with ID {result.get('id')}")

            return result

        except requests.HTTPError as e:
            logger.error(f"HTTP error creating ARRMS questionnaire: {str(e)}")
            if e.response is not None:
                logger.error(f"Response body: {e.response.text}")
            raise ARRMSAPIError(f"Failed to create questionnaire: {str(e)}")
        except requests.RequestException as e:
            logger.error(f"Request error creating ARRMS questionnaire: {str(e)}")
            raise ARRMSAPIError(f"Request failed: {str(e)}")

    def update_questionnaire(self, arrms_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update existing questionnaire in ARRMS.

        Args:
            arrms_id: ARRMS questionnaire ID
            data: Updated questionnaire data

        Returns:
            Updated questionnaire response

        Raises:
            ARRMSAPIError: If API request fails
        """
        try:
            url = f"{self.base_url}/api/v1/questionnaires/{arrms_id}"
            logger.info(f"Updating ARRMS questionnaire {arrms_id}")

            response = self.session.put(url, json=data, timeout=30)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Updated ARRMS questionnaire {arrms_id}")

            return result

        except requests.HTTPError as e:
            logger.error(f"HTTP error updating ARRMS questionnaire: {str(e)}")
            if e.response is not None:
                logger.error(f"Response body: {e.response.text}")
            raise ARRMSAPIError(f"Failed to update questionnaire: {str(e)}")
        except requests.RequestException as e:
            logger.error(f"Request error updating ARRMS questionnaire: {str(e)}")
            raise ARRMSAPIError(f"Request failed: {str(e)}")

    def get_questionnaire_by_external_id(self, external_id: str) -> Optional[Dict[str, Any]]:
        """
        Query questionnaire by Onspring record ID.

        Args:
            external_id: Onspring record ID

        Returns:
            Questionnaire data if found, None otherwise

        Raises:
            ARRMSAPIError: If API request fails (other than 404)
        """
        try:
            url = f"{self.base_url}/api/v1/questionnaires"
            params = {
                "external_source": "onspring",
                "external_id": external_id,
            }

            response = self.session.get(url, params=params, timeout=10)

            if response.status_code == 404:
                return None

            response.raise_for_status()
            results = response.json()

            # Should return single result or empty list
            return results[0] if results else None

        except requests.HTTPError as e:
            if e.response and e.response.status_code == 404:
                return None
            logger.error(f"HTTP error querying questionnaire: {str(e)}")
            raise ARRMSAPIError(f"Failed to query questionnaire: {str(e)}")
        except requests.RequestException as e:
            logger.error(f"Request error querying questionnaire: {str(e)}")
            raise ARRMSAPIError(f"Request failed: {str(e)}")

    def upsert_questionnaire(self, external_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create or update questionnaire by Onspring ID.

        Args:
            external_id: Onspring record ID
            data: Questionnaire data

        Returns:
            Upsert operation response

        Raises:
            ARRMSAPIError: If API request fails
        """
        try:
            # First, try to find existing questionnaire
            existing = self.get_questionnaire_by_external_id(external_id)

            if existing:
                # Update existing
                logger.info(f"Questionnaire with external_id {external_id} exists, updating")
                return self.update_questionnaire(existing["id"], data)
            else:
                # Create new
                logger.info(f"Questionnaire with external_id {external_id} does not exist, creating")
                return self.create_questionnaire(data)

        except ARRMSAPIError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error during upsert: {str(e)}")
            raise ARRMSAPIError(f"Upsert operation failed: {str(e)}")

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
