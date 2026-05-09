"""AI分身相关模型"""
import time
from decimal import Decimal
from typing import Optional

from sqlalchemy import BigInteger, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AgentProject(Base):
    """项目模型"""
    __tablename__ = "agent_project"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_code: Mapped[str] = mapped_column(String(64), unique=True)
    project_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    priority: Mapped[str] = mapped_column(String(16), default="P2")
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    creator_id: Mapped[int] = mapped_column(BigInteger)
    start_time: Mapped[Optional[int]] = mapped_column(BigInteger)
    end_time: Mapped[Optional[int]] = mapped_column(BigInteger)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)
    pipeline_prompts: Mapped[Optional[str]] = mapped_column(Text)

    def to_dict(self):
        return {
            "id": self.id,
            "projectCode": self.project_code,
            "projectName": self.project_name,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "tenantId": self.tenant_id,
            "creatorId": self.creator_id,
            "startTime": self.start_time,
            "endTime": self.end_time,
            "createTime": self.create_time,
            "updateTime": self.update_time,
        }


class AgentSession(Base):
    """会话模型"""
    __tablename__ = "agent_session"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True)
    project_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(255))
    current_agent: Mapped[Optional[str]] = mapped_column(String(32))
    workflow_stage: Mapped[Optional[str]] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="active")
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    last_message_time: Mapped[Optional[int]] = mapped_column(BigInteger)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)


class AgentMessage(Base):
    """消息模型"""
    __tablename__ = "agent_message"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    msg_id: Mapped[str] = mapped_column(String(64), unique=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    project_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    from_agent: Mapped[str] = mapped_column(String(32), index=True)
    to_agent: Mapped[str] = mapped_column(String(32), index=True)
    msg_type: Mapped[str] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text)
    payload: Mapped[Optional[str]] = mapped_column(Text)
    token_count: Mapped[Optional[int]] = mapped_column(Integer)
    model_used: Mapped[Optional[str]] = mapped_column(String(64))
    parent_msg_id: Mapped[Optional[str]] = mapped_column(String(64))
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))


class AgentConfig(Base):
    """分身配置模型"""
    __tablename__ = "agent_config"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    config_id: Mapped[str] = mapped_column(String(64), unique=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    agent_type: Mapped[str] = mapped_column(String(32), index=True)
    config_name: Mapped[str] = mapped_column(String(255))
    system_prompt: Mapped[Optional[str]] = mapped_column(Text)
    model_config: Mapped[Optional[str]] = mapped_column(Text)
    tool_config: Mapped[Optional[str]] = mapped_column(Text)
    behavior_config: Mapped[Optional[str]] = mapped_column(Text)
    is_default: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)


class AgentTask(Base):
    """任务模型"""
    __tablename__ = "agent_task"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), unique=True)
    project_id: Mapped[int] = mapped_column(BigInteger, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(64))
    parent_task_id: Mapped[Optional[str]] = mapped_column(String(64))
    task_code: Mapped[Optional[str]] = mapped_column(String(64))
    task_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    task_type: Mapped[str] = mapped_column(String(32))
    assignee: Mapped[Optional[str]] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    priority: Mapped[str] = mapped_column(String(16), default="P2")
    estimated_hours: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 1))
    actual_hours: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 1))
    progress: Mapped[int] = mapped_column(Integer, default=0)
    dependencies: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[Optional[str]] = mapped_column(String(255))
    start_time: Mapped[Optional[int]] = mapped_column(BigInteger)
    end_time: Mapped[Optional[int]] = mapped_column(BigInteger)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)

    def to_dict(self):
        return {
            "id": self.id,
            "taskId": self.task_id,
            "projectId": self.project_id,
            "taskCode": self.task_code,
            "taskName": self.task_name,
            "description": self.description,
            "taskType": self.task_type,
            "assignee": self.assignee,
            "status": self.status,
            "priority": self.priority,
            "progress": self.progress,
            "startTime": self.start_time,
            "endTime": self.end_time,
            "createTime": self.create_time,
            "updateTime": self.update_time,
        }


