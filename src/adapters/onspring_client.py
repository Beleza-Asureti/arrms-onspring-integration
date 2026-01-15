"""
Onspring API Client

Adapter for interacting with Onspring API.
Handles authentication, request/response processing, and error handling.
"""

import os
import json
from typing import Dict, Any, List, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from aws_lambda_powertools import Logger
import boto3
from botocore.exceptions import ClientError

from utils.exceptions import OnspringAPIError, AuthenticationError

logger = Logger(child=True)


class OnspringClient:
    """
    Client for Onspring API operations.

    Provides methods for retrieving, creating, updating, and deleting
    records in Onspring applications.
    """

    def __init__(self):
        """Initialize Onspring client with configuration from environment."""
        self.base_url = os.environ.get('ONSPRING_API_URL', 'https://api.onspring.com/v2')
        self.api_key_secret_name = os.environ.get('ONSPRING_API_KEY_SECRET')

        if not self.api_key_secret_name:
            raise ValueError("ONSPRING_API_KEY_SECRET environment variable not set")

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
            secrets_client = boto3.client('secretsmanager')
            response = secrets_client.get_secret_value(SecretId=self.api_key_secret_name)

            # Handle both string and JSON secrets
            if 'SecretString' in response:
                secret = response['SecretString']
                try:
                    secret_dict = json.loads(secret)
                    return secret_dict.get('api_key', secret)
                except json.JSONDecodeError:
                    return secret
            else:
                raise AuthenticationError("Secret not found in expected format")

        except ClientError as e:
            logger.error(f"Failed to retrieve Onspring API key: {str(e)}")
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
            allowed_methods=["GET", "POST", "PUT", "DELETE"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        # Set default headers
        session.headers.update({
            'x-apikey': self.api_key,
            'x-api-version': '2',
            'Content-Type': 'application/json'
        })

        return session

    def health_check(self) -> bool:
        """
        Perform health check by pinging Onspring API.

        Returns:
            True if API is reachable

        Raises:
            OnspringAPIError: If health check fails
        """
        try:
            # Use the ping endpoint or a lightweight API call
            response = self.session.get(f"{self.base_url}/Ping", timeout=10)
            response.raise_for_status()
            logger.info("Onspring health check passed")
            return True
        except requests.RequestException as e:
            logger.error(f"Onspring health check failed: {str(e)}")
            raise OnspringAPIError(f"Health check failed: {str(e)}")

    def get_record(self, app_id: int, record_id: int) -> Dict[str, Any]:
        """
        Retrieve a single record from Onspring.

        Args:
            app_id: Onspring application ID
            record_id: Record ID to retrieve

        Returns:
            Record data dictionary

        Raises:
            OnspringAPIError: If API request fails
        """
        try:
            url = f"{self.base_url}/Records/appId/{app_id}/recordId/{record_id}"
            logger.info(f"Retrieving record {record_id} from app {app_id}")

            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            data = response.json()
            logger.debug(f"Retrieved record {record_id}", extra={"data": data})

            return data

        except requests.HTTPError as e:
            logger.error(f"HTTP error retrieving record: {str(e)}")
            raise OnspringAPIError(f"Failed to retrieve record {record_id}: {str(e)}")
        except requests.RequestException as e:
            logger.error(f"Request error retrieving record: {str(e)}")
            raise OnspringAPIError(f"Request failed: {str(e)}")

    def get_records(
        self,
        app_id: int,
        filter_criteria: Optional[Dict[str, Any]] = None,
        page_size: int = 100,
        page_number: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Retrieve multiple records from Onspring application.

        Args:
            app_id: Onspring application ID
            filter_criteria: Optional filter criteria
            page_size: Number of records per page (max 1000)
            page_number: Page number to retrieve

        Returns:
            List of record dictionaries

        Raises:
            OnspringAPIError: If API request fails
        """
        try:
            url = f"{self.base_url}/Records/Query"
            logger.info(f"Querying records from app {app_id}")

            # Build request payload
            payload = {
                "appId": app_id,
                "pagingRequest": {
                    "pageNumber": page_number,
                    "pageSize": min(page_size, 1000)
                }
            }

            if filter_criteria:
                payload["filter"] = filter_criteria

            response = self.session.post(url, json=payload, timeout=60)
            response.raise_for_status()

            data = response.json()
            records = data.get('records', [])

            logger.info(f"Retrieved {len(records)} records from app {app_id}")

            return records

        except requests.HTTPError as e:
            logger.error(f"HTTP error querying records: {str(e)}")
            raise OnspringAPIError(f"Failed to query records: {str(e)}")
        except requests.RequestException as e:
            logger.error(f"Request error querying records: {str(e)}")
            raise OnspringAPIError(f"Request failed: {str(e)}")

    def create_record(self, app_id: int, field_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new record in Onspring.

        Args:
            app_id: Onspring application ID
            field_data: Record field data

        Returns:
            Created record response

        Raises:
            OnspringAPIError: If API request fails
        """
        try:
            url = f"{self.base_url}/Records"
            logger.info(f"Creating record in app {app_id}")

            payload = {
                "appId": app_id,
                "fieldData": field_data
            }

            response = self.session.post(url, json=payload, timeout=30)
            response.raise_for_status()

            data = response.json()
            logger.info(f"Created record with ID {data.get('id')}")

            return data

        except requests.HTTPError as e:
            logger.error(f"HTTP error creating record: {str(e)}")
            raise OnspringAPIError(f"Failed to create record: {str(e)}")
        except requests.RequestException as e:
            logger.error(f"Request error creating record: {str(e)}")
            raise OnspringAPIError(f"Request failed: {str(e)}")

    def update_record(self, record_id: int, field_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing record in Onspring.

        Args:
            record_id: Record ID to update
            field_data: Updated field data

        Returns:
            Update response

        Raises:
            OnspringAPIError: If API request fails
        """
        try:
            url = f"{self.base_url}/Records/{record_id}"
            logger.info(f"Updating record {record_id}")

            payload = {
                "id": record_id,
                "fieldData": field_data
            }

            response = self.session.put(url, json=payload, timeout=30)
            response.raise_for_status()

            logger.info(f"Updated record {record_id}")

            return response.json() if response.text else {"id": record_id, "status": "updated"}

        except requests.HTTPError as e:
            logger.error(f"HTTP error updating record: {str(e)}")
            raise OnspringAPIError(f"Failed to update record {record_id}: {str(e)}")
        except requests.RequestException as e:
            logger.error(f"Request error updating record: {str(e)}")
            raise OnspringAPIError(f"Request failed: {str(e)}")

    def delete_record(self, record_id: int) -> bool:
        """
        Delete a record from Onspring.

        Args:
            record_id: Record ID to delete

        Returns:
            True if successful

        Raises:
            OnspringAPIError: If API request fails
        """
        try:
            url = f"{self.base_url}/Records/{record_id}"
            logger.info(f"Deleting record {record_id}")

            response = self.session.delete(url, timeout=30)
            response.raise_for_status()

            logger.info(f"Deleted record {record_id}")

            return True

        except requests.HTTPError as e:
            logger.error(f"HTTP error deleting record: {str(e)}")
            raise OnspringAPIError(f"Failed to delete record {record_id}: {str(e)}")
        except requests.RequestException as e:
            logger.error(f"Request error deleting record: {str(e)}")
            raise OnspringAPIError(f"Request failed: {str(e)}")
