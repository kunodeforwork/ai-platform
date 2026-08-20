"""SQLAlchemy persistence infrastructure for Agent configurations."""

from collections.abc import Callable
from datetime import UTC, datetime
from threading import Lock
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    Uuid,
    create_engine,
    update,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from chint_ai_platform.agent_runs import PersistedAgentRun
from chint_ai_platform.agents import Agent
from chint_ai_platform.settings import DatabaseNotConfiguredError, DatabaseSettings


class DatabaseUnavailableError(RuntimeError):
    """Raised when database infrastructure cannot complete an operation."""


class Base(DeclarativeBase):
    pass


class AgentRow(Base):
    __tablename__ = "agents"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(
        String(500), nullable=False, default="", server_default=""
    )
    system_prompt: Mapped[str] = mapped_column(String(4000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentRunRow(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_agent_runs_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    agent_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agents.id"), nullable=True, index=True
    )
    input: Mapped[str] = mapped_column(Text, nullable=False)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DatabaseSessionScope:
    """Lazily own one request-scoped Session and its transaction lifecycle."""

    def __init__(self, factory: Callable[[], Session]) -> None:
        self._factory = factory
        self._session: Session | None = None
        self._lock = Lock()

    @property
    def session(self) -> Session:
        if self._session is None:
            with self._lock:
                if self._session is None:
                    try:
                        self._session = self._factory()
                    except DatabaseNotConfiguredError:
                        raise
                    except Exception as error:
                        raise DatabaseUnavailableError("Database is unavailable") from error
        return self._session

    def commit(self) -> None:
        if self._session is not None:
            self._call(self._session.commit)

    def rollback(self) -> None:
        if self._session is not None:
            self._call(self._session.rollback)

    def close(self) -> None:
        if self._session is not None:
            self._call(self._session.close)

    @staticmethod
    def _call(operation: Callable[[], None]) -> None:
        try:
            operation()
        except SQLAlchemyError as error:
            raise DatabaseUnavailableError("Database is unavailable") from error


class SqlAlchemyAgentRepository:
    def __init__(self, scope: DatabaseSessionScope) -> None:
        self._scope = scope

    def add(self, agent: Agent) -> None:
        try:
            self._scope.session.add(
                AgentRow(
                    id=UUID(agent.id),
                    name=agent.name,
                    description=agent.description,
                    system_prompt=agent.system_prompt,
                    created_at=agent.created_at,
                )
            )
        except SQLAlchemyError as error:
            raise DatabaseUnavailableError("Database is unavailable") from error

    def get(self, agent_id: str) -> Agent | None:
        try:
            row = self._scope.session.get(AgentRow, UUID(agent_id))
        except SQLAlchemyError as error:
            raise DatabaseUnavailableError("Database is unavailable") from error
        if row is None:
            return None
        created_at = row.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return Agent(
            id=str(row.id),
            name=row.name,
            description=row.description,
            system_prompt=row.system_prompt,
            created_at=created_at,
        )


class SqlAlchemyAgentRunRepository:
    def __init__(self, scope: DatabaseSessionScope) -> None:
        self._scope = scope

    def add(self, run: PersistedAgentRun) -> None:
        try:
            self._scope.session.add(self._to_row(run))
        except SQLAlchemyError as error:
            raise DatabaseUnavailableError("Database is unavailable") from error

    def get(self, run_id: str) -> PersistedAgentRun | None:
        try:
            row = self._scope.session.get(AgentRunRow, UUID(run_id))
        except SQLAlchemyError as error:
            raise DatabaseUnavailableError("Database is unavailable") from error
        return None if row is None else self._to_domain(row)

    def update(self, run: PersistedAgentRun) -> None:
        try:
            result = self._scope.session.execute(
                update(AgentRunRow)
                .where(AgentRunRow.id == UUID(run.id), AgentRunRow.status == "running")
                .values(
                    output=run.output,
                    status=run.status,
                    error_code=run.error_code,
                    completed_at=run.completed_at,
                )
            )
            if result.rowcount != 1:
                raise DatabaseUnavailableError("Database is unavailable")
        except SQLAlchemyError as error:
            raise DatabaseUnavailableError("Database is unavailable") from error

    @staticmethod
    def _to_row(run: PersistedAgentRun) -> AgentRunRow:
        return AgentRunRow(
            id=UUID(run.id),
            agent_id=None if run.agent_id is None else UUID(run.agent_id),
            input=run.input,
            output=run.output,
            status=run.status,
            error_code=run.error_code,
            created_at=run.created_at,
            completed_at=run.completed_at,
        )

    @staticmethod
    def _to_domain(row: AgentRunRow) -> PersistedAgentRun:
        created_at = row.created_at
        completed_at = row.completed_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if completed_at is not None and completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=UTC)
        return PersistedAgentRun(
            id=str(row.id),
            agent_id=None if row.agent_id is None else str(row.agent_id),
            input=row.input,
            output=row.output,
            status=row.status,  # type: ignore[arg-type]
            error_code=row.error_code,
            created_at=created_at,
            completed_at=completed_at,
        )


_SESSION_FACTORY: sessionmaker[Session] | None = None
_SESSION_FACTORY_LOCK = Lock()


def get_session_factory() -> sessionmaker[Session]:
    global _SESSION_FACTORY
    if _SESSION_FACTORY is None:
        with _SESSION_FACTORY_LOCK:
            if _SESSION_FACTORY is None:
                try:
                    settings = DatabaseSettings.from_environment()
                    engine = create_engine(settings.url)
                    _SESSION_FACTORY = sessionmaker(engine)
                except DatabaseNotConfiguredError:
                    raise
                except Exception as error:
                    raise DatabaseUnavailableError("Database is unavailable") from error
    return _SESSION_FACTORY
