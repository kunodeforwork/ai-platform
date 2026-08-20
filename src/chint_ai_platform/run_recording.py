"""Short-transaction persistence for Agent run state changes."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypeVar
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from chint_ai_platform.agent_runs import (
    AgentRunNotFoundError,
    AgentRunStateError,
    PersistedAgentRun,
)
from chint_ai_platform.persistence import (
    DatabaseSessionScope,
    DatabaseUnavailableError,
    SqlAlchemyAgentRunRepository,
)

T = TypeVar("T")


class SqlAlchemyAgentRunRecorder:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._session_factory = session_factory
        self._id_factory = id_factory
        self._clock = clock

    def start(self, agent_id: str | None, input: str) -> PersistedAgentRun:
        run = PersistedAgentRun.start(str(self._id_factory()), agent_id, input, self._clock())

        def add(repository: SqlAlchemyAgentRunRepository) -> PersistedAgentRun:
            repository.add(run)
            return run

        return self._transaction(add)

    def complete(self, run_id: str, output: str) -> PersistedAgentRun:
        return self._transition(run_id, lambda run: run.complete(output, self._clock()))

    def fail(self, run_id: str, error_code: str) -> PersistedAgentRun:
        return self._transition(run_id, lambda run: run.fail(error_code, self._clock()))

    def get(self, run_id: str) -> PersistedAgentRun:
        def load(repository: SqlAlchemyAgentRunRepository) -> PersistedAgentRun:
            run = repository.get(run_id)
            if run is None:
                raise AgentRunNotFoundError(run_id)
            return run

        return self._transaction(load)

    def _transition(
        self,
        run_id: str,
        transition: Callable[[PersistedAgentRun], PersistedAgentRun],
    ) -> PersistedAgentRun:
        def update(repository: SqlAlchemyAgentRunRepository) -> PersistedAgentRun:
            run = repository.get(run_id)
            if run is None:
                raise DatabaseUnavailableError("Database is unavailable")
            try:
                changed = transition(run)
            except AgentRunStateError as error:
                raise DatabaseUnavailableError("Database is unavailable") from error
            repository.update(changed)
            return changed

        return self._transaction(update)

    def _transaction(self, operation: Callable[[SqlAlchemyAgentRunRepository], T]) -> T:
        scope = DatabaseSessionScope(self._session_factory)
        try:
            result = operation(SqlAlchemyAgentRunRepository(scope))
            scope.commit()
            return result
        except Exception:
            scope.rollback()
            raise
        finally:
            scope.close()
