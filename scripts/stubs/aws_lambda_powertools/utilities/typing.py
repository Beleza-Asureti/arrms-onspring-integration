"""Stub typing module for local development."""

from typing import Any, Protocol


class LambdaContext(Protocol):
    """Stub LambdaContext type for type hints."""

    function_name: str
    function_version: str
    invoked_function_arn: str
    memory_limit_in_mb: int
    aws_request_id: str
    log_group_name: str
    log_stream_name: str

    def get_remaining_time_in_millis(self) -> int:
        ...
