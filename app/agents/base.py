"""Base agent abstraction providing execution lifecycle tracing, error capture, and timing."""

import time
from abc import ABC, abstractmethod
from typing import Any, Optional

from app.logging_config import get_logger
from app.memory.session_memory import SessionContext


class BaseAgent(ABC):
    """Abstract Base Class for specialized agents in the Wealth Advisor system."""

    def __init__(self, name: str, role_description: str):
        self.name = name
        self.role_description = role_description
        self.logger = get_logger(f"agent.{name.lower()}")

    async def execute_stage(
        self,
        stage_name: str,
        context: SessionContext,
        action_coro,
        *args,
        **kwargs
    ) -> Any:
        """Executes an async agent action while recording execution timings and traces."""
        start_time = time.perf_counter()
        context.set_stage(f"{self.name}:{stage_name}")

        try:
            result = await action_coro(*args, **kwargs)
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            context.add_trace(
                agent=self.name,
                stage=stage_name,
                duration_ms=duration_ms,
                status="SUCCESS"
            )
            self.logger.info(
                f"Agent {self.name} completed stage {stage_name} in {round(duration_ms, 2)}ms",
                extra={
                    "agent": self.name,
                    "stage": stage_name,
                    "duration_ms": round(duration_ms, 2),
                    "client_id": context.client_id,
                }
            )
            return result
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            context.add_trace(
                agent=self.name,
                stage=stage_name,
                duration_ms=duration_ms,
                status="ERROR",
                notes=str(e)
            )
            self.logger.error(
                f"Agent {self.name} failed at stage {stage_name}: {e}",
                extra={
                    "agent": self.name,
                    "stage": stage_name,
                    "duration_ms": round(duration_ms, 2),
                    "error_category": type(e).__name__,
                    "client_id": context.client_id,
                },
                exc_info=True
            )
            raise e
