import time
from types import SimpleNamespace

import pytest

from app.ai.flow_manager import DevPipelineManager
from app.services.memory_service import MemoryService
from app.services.user_evolution_service import UserEvolutionService


def _pipeline(**overrides):
    data = {
        "pipeline_id": "pipe-001",
        "project_id": "42",
        "user_request": "Build a polished wealth-admin-home user permission page",
        "status": "completed",
        "current_stage": "report",
        "retry_count": 2,
        "tenant_id": 1,
        "creator_id": 7,
        "skill_config": '{"frontend_tech":"React + Ant Design","backend_tech":"Go + FastAPI"}',
        "workspace_path": "F:/AI/admin-platform/.workspace/pipe-001",
        "git_commit_sha": "abc123",
        "update_time": int(time.time() * 1000),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _stages():
    return {
        "requirement": {
            "status": "completed",
            "structured_output": {
                "pm_quality": {
                    "score": 96,
                    "permission_points": ["user:list", "user:assign-role"],
                }
            },
        },
        "prototype": {
            "status": "completed",
            "structured_output": {
                "preview_quality": {
                    "score": 91,
                    "ready_for_preview": True,
                }
            },
        },
        "testing": {
            "status": "completed",
            "structured_output": {
                "tests_passed": True,
                "actual_test_result": "16 passed",
            },
        },
    }


def test_user_session_id_is_scoped_by_tenant_and_creator():
    assert UserEvolutionService.user_session_id(tenant_id=1, user_id=7) == "user:1:7"


def test_completion_summary_captures_request_quality_and_delivery_signals():
    summary = UserEvolutionService.build_completion_summary(_pipeline(), _stages())

    assert "Build a polished wealth-admin-home user permission page" in summary
    assert "pipe-001" in summary
    assert "React + Ant Design" in summary
    assert "Go + FastAPI" in summary
    assert "requirement: completed" in summary
    assert "pm_quality.score=96" in summary
    assert "preview_quality.score=91" in summary
    assert "tests_passed=True" in summary
    assert "retry_count=2" in summary


def test_profile_snapshot_keeps_existing_profile_and_appends_latest_requirement():
    existing = "# User Evolution Profile\n\n## Stable Preferences\n- Likes polished admin previews"
    profile = UserEvolutionService.build_profile_snapshot(
        existing_profile=existing,
        completion_summary="completed requirement summary",
        pipeline=_pipeline(),
        stages=_stages(),
    )

    assert "Likes polished admin previews" in profile
    assert "Build a polished wealth-admin-home user permission page" in profile
    assert "completed requirement summary" in profile
    assert "Last Completed Requirement" in profile


def test_format_user_memory_context_prioritizes_profile_then_recent_requirements():
    profile = SimpleNamespace(
        memory_type="semantic",
        key_info="user_profile:1:7",
        content="# User Evolution Profile\n- Prefers high quality preview",
    )
    episode = SimpleNamespace(
        memory_type="episodic",
        key_info="requirement_done:pipe-001",
        content="completed requirement summary",
    )

    context = UserEvolutionService.format_user_memory_context([episode, profile])

    assert "User Evolution Profile" in context
    assert "Prefers high quality preview" in context
    assert "Recent Completed Requirements" in context
    assert "completed requirement summary" in context


@pytest.mark.asyncio
async def test_pipeline_memory_retrieval_injects_user_evolution_context(monkeypatch):
    class FakeSession:
        async def flush(self):
            return None

    async def fake_get_memories(**kwargs):
        assert kwargs["session_id"] == "pipe-001"
        return [SimpleNamespace(agent_type="PM", content="stage lesson")]

    async def fake_get_user_memory_context(**kwargs):
        assert kwargs["tenant_id"] == 1
        assert kwargs["user_id"] == 7
        return "## User Evolution Profile / 用户画像\n- Prefers polished preview"

    monkeypatch.setattr(MemoryService, "get_memories", fake_get_memories)
    monkeypatch.setattr(
        UserEvolutionService,
        "get_user_memory_context",
        fake_get_user_memory_context,
    )

    manager = object.__new__(DevPipelineManager)
    context = await manager._retrieve_memories(
        "pipe-001",
        "requirement",
        tenant_id=1,
        session=FakeSession(),
        creator_id=7,
    )

    assert "stage lesson" in context
    assert "User Evolution Profile" in context
    assert "Prefers polished preview" in context
