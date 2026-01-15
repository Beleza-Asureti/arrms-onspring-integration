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
                "Authorization": f"Bearer {self.api_key}",
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

    def create_record(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new record in ARRMS.

        Args:
            data: Record data to create

        Returns:
            Created record response

        Raises:
            ARRMSAPIError: If API request fails
        """
        try:
            url = f"{self.base_url}/records"
            logger.info("Creating record in ARRMS")

            # Add metadata
            payload = {
                **data,
                "created_at": datetime.utcnow().isoformat(),
                "source": "onspring",
            }

            response = self.session.post(url, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Created ARRMS record with ID {result.get('id')}")

            return result

        except requests.HTTPError as e:
            logger.error(f"HTTP error creating ARRMS record: {str(e)}")
            if e.response is not None:
                logger.error(f"Response body: {e.response.text}")
            raise ARRMSAPIError(f"Failed to create record: {str(e)}")
        except requests.RequestException as e:
            logger.error(f"Request error creating ARRMS record: {str(e)}")
            raise ARRMSAPIError(f"Request failed: {str(e)}")

    def update_record(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing record in ARRMS.

        Args:
            data: Record data with ID

        Returns:
            Updated record response

        Raises:
            ARRMSAPIError: If API request fails
        """
        try:
            record_id = data.get("id")
            if not record_id:
                raise ValueError("Record ID is required for update")

            url = f"{self.base_url}/records/{record_id}"
            logger.info(f"Updating ARRMS record {record_id}")

            # Add metadata
            payload = {
                **data,
                "updated_at": datetime.utcnow().isoformat(),
                "source": "onspring",
            }

            response = self.session.put(url, json=payload, timeout=30)
            response.raise_for_status()

            result = (
                response.json()
                if response.text
                else {"id": record_id, "status": "updated"}
            )
            logger.info(f"Updated ARRMS record {record_id}")

            return result

        except requests.HTTPError as e:
            logger.error(f"HTTP error updating ARRMS record: {str(e)}")
            if e.response is not None:
                logger.error(f"Response body: {e.response.text}")
            raise ARRMSAPIError(f"Failed to update record: {str(e)}")
        except requests.RequestException as e:
            logger.error(f"Request error updating ARRMS record: {str(e)}")
            raise ARRMSAPIError(f"Request failed: {str(e)}")

    def upsert_record(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create or update a record in ARRMS (upsert operation).

        Args:
            data: Record data

        Returns:
            Upsert operation response

        Raises:
            ARRMSAPIError: If API request fails
        """
        try:
            record_id = data.get("id")

            # Check if record exists
            if record_id and self._record_exists(record_id):
                logger.info(f"Record {record_id} exists, updating")
                return self.update_record(data)
            else:
                logger.info("Record does not exist, creating")
                return self.create_record(data)

        except ARRMSAPIError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error during upsert: {str(e)}")
            raise ARRMSAPIError(f"Upsert operation failed: {str(e)}")

    def _record_exists(self, record_id: str) -> bool:
        """
        Check if a record exists in ARRMS.

        Args:
            record_id: Record ID to check

        Returns:
            True if record exists, False otherwise
        """
        try:
            url = f"{self.base_url}/records/{record_id}"
            response = self.session.get(url, timeout=10)

            return response.status_code == 200

        except requests.RequestException:
            return False

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
