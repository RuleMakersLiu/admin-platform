"""User evolution memory service.

This service turns completed development pipelines into durable user-level
memories. It intentionally reuses agent_memory so the feature can ship without
schema changes while keeping pipeline-stage memory and user profile memory
separate.
"""
import json
import time
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_models import AgentMemory
from app.services.memory_service import MemoryService, MemoryType


class UserEvolutionService:
    """Build and persist user-level learning from completed requirements."""

    AGENT_TYPE = "USER"
    PROFILE_IMPORTANCE = 95
    COMPLETION_IMPORTANCE = 85
    PROFILE_MAX_CHARS = 12000
    COMPLETION_MAX_CHARS = 6000
    EPISODIC_EXPIRE_HOURS = 24 * 365
    MEMORY_TYPES = [MemoryType.SEMANTIC, MemoryType.EPISODIC, MemoryType.LONG_TERM]

    @staticmethod
    def user_session_id(tenant_id: int, user_id: int) -> str:
        """Return the stable memory bucket for one tenant-scoped user."""
        return f"user:{tenant_id}:{user_id}"

    @staticmethod
    def profile_key(tenant_id: int, user_id: int) -> str:
        return f"user_profile:{tenant_id}:{user_id}"

    @staticmethod
    def completion_key(pipeline_id: str) -> str:
        return f"requirement_done:{pipeline_id}"

    @staticmethod
    def safe_project_id(project_id: Any) -> Optional[int]:
        if project_id in (None, ""):
            return None
        try:
            return int(project_id)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _one_line(value: Any, max_len: int = 300) -> str:
        text = "" if value is None else str(value)
        text = " ".join(text.split())
        if len(text) <= max_len:
            return text
        return f"{text[:max_len - 3]}..."

    @staticmethod
    def _load_skill_config(pipeline: Any) -> Dict[str, Any]:
        raw = getattr(pipeline, "skill_config", "") or "{}"
        if isinstance(raw, dict):
            return raw
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _structured_output(stage: Dict[str, Any]) -> Dict[str, Any]:
        structured = stage.get("structured_output") or {}
        return structured if isinstance(structured, dict) else {}

    @staticmethod
    def _quality_lines(stage_key: str, stage: Dict[str, Any]) -> List[str]:
        structured = UserEvolutionService._structured_output(stage)
        lines: List[str] = []

        pm_quality = structured.get("pm_quality")
        if isinstance(pm_quality, dict) and "score" in pm_quality:
            lines.append(f"  - pm_quality.score={pm_quality.get('score')}")
            permission_points = pm_quality.get("permission_points")
            if permission_points:
                lines.append(
                    f"  - permission_points={UserEvolutionService._one_line(permission_points)}"
                )

        design_quality = structured.get("design_quality")
        if isinstance(design_quality, dict) and "score" in design_quality:
            lines.append(f"  - design_quality.score={design_quality.get('score')}")

        preview_quality = structured.get("preview_quality")
        if isinstance(preview_quality, dict):
            if "score" in preview_quality:
                lines.append(f"  - preview_quality.score={preview_quality.get('score')}")
            if "ready_for_preview" in preview_quality:
                lines.append(
                    f"  - ready_for_preview={preview_quality.get('ready_for_preview')}"
                )

        if "tests_passed" in structured:
            lines.append(f"  - tests_passed={structured.get('tests_passed')}")
        if "actual_test_result" in structured:
            lines.append(
                f"  - actual_test_result={UserEvolutionService._one_line(structured.get('actual_test_result'))}"
            )

        error = stage.get("error")
        if error:
            lines.append(f"  - error={UserEvolutionService._one_line(error)}")

        if not lines and stage_key in ("commit", "deploy", "report"):
            output = stage.get("output")
            if output:
                lines.append(f"  - output={UserEvolutionService._one_line(output, 180)}")

        return lines

    @staticmethod
    def _ordered_stage_keys(stages: Dict[str, Any]) -> List[str]:
        preferred = [
            "requirement",
            "page_design",
            "prototype",
            "delivery",
            "frontend_dev",
            "backend_dev",
            "code_review",
            "testing",
            "commit",
            "deploy",
            "report",
        ]
        remaining = [key for key in stages.keys() if key not in preferred]
        return [key for key in preferred if key in stages] + remaining

    @staticmethod
    def build_completion_summary(pipeline: Any, stages: Dict[str, Any]) -> str:
        """Build a compact, searchable memory for one completed requirement."""
        config = UserEvolutionService._load_skill_config(pipeline)
        frontend_tech = config.get("frontend_tech") or config.get("frontend") or ""
        backend_tech = config.get("backend_tech") or config.get("backend") or ""

        lines = [
            "# Completed Requirement Summary",
            f"pipeline_id={getattr(pipeline, 'pipeline_id', '')}",
            f"tenant_id={getattr(pipeline, 'tenant_id', '')}",
            f"user_id={getattr(pipeline, 'creator_id', '')}",
            f"project_id={getattr(pipeline, 'project_id', '')}",
            f"status={getattr(pipeline, 'status', '')}",
            f"retry_count={getattr(pipeline, 'retry_count', 0) or 0}",
            f"user_request={UserEvolutionService._one_line(getattr(pipeline, 'user_request', ''))}",
        ]

        if frontend_tech or backend_tech:
            lines.extend([
                "",
                "## Tech Stack",
                f"- frontend={frontend_tech}",
                f"- backend={backend_tech}",
            ])

        lines.extend(["", "## Stage Results"])
        for stage_key in UserEvolutionService._ordered_stage_keys(stages):
            stage = stages.get(stage_key) or {}
            status = stage.get("status", "unknown")
            lines.append(f"- {stage_key}: {status}")
            lines.extend(UserEvolutionService._quality_lines(stage_key, stage))

        workspace_path = getattr(pipeline, "workspace_path", "") or ""
        commit_sha = getattr(pipeline, "git_commit_sha", "") or ""
        if workspace_path or commit_sha:
            lines.extend(["", "## Delivery Metadata"])
            if workspace_path:
                lines.append(f"- workspace_path={workspace_path}")
            if commit_sha:
                lines.append(f"- git_commit_sha={commit_sha}")

        return "\n".join(lines)[: UserEvolutionService.COMPLETION_MAX_CHARS]

    @staticmethod
    def _infer_preference_signals(pipeline: Any, stages: Dict[str, Any]) -> List[str]:
        signals: List[str] = []
        request = UserEvolutionService._one_line(getattr(pipeline, "user_request", ""), 180)
        if request:
            signals.append(f"Recent demand pattern: {request}")

        config = UserEvolutionService._load_skill_config(pipeline)
        frontend_tech = config.get("frontend_tech") or config.get("frontend")
        backend_tech = config.get("backend_tech") or config.get("backend")
        if frontend_tech:
            signals.append(f"Frontend stack signal: {frontend_tech}")
        if backend_tech:
            signals.append(f"Backend stack signal: {backend_tech}")

        requirement = stages.get("requirement") or {}
        pm_quality = UserEvolutionService._structured_output(requirement).get("pm_quality")
        if isinstance(pm_quality, dict) and pm_quality.get("permission_points"):
            signals.append("Cares about explicit permission points and RBAC/ABAC detail.")

        prototype = stages.get("prototype") or {}
        preview_quality = UserEvolutionService._structured_output(prototype).get("preview_quality")
        if isinstance(preview_quality, dict) and preview_quality.get("ready_for_preview"):
            signals.append("Values a complete, reviewable frontend preview.")

        retry_count = getattr(pipeline, "retry_count", 0) or 0
        if retry_count:
            signals.append(f"Delivery had retry_count={retry_count}; future runs should address known gaps earlier.")

        return signals

    @staticmethod
    def build_profile_snapshot(
        existing_profile: str,
        completion_summary: str,
        pipeline: Any,
        stages: Dict[str, Any],
    ) -> str:
        """Append the latest completed demand to the user's semantic profile."""
        now = int(time.time() * 1000)
        existing = (existing_profile or "").strip()
        if not existing:
            existing = (
                "# User Evolution Profile\n\n"
                "This profile summarizes the user's recurring delivery preferences and lessons."
            )

        request = UserEvolutionService._one_line(getattr(pipeline, "user_request", ""), 240)
        signals = UserEvolutionService._infer_preference_signals(pipeline, stages)
        signal_lines = "\n".join(f"- {signal}" for signal in signals) or "- No strong signal yet."

        latest_block = "\n".join([
            "",
            "## Last Completed Requirement",
            f"- update_time={now}",
            f"- pipeline_id={getattr(pipeline, 'pipeline_id', '')}",
            f"- user_request={request}",
            "",
            "## Latest Preference Signals",
            signal_lines,
            "",
            "## Latest Completion Summary",
            completion_summary.strip(),
        ])

        profile = f"{existing}\n{latest_block}"
        if len(profile) <= UserEvolutionService.PROFILE_MAX_CHARS:
            return profile

        # Keep the header and the newest evidence when the profile grows large.
        header = "# User Evolution Profile\n\n"
        tail_len = UserEvolutionService.PROFILE_MAX_CHARS - len(header)
        return header + profile[-tail_len:]

    @staticmethod
    def format_user_memory_context(memories: Iterable[AgentMemory]) -> str:
        """Format user-level memories for prompt injection."""
        profile_parts: List[str] = []
        episode_parts: List[str] = []

        for memory in memories:
            content = (getattr(memory, "content", "") or "").strip()
            if not content:
                continue

            key_info = getattr(memory, "key_info", "") or ""
            memory_type = getattr(memory, "memory_type", "") or ""
            if memory_type == MemoryType.SEMANTIC or key_info.startswith("user_profile:"):
                profile_parts.append(content)
            else:
                episode_parts.append(content)

        if not profile_parts and not episode_parts:
            return ""

        sections: List[str] = []
        if profile_parts:
            sections.append("## User Evolution Profile / 用户画像\n" + "\n\n".join(profile_parts))
        if episode_parts:
            sections.append(
                "## Recent Completed Requirements / 最近完成需求\n"
                + "\n\n".join(episode_parts[:5])
            )
        return "\n\n".join(sections)

    @staticmethod
    async def _find_memory(
        db: AsyncSession,
        session_id: str,
        key_info: str,
        memory_type: str,
        tenant_id: int,
    ) -> Optional[AgentMemory]:
        stmt = select(AgentMemory).where(
            AgentMemory.session_id == session_id,
            AgentMemory.key_info == key_info,
            AgentMemory.memory_type == memory_type,
            AgentMemory.tenant_id == tenant_id,
            AgentMemory.is_deleted == 0,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def _upsert_memory(
        db: AsyncSession,
        session_id: str,
        key_info: str,
        content: str,
        tenant_id: int,
        memory_type: str,
        project_id: Optional[int],
        importance: int,
        expire_hours: Optional[int] = None,
    ) -> AgentMemory:
        existing = await UserEvolutionService._find_memory(
            db=db,
            session_id=session_id,
            key_info=key_info,
            memory_type=memory_type,
            tenant_id=tenant_id,
        )
        now = int(time.time() * 1000)
        if existing:
            existing.project_id = project_id
            existing.agent_type = UserEvolutionService.AGENT_TYPE
            existing.content = content
            existing.importance = importance
            existing.last_access_time = now
            existing.update_time = now
            if expire_hours is not None:
                existing.expire_time = now + expire_hours * 60 * 60 * 1000
            await db.flush()
            return existing

        return await MemoryService.save_memory(
            db=db,
            session_id=session_id,
            agent_type=UserEvolutionService.AGENT_TYPE,
            content=content,
            tenant_id=tenant_id,
            memory_type=memory_type,
            key_info=key_info,
            project_id=project_id,
            importance=importance,
            expire_hours=expire_hours,
        )

    @staticmethod
    async def summarize_completed_requirement(
        db: AsyncSession,
        pipeline: Any,
        stages: Dict[str, Any],
    ) -> None:
        """Persist the completed requirement and refresh the user's profile."""
        tenant_id = int(getattr(pipeline, "tenant_id", 0) or 0)
        user_id = int(getattr(pipeline, "creator_id", 0) or 0)
        pipeline_id = getattr(pipeline, "pipeline_id", "") or ""
        if not tenant_id or not user_id or not pipeline_id:
            return

        session_id = UserEvolutionService.user_session_id(tenant_id, user_id)
        project_id = UserEvolutionService.safe_project_id(getattr(pipeline, "project_id", None))
        completion_summary = UserEvolutionService.build_completion_summary(pipeline, stages)

        await UserEvolutionService._upsert_memory(
            db=db,
            session_id=session_id,
            key_info=UserEvolutionService.completion_key(pipeline_id),
            content=completion_summary,
            tenant_id=tenant_id,
            memory_type=MemoryType.EPISODIC,
            project_id=project_id,
            importance=UserEvolutionService.COMPLETION_IMPORTANCE,
            expire_hours=UserEvolutionService.EPISODIC_EXPIRE_HOURS,
        )

        profile_key = UserEvolutionService.profile_key(tenant_id, user_id)
        existing_profile = await UserEvolutionService._find_memory(
            db=db,
            session_id=session_id,
            key_info=profile_key,
            memory_type=MemoryType.SEMANTIC,
            tenant_id=tenant_id,
        )
        profile_content = UserEvolutionService.build_profile_snapshot(
            existing_profile=existing_profile.content if existing_profile else "",
            completion_summary=completion_summary,
            pipeline=pipeline,
            stages=stages,
        )
        await UserEvolutionService._upsert_memory(
            db=db,
            session_id=session_id,
            key_info=profile_key,
            content=profile_content,
            tenant_id=tenant_id,
            memory_type=MemoryType.SEMANTIC,
            project_id=project_id,
            importance=UserEvolutionService.PROFILE_IMPORTANCE,
        )

    @staticmethod
    async def get_user_memory_context(
        db: AsyncSession,
        tenant_id: int,
        user_id: int,
        limit: int = 6,
    ) -> str:
        """Return formatted memories for a user, suitable for prompt context."""
        if not tenant_id or not user_id:
            return ""

        now = int(time.time() * 1000)
        stmt = (
            select(AgentMemory)
            .where(
                AgentMemory.session_id == UserEvolutionService.user_session_id(tenant_id, user_id),
                AgentMemory.tenant_id == tenant_id,
                AgentMemory.memory_type.in_(UserEvolutionService.MEMORY_TYPES),
                AgentMemory.is_deleted == 0,
                or_(AgentMemory.expire_time.is_(None), AgentMemory.expire_time > now),
            )
            .order_by(desc(AgentMemory.importance), desc(AgentMemory.update_time))
            .limit(limit)
        )
        result = await db.execute(stmt)
        memories = list(result.scalars().all())

        for memory in memories:
            memory.access_count += 1
            memory.last_access_time = now
        await db.flush()

        return UserEvolutionService.format_user_memory_context(memories)
