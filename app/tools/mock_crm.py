"""Mock CRM Adapter with realistic synthetic profiles, simulated latency, timeouts, and bounded retries."""

import asyncio
import time
from typing import Dict, Optional

from app.config import settings
from app.logging_config import get_logger
from app.models.client import CRMClientData, RiskProfile
from app.tools.interfaces import (
    CRMClientNotFoundError,
    CRMTimeoutError,
    CRMToolInterface,
    CRMUnavailableError,
)

logger = get_logger("tools.mock_crm")

# Deterministic synthetic profiles clearly labeled as synthetic test data
SYNTHETIC_CRM_DATABASE: Dict[str, CRMClientData] = {
    "client_001": CRMClientData(
        client_id="client_001",
        name="[SYNTHETIC] Sarah Jenkins",
        risk_profile=RiskProfile.MODERATE,
        monthly_income_declared=12500.0,
        primary_advisor_id="ADV_401",
        kyc_status="VERIFIED",
        last_interaction_date="2026-09-15",
        notes="Long-term wealth builder; plans home renovation next spring."
    ),
    "client_002": CRMClientData(
        client_id="client_002",
        name="[SYNTHETIC] David Chen",
        risk_profile=RiskProfile.AGGRESSIVE,
        monthly_income_declared=28000.0,
        primary_advisor_id="ADV_108",
        kyc_status="VERIFIED",
        last_interaction_date="2026-10-01",
        notes="High risk tolerance, tech executive, interested in private equity."
    ),
    "client_003": CRMClientData(
        client_id="client_003",
        name="[SYNTHETIC] Elena Rostova",
        risk_profile=RiskProfile.CONSERVATIVE,
        monthly_income_declared=6500.0,
        primary_advisor_id="ADV_204",
        kyc_status="PENDING",
        last_interaction_date="2026-08-20",
        notes="Retired educator; capital preservation is primary objective."
    ),
}


class MockCRMAdapter(CRMToolInterface):
    """Deterministic Mock CRM Adapter supporting timeouts, retries, and failure injection."""

    def __init__(
        self,
        base_delay_seconds: float = 0.05,
        default_timeout: float = settings.CRM_TIMEOUT_SECONDS,
        max_retries: int = settings.CRM_MAX_RETRIES,
        backoff_factor: float = settings.CRM_RETRY_BACKOFF_FACTOR,
    ):
        self.base_delay = base_delay_seconds
        self.default_timeout = default_timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    async def get_client_profile(
        self,
        client_id: str,
        timeout: Optional[float] = None,
        simulate_failure: bool = False,
        simulate_timeout: bool = False,
    ) -> CRMClientData:
        """Fetches client profile with bounded retries on transient errors."""
        effective_timeout = timeout or self.default_timeout
        start_time = time.perf_counter()

        for attempt in range(1, self.max_retries + 1):
            try:
                # Simulate timeout scenario if requested
                if simulate_timeout:
                    await asyncio.sleep(effective_timeout + 0.1)
                    raise asyncio.TimeoutError("Simulated socket timeout reading CRM stream")

                # Normal simulated network latency
                await asyncio.sleep(self.base_delay)

                # Simulate transient failure scenario
                if simulate_failure:
                    raise ConnectionError("Simulated 503 Service Unavailable from CRM cluster")

                # Retrieve client data
                if client_id in SYNTHETIC_CRM_DATABASE:
                    profile = SYNTHETIC_CRM_DATABASE[client_id]
                else:
                    # Provide deterministic default for any unknown synthetic test ID
                    profile = CRMClientData(
                        client_id=client_id,
                        name=f"[SYNTHETIC] Client {client_id}",
                        risk_profile=RiskProfile.MODERATE,
                        monthly_income_declared=10000.0,
                        primary_advisor_id="ADV_DEFAULT",
                        kyc_status="VERIFIED",
                        notes="Auto-generated deterministic synthetic test profile."
                    )

                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                logger.info(
                    f"Successfully fetched CRM profile for client {client_id}",
                    extra={
                        "agent": "DataFetcherAgent",
                        "stage": "crm_fetch",
                        "duration_ms": duration_ms,
                        "client_id": client_id,
                    }
                )
                return profile

            except (asyncio.TimeoutError, TimeoutError) as te:
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                logger.warning(
                    f"CRM request timed out for client {client_id} (attempt {attempt}/{self.max_retries})",
                    extra={
                        "agent": "DataFetcherAgent",
                        "stage": "crm_fetch_timeout",
                        "duration_ms": duration_ms,
                        "error_category": "TIMEOUT",
                        "client_id": client_id,
                    }
                )
                if attempt >= self.max_retries:
                    raise CRMTimeoutError(
                        f"CRM API timed out after {self.max_retries} attempts ({effective_timeout}s threshold)"
                    ) from te
                await asyncio.sleep(self.backoff_factor * (2 ** (attempt - 1)))

            except ConnectionError as ce:
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                logger.warning(
                    f"CRM connection error for client {client_id} (attempt {attempt}/{self.max_retries}): {ce}",
                    extra={
                        "agent": "DataFetcherAgent",
                        "stage": "crm_fetch_failure",
                        "duration_ms": duration_ms,
                        "error_category": "SERVICE_UNAVAILABLE",
                        "client_id": client_id,
                    }
                )
                if attempt >= self.max_retries:
                    raise CRMUnavailableError(
                        f"CRM service unavailable after {self.max_retries} attempts: {ce}"
                    ) from ce
                await asyncio.sleep(self.backoff_factor * (2 ** (attempt - 1)))

        raise CRMUnavailableError("CRM request failed after retry bounds exhausted.")

    async def health_check(self) -> bool:
        """Simple liveness probe."""
        return True