class AgentBug(Base):
    """BUG模型"""
    __tablename__ = "agent_bug"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    bug_id: Mapped[str] = mapped_column(String(64), unique=True)
    project_id: Mapped[int] = mapped_column(BigInteger, index=True)
    task_id: Mapped[Optional[str]] = mapped_column(String(64))
    session_id: Mapped[Optional[str]] = mapped_column(String(64))
    bug_code: Mapped[Optional[str]] = mapped_column(String(64))
    bug_title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16), default="minor")
    priority: Mapped[str] = mapped_column(String(16), default="P2")
    status: Mapped[str] = mapped_column(String(32), default="open")
    reporter: Mapped[Optional[str]] = mapped_column(String(32))
    assignee: Mapped[Optional[str]] = mapped_column(String(32))
    environment: Mapped[Optional[str]] = mapped_column(String(255))
    reproduce_steps: Mapped[Optional[str]] = mapped_column(Text)
    expected_result: Mapped[Optional[str]] = mapped_column(Text)
    actual_result: Mapped[Optional[str]] = mapped_column(Text)
    attachments: Mapped[Optional[str]] = mapped_column(Text)
    fix_note: Mapped[Optional[str]] = mapped_column(Text)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)

    def to_dict(self):
        return {
            "id": self.id,
            "bugId": self.bug_id,
            "projectId": self.project_id,
            "bugCode": self.bug_code,
            "bugTitle": self.bug_title,
            "title": self.bug_title,
            "description": self.description,
            "severity": self.severity,
            "priority": self.priority,
            "status": self.status,
            "reporter": self.reporter,
            "assignee": self.assignee,
            "stepsToReproduce": self.reproduce_steps,
            "expectedBehavior": self.expected_result,
            "actualBehavior": self.actual_result,
            "resolution": self.fix_note,
            "createTime": self.create_time,
            "updateTime": self.update_time,
        }


class AgentMemory(Base):
    """记忆模型"""
    __tablename__ = "agent_memory"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    memory_id: Mapped[str] = mapped_column(String(64), unique=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(64))
    project_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    agent_type: Mapped[str] = mapped_column(String(32), index=True)
    memory_type: Mapped[str] = mapped_column(String(32))
    key_info: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    importance: Mapped[int] = mapped_column(Integer, default=50)
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    last_access_time: Mapped[Optional[int]] = mapped_column(BigInteger)
    expire_time: Mapped[Optional[int]] = mapped_column(BigInteger)
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)


class AgentKnowledge(Base):
    """知识库模型"""
    __tablename__ = "agent_knowledge"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    knowledge_id: Mapped[str] = mapped_column(String(64), unique=True)
    project_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(String(64))
    tags: Mapped[Optional[str]] = mapped_column(String(255))
    source: Mapped[Optional[str]] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer, default=1)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding_status: Mapped[str] = mapped_column(String(32), default="pending")
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)


class KnowledgeEdge(Base):
    """知识图谱边 - 表示知识条目之间的关系"""
    __tablename__ = "knowledge_edge"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    edge_id: Mapped[str] = mapped_column(String(64), unique=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)  # source knowledge_id
    target_id: Mapped[str] = mapped_column(String(64), index=True)  # target knowledge_id
    relation_type: Mapped[str] = mapped_column(String(64))  # depends_on, related_to, derived_from, supersedes, references
    weight: Mapped[float] = mapped_column(Numeric(3, 2), default=1.0)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)


class DevPipeline(Base):
    """开发流水线模型"""
    __tablename__ = "dev_pipeline"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    pipeline_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(64))
    user_request: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    current_stage: Mapped[str] = mapped_column(String(32), default="requirement")
    stages_data: Mapped[Optional[str]] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    creator_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    workspace_path: Mapped[Optional[str]] = mapped_column(String(512))
    git_repo_url: Mapped[Optional[str]] = mapped_column(String(512))
    git_branch: Mapped[Optional[str]] = mapped_column(String(64))
    git_commit_sha: Mapped[Optional[str]] = mapped_column(String(64))
    deploy_task_id: Mapped[Optional[str]] = mapped_column(String(64))
    git_config_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    skill_config: Mapped[Optional[str]] = mapped_column(Text)
    create_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    update_time: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time() * 1000))
    is_deleted: Mapped[int] = mapped_column(Integer, default=0)
