"""Tool abstraction layer: interfaces, mock adapters, and HTTP adapters."""

from app.tools.interfaces import (
    CRMToolInterface,
    StorageInterface,
    ToolError,
    CRMTimeoutError,
    CRMUnavailableError,
    CRMClientNotFoundError,
)
from app.tools.mock_crm import MockCRMAdapter
from app.tools.http_crm import HttpCRMAdapter

__all__ = [
    "CRMToolInterface",
    "StorageInterface",
    "ToolError",
    "CRMTimeoutError",
    "CRMUnavailableError",
    "CRMClientNotFoundError",
    "MockCRMAdapter",
    "HttpCRMAdapter",
]
