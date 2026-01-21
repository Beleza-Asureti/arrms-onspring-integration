"""
Secrets Provider Abstraction

Provides pluggable secrets retrieval for local development and AWS deployment.
"""

import json
import os
from abc import ABC, abstractmethod
from typing import Optional


class SecretsProvider(ABC):
    """Abstract base class for secrets providers."""

    @abstractmethod
    def get_secret(self, secret_name: str) -> str:
        """
        Retrieve a secret value by name.

        Args:
            secret_name: Name/ID of the secret to retrieve

        Returns:
            Secret value as string

        Raises:
            SecretsError: If secret cannot be retrieved
        """
        pass


class SecretsError(Exception):
    """Raised when a secret cannot be retrieved."""

    pass


class AWSSecretsProvider(SecretsProvider):
    """
    AWS Secrets Manager provider.

    Retrieves secrets from AWS Secrets Manager. Used in production Lambda environment.
    """

    def __init__(self):
        import boto3

        self._client = boto3.client("secretsmanager")

    def get_secret(self, secret_name: str) -> str:
        """Retrieve secret from AWS Secrets Manager."""
        from botocore.exceptions import ClientError

        try:
            response = self._client.get_secret_value(SecretId=secret_name)

            if "SecretString" in response:
                secret = response["SecretString"]
                # Handle both plain string and JSON secrets
                try:
                    secret_dict = json.loads(secret)
                    return secret_dict.get("api_key", secret)
                except json.JSONDecodeError:
                    return secret
            else:
                raise SecretsError(f"Secret '{secret_name}' not in expected format")

        except ClientError as e:
            raise SecretsError(f"Failed to retrieve secret '{secret_name}': {str(e)}")


class LocalSecretsProvider(SecretsProvider):
    """
    Local secrets provider for development.

    Retrieves secrets from environment variables or a local secrets file.
    Supports multiple naming conventions for flexibility.
    """

    def __init__(self, secrets_file: Optional[str] = None):
        """
        Initialize local secrets provider.

        Args:
            secrets_file: Optional path to JSON file containing secrets
        """
        self._secrets = {}

        # Load from file if provided
        if secrets_file and os.path.exists(secrets_file):
            with open(secrets_file, "r") as f:
                self._secrets = json.load(f)

    def get_secret(self, secret_name: str) -> str:
        """
        Retrieve secret from environment or local file.

        Tries multiple naming conventions:
        1. Exact match in loaded secrets file
        2. Environment variable with exact name
        3. Environment variable with normalized name (slashes -> underscores, uppercase)
        4. Common local dev names (ONSPRING_API_KEY, ARRMS_API_KEY)
        """
        # Try loaded secrets file first
        if secret_name in self._secrets:
            value = self._secrets[secret_name]
            if isinstance(value, dict):
                return value.get("api_key", str(value))
            return str(value)

        # Try exact environment variable
        if secret_name in os.environ:
            return os.environ[secret_name]

        # Try normalized name (e.g., "onspring/api-key/prod" -> "ONSPRING_API_KEY_PROD")
        normalized = secret_name.replace("/", "_").replace("-", "_").upper()
        if normalized in os.environ:
            return os.environ[normalized]

        # Try common local dev names
        if "onspring" in secret_name.lower():
            for key in ["ONSPRING_API_KEY", "ONSPRING_API_KEY_SECRET"]:
                if key in os.environ:
                    return os.environ[key]

        if "arrms" in secret_name.lower():
            for key in ["ARRMS_API_KEY", "ARRMS_API_KEY_SECRET"]:
                if key in os.environ:
                    return os.environ[key]

        raise SecretsError(
            f"Secret '{secret_name}' not found. "
            f"Set environment variable '{normalized}' or add to secrets file."
        )


class EnvSecretsProvider(SecretsProvider):
    """
    Simple environment variable secrets provider.

    Maps secret names directly to environment variable names via a provided mapping.
    """

    def __init__(self, mapping: dict[str, str]):
        """
        Initialize with explicit mapping.

        Args:
            mapping: Dict mapping secret names to environment variable names
                     e.g., {"onspring/api-key": "ONSPRING_API_KEY"}
        """
        self._mapping = mapping

    def get_secret(self, secret_name: str) -> str:
        """Retrieve secret from mapped environment variable."""
        if secret_name not in self._mapping:
            raise SecretsError(f"No mapping configured for secret '{secret_name}'")

        env_var = self._mapping[secret_name]
        value = os.environ.get(env_var)

        if not value:
            raise SecretsError(f"Environment variable '{env_var}' not set for secret '{secret_name}'")

        return value


def get_secrets_provider(local_mode: bool = False, secrets_file: Optional[str] = None) -> SecretsProvider:
    """
    Factory function to get appropriate secrets provider.

    Args:
        local_mode: If True, use LocalSecretsProvider. If False, use AWSSecretsProvider.
        secrets_file: Optional path to local secrets file (only used in local mode)

    Returns:
        Configured SecretsProvider instance
    """
    # Auto-detect local mode from environment
    if os.environ.get("LOCAL_DEV", "").lower() in ("true", "1", "yes"):
        local_mode = True

    if local_mode:
        return LocalSecretsProvider(secrets_file=secrets_file)
    else:
        return AWSSecretsProvider()
