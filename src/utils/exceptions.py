"""
Custom Exception Classes

Defines custom exceptions for the integration service.
Provides structured error handling across the application.
"""


class IntegrationError(Exception):
    """Base exception for integration errors."""

    def __init__(self, message: str, details: dict = None):
        """
        Initialize integration error.

        Args:
            message: Error message
            details: Additional error details
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationError(IntegrationError):
    """Exception raised for data validation errors."""

    def __init__(self, message: str, field: str = None, details: dict = None):
        """
        Initialize validation error.

        Args:
            message: Error message
            field: Field that failed validation
            details: Additional error details
        """
        super().__init__(message, details)
        self.field = field


class AuthenticationError(IntegrationError):
    """Exception raised for authentication failures."""

    pass


class OnspringAPIError(IntegrationError):
    """Exception raised for Onspring API errors."""

    def __init__(self, message: str, status_code: int = None, details: dict = None):
        """
        Initialize Onspring API error.

        Args:
            message: Error message
            status_code: HTTP status code
            details: Additional error details
        """
        super().__init__(message, details)
        self.status_code = status_code


class ARRMSAPIError(IntegrationError):
    """Exception raised for ARRMS API errors."""

    def __init__(self, message: str, status_code: int = None, details: dict = None):
        """
        Initialize ARRMS API error.

        Args:
            message: Error message
            status_code: HTTP status code
            details: Additional error details
        """
        super().__init__(message, details)
        self.status_code = status_code


class TransformationError(IntegrationError):
    """Exception raised for data transformation errors."""

    def __init__(self, message: str, source_data: dict = None, details: dict = None):
        """
        Initialize transformation error.

        Args:
            message: Error message
            source_data: Source data that failed transformation
            details: Additional error details
        """
        super().__init__(message, details)
        self.source_data = source_data


class ConfigurationError(IntegrationError):
    """Exception raised for configuration errors."""

    pass
