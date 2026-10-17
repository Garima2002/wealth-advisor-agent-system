"""Production-grade HTTP CRM Adapter template demonstrating real external API integration."""

from typing import Optional
import httpx

from app.config import settings
from app.logging_config import get_logger
from app.models.client import CRMClientData, RiskProfile
from app.tools.interfaces import (
    CRMClientNotFoundError,
    CRMTimeoutError,
    CRMToolInterface,
    CRMUnavailableError,
)

logger = get_logger("tools.http_crm")


class HttpCRMAdapter(CRMToolInterface):
    """Production implementation of CRMToolInterface connecting to an external REST CRM API."""

    def __init__(
        self,
        base_url: str = "https://api.crm.internal/v1",
        api_key: Optional[str] = None,
        default_timeout: float = settings.CRM_TIMEOUT_SECONDS,
        max_retries: int = settings.CRM_MAX_RETRIES,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_timeout = default_timeout
        self.max_retries = max_retries

    def _get_headers(self) -> dict:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def get_client_profile(
        self,
        client_id: str,
        timeout: Optional[float] = None,
        simulate_failure: bool = False,
        simulate_timeout: bool = False,
    ) -> CRMClientData:
        """Fetch client profile from external HTTP CRM API with timeouts and status mapping."""
        effective_timeout = timeout or self.default_timeout
        url = f"{self.base_url}/clients/{client_id}"

        async with httpx.AsyncClient(timeout=effective_timeout) as client:
            try:
                response = await client.get(url, headers=self._get_headers())
                if response.status_code == 404:
                    raise CRMClientNotFoundError(f"Client {client_id} not found in remote CRM")
                response.raise_for_status()
                data = response.json()

                return CRMClientData(
                    client_id=client_id,
                    name=data.get("full_name", f"Client {client_id}"),
                    risk_profile=RiskProfile(data.get("risk_profile", "moderate").lower()),
                    monthly_income_declared=data.get("annual_income", 0) / 12.0 if "annual_income" in data else None,
                    primary_advisor_id=data.get("advisor_id"),
                    kyc_status=data.get("kyc_status", "UNKNOWN"),
                    last_interaction_date=data.get("last_contact_date"),
                    notes=data.get("notes"),
                )
            except httpx.TimeoutException as te:
                logger.error(
                    f"HTTP CRM timeout for client {client_id}: {te}",
                    extra={"agent": "DataFetcherAgent", "error_category": "TIMEOUT", "client_id": client_id}
                )
                raise CRMTimeoutError(f"CRM API timed out after {effective_timeout}s") from te
            except httpx.HTTPStatusError as hse:
                logger.error(
                    f"HTTP CRM status error {hse.response.status_code} for client {client_id}",
                    extra={"agent": "DataFetcherAgent", "error_category": "CRM_HTTP_ERROR", "client_id": client_id}
                )
                raise CRMUnavailableError(f"CRM returned HTTP {hse.response.status_code}") from hse
            except httpx.RequestError as re:
                logger.error(
                    f"HTTP CRM request network error: {re}",
                    extra={"agent": "DataFetcherAgent", "error_category": "NETWORK_ERROR", "client_id": client_id}
                )
                raise CRMUnavailableError(f"CRM network connection failed: {re}") from re

    async def health_check(self) -> bool:
        """Probe CRM health endpoint."""
        async with httpx.AsyncClient(timeout=3.0) as client:
            try:
                resp = await client.get(f"{self.base_url}/health", headers=self._get_headers())
                return resp.status_code == 200
            except Exception:
                return False
