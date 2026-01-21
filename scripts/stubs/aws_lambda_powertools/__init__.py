"""
Stub implementation of aws_lambda_powertools for local development.

This provides no-op implementations of Logger, Metrics, and Tracer
that allow handler code to run without the actual AWS package.
"""

import logging
import functools
from typing import Any, Callable, Optional


class Logger:
    """Stub Logger that wraps Python's standard logging."""

    def __init__(
        self,
        service: Optional[str] = None,
        level: str = "INFO",
        child: bool = False,
        **kwargs,
    ):
        self.service = service or "local-dev"
        self._logger = logging.getLogger(f"powertools.{self.service}")
        self._logger.setLevel(getattr(logging, level.upper(), logging.INFO))

        if not self._logger.handlers and not child:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
            )
            self._logger.addHandler(handler)

    def info(self, msg: str, *args, **kwargs):
        extra = kwargs.pop("extra", None)
        self._logger.info(msg, *args)

    def error(self, msg: str, *args, **kwargs):
        extra = kwargs.pop("extra", None)
        self._logger.error(msg, *args)

    def warning(self, msg: str, *args, **kwargs):
        extra = kwargs.pop("extra", None)
        self._logger.warning(msg, *args)

    def debug(self, msg: str, *args, **kwargs):
        extra = kwargs.pop("extra", None)
        self._logger.debug(msg, *args)

    def exception(self, msg: str, *args, **kwargs):
        extra = kwargs.pop("extra", None)
        self._logger.exception(msg, *args)

    def append_keys(self, **kwargs):
        """No-op for local dev."""
        pass

    def remove_keys(self, keys):
        """No-op for local dev."""
        pass

    def structure_logs(self, **kwargs):
        """No-op for local dev."""
        pass

    def inject_lambda_context(self, lambda_handler: Callable = None, **kwargs):
        """Decorator that passes through to the handler."""
        def decorator(func):
            @functools.wraps(func)
            def wrapper(event, context, *args, **inner_kwargs):
                return func(event, context, *args, **inner_kwargs)
            return wrapper

        if lambda_handler is not None:
            return decorator(lambda_handler)
        return decorator


class Metrics:
    """Stub Metrics that does nothing."""

    def __init__(self, service: Optional[str] = None, namespace: Optional[str] = None, **kwargs):
        self.service = service
        self.namespace = namespace

    def add_metric(self, name: str, unit: Any, value: float, **kwargs):
        """No-op for local dev."""
        pass

    def add_dimension(self, name: str, value: str):
        """No-op for local dev."""
        pass

    def add_metadata(self, key: str, value: Any):
        """No-op for local dev."""
        pass

    def log_metrics(self, lambda_handler: Callable = None, **kwargs):
        """Decorator that passes through to the handler."""
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **inner_kwargs):
                return func(*args, **inner_kwargs)
            return wrapper

        if lambda_handler is not None:
            return decorator(lambda_handler)
        return decorator

    def flush_metrics(self):
        """No-op for local dev."""
        pass


class Tracer:
    """Stub Tracer that does nothing."""

    def __init__(self, service: Optional[str] = None, **kwargs):
        self.service = service

    def capture_lambda_handler(self, lambda_handler: Callable = None, **kwargs):
        """Decorator that passes through to the handler."""
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **inner_kwargs):
                return func(*args, **inner_kwargs)
            return wrapper

        if lambda_handler is not None:
            return decorator(lambda_handler)
        return decorator

    def capture_method(self, method: Callable = None, **kwargs):
        """Decorator that passes through to the method."""
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **inner_kwargs):
                return func(*args, **inner_kwargs)
            return wrapper

        if method is not None:
            return decorator(method)
        return decorator

    def put_annotation(self, key: str, value: Any):
        """No-op for local dev."""
        pass

    def put_metadata(self, key: str, value: Any, namespace: Optional[str] = None):
        """No-op for local dev."""
        pass
