from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from chint_ai_platform.persistence import Base, DatabaseUnavailableError
from chint_ai_platform.run_recording import SqlAlchemyAgentRunRecorder


def test_recorder_commits_running_and_terminal_states_in_separate_transactions(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'recording.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    created_at = datetime(2026, 8, 20, 9, 30, tzinfo=UTC)
    times = iter([created_at, created_at + timedelta(seconds=2)])
    recorder = SqlAlchemyAgentRunRecorder(factory, clock=lambda: next(times))

    running = recorder.start(None, "分析异常")
    completed = recorder.complete(running.id, "分析完成")
    loaded = recorder.get(running.id)

    assert str(UUID(running.id)) == running.id
    assert running.status == "running"
    assert completed.status == "completed"
    assert loaded == completed


def test_recorder_persists_failed_state(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'recording.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    recorder = SqlAlchemyAgentRunRecorder(factory)

    running = recorder.start(None, "分析异常")
    failed = recorder.fail(running.id, "deepseek_timeout")

    assert recorder.get(running.id) == failed


def test_recorder_uses_independent_sessions_and_rolls_back_failed_commit(tmp_path) -> None:
    events: list[tuple[str, int]] = []

    class TrackingSession(Session):
        def commit(self) -> None:
            events.append(("commit", id(self)))
            super().commit()

        def rollback(self) -> None:
            events.append(("rollback", id(self)))
            super().rollback()

        def close(self) -> None:
            events.append(("close", id(self)))
            super().close()

    engine = create_engine(f"sqlite:///{tmp_path / 'recording.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, class_=TrackingSession)
    sessions: list[TrackingSession] = []

    def tracking_factory() -> TrackingSession:
        session = factory()
        sessions.append(session)
        return session

    fixed_id = UUID("d6109938-c9ba-4bc0-a20a-27e1b1fceb67")
    recorder = SqlAlchemyAgentRunRecorder(tracking_factory, id_factory=lambda: fixed_id)

    running = recorder.start(None, "输入")
    recorder.complete(running.id, "输出")

    with pytest.raises(DatabaseUnavailableError):
        recorder.start(None, "重复主键")

    committed_sessions = {session_id for event, session_id in events if event == "commit"}
    closed_sessions = {session_id for event, session_id in events if event == "close"}
    rolled_back_sessions = {session_id for event, session_id in events if event == "rollback"}
    assert len(sessions) == 3
    assert len(committed_sessions) == 3
    assert committed_sessions <= closed_sessions
    assert rolled_back_sessions
    assert rolled_back_sessions <= closed_sessions


def test_recorder_maps_unknown_internal_transition_to_database_failure(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'recording.db'}")
    Base.metadata.create_all(engine)
    recorder = SqlAlchemyAgentRunRecorder(sessionmaker(engine))

    with pytest.raises(DatabaseUnavailableError, match="Database is unavailable"):
        recorder.complete("8e52ea3a-f9ec-41b8-9464-e21e4c4ef9e9", "输出")
