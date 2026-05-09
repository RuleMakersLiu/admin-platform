"""AI Agent Skills 系统

将 Agent 能力封装为标准化的 Skill，支持:
- 自动注册与发现
- 输入/输出 Schema 定义
- Skill 组合（编排多个 Skill）
- 错误处理与重试
"""
import asyncio
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


class SkillStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SkillDefinition:
    """Skill 定义"""
    skill_id: str
    name: str
    description: str
    category: str  # analysis, development, testing, deployment, knowledge, report
    agent_type: str  # PM, PJM, BE, FE, QA, RPT, SYSTEM
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    examples: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    instructions: str = ""


@dataclass
class SkillResult:
    """Skill 执行结果"""
    skill_id: str
    execution_id: str
    status: SkillStatus
    output: Optional[Any] = None
    error: Optional[str] = None
    execution_time_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"
USER_SKILLS_DIR = Path.home() / ".admin-platform" / "skills"


class SkillLoader:
    """Discovers and loads SKILL.md files from disk.

    Follows the Hermes Agent / agentskills.io standard:
    each skill lives in a directory containing a SKILL.md file
    with YAML frontmatter and markdown body.
    """

    @staticmethod
    def parse_skill_md(skill_md_path: Path) -> Optional[SkillDefinition]:
        """Parse a SKILL.md file into a SkillDefinition.

        The file must start with YAML frontmatter delimited by '---'.
        The body after the closing '---' becomes the instructions field.
        """
        try:
            content = skill_md_path.read_text(encoding="utf-8")
        except (OSError, IOError) as e:
            logger.warning(f"Cannot read skill file {skill_md_path}: {e}")
            return None

        if not content.startswith("---"):
            return None

        end = content.find("\n---", 3)
        if end == -1:
            return None

        try:
            frontmatter = yaml.safe_load(content[3:end])
        except yaml.YAMLError:
            return None

        if not isinstance(frontmatter, dict):
            return None

        body = content[end + 4:].strip()

        return SkillDefinition(
            skill_id=frontmatter.get("id", skill_md_path.parent.name),
            name=frontmatter.get("name", skill_md_path.parent.name),
            description=frontmatter.get("description", ""),
            category=frontmatter.get("category", "general"),
            agent_type=frontmatter.get("agent_type", "SYSTEM"),
            version=frontmatter.get("version", "1.0.0"),
            input_schema=frontmatter.get("input_schema", {}),
            output_schema=frontmatter.get("output_schema", {}),
            instructions=body,
        )

    @staticmethod
    def discover_skills(directories: Optional[List[Path]] = None) -> List[SkillDefinition]:
        """Scan directories for SKILL.md files.

        If no directories are provided, defaults to the built-in skills
        directory and the user skills directory (~/.admin-platform/skills/).
        Duplicate skill names are skipped (first occurrence wins).
        """
        if directories is None:
            directories = [SKILLS_DIR]
            if USER_SKILLS_DIR.exists():
                directories.append(USER_SKILLS_DIR)

        skills: List[SkillDefinition] = []
        seen: set = set()
        for dir_path in directories:
            if not dir_path.exists():
                continue
            for skill_md in dir_path.rglob("SKILL.md"):
                name = skill_md.parent.name
                if name in seen:
                    continue
                skill = SkillLoader.parse_skill_md(skill_md)
                if skill:
                    skills.append(skill)
                    seen.add(name)
        return skills


class SkillRegistry:
    """Skill 注册中心 - 全局单例"""

    def __init__(self):
        self._skills: Dict[str, SkillDefinition] = {}
        self._handlers: Dict[str, Callable] = {}

    def register(
        self,
        skill_id: str,
        name: str,
        description: str,
        category: str,
        agent_type: str,
        input_schema: Optional[Dict] = None,
        output_schema: Optional[Dict] = None,
        examples: Optional[List[str]] = None,
        version: str = "1.0.0",
    ):
        """注册一个 Skill（装饰器模式）"""
        def decorator(func: Callable):
            self._skills[skill_id] = SkillDefinition(
                skill_id=skill_id,
                name=name,
                description=description,
                category=category,
                agent_type=agent_type,
                input_schema=input_schema or {},
                output_schema=output_schema or {},
                examples=examples or [],
                version=version,
            )
            self._handlers[skill_id] = func
            logger.info(f"Registered skill: {skill_id} ({name})")
            return func
        return decorator

    def get_skill(self, skill_id: str) -> Optional[SkillDefinition]:
        return self._skills.get(skill_id)

    def list_skills(
        self,
        category: Optional[str] = None,
        agent_type: Optional[str] = None,
    ) -> List[SkillDefinition]:
        skills = list(self._skills.values())
        if category:
            skills = [s for s in skills if s.category == category]
        if agent_type:
            skills = [s for s in skills if s.agent_type == agent_type]
        return skills

    async def execute(self, skill_id: str, timeout_seconds: int = 120, **kwargs) -> SkillResult:
        """执行一个 Skill，支持超时控制"""
        execution_id = f"SKEX-{uuid.uuid4().hex[:12].upper()}"

        if skill_id not in self._handlers:
            return SkillResult(
                skill_id=skill_id,
                execution_id=execution_id,
                status=SkillStatus.FAILED,
                error=f"Skill not found: {skill_id}",
            )

        handler = self._handlers[skill_id]
        start = time.time()
        try:
            result = handler(**kwargs)
            if asyncio.iscoroutine(result):
                result = await asyncio.wait_for(result, timeout=timeout_seconds)

            return SkillResult(
                skill_id=skill_id,
                execution_id=execution_id,
                status=SkillStatus.COMPLETED,
                output=result,
                execution_time_ms=int((time.time() - start) * 1000),
            )
        except asyncio.TimeoutError:
            logger.error(f"Skill execution timed out: {skill_id} ({timeout_seconds}s)")
            return SkillResult(
                skill_id=skill_id,
                execution_id=execution_id,
                status=SkillStatus.FAILED,
                error=f"Execution timed out after {timeout_seconds}s",
                execution_time_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            logger.error(f"Skill execution failed: {skill_id} - {e}")
            return SkillResult(
                skill_id=skill_id,
                execution_id=execution_id,
                status=SkillStatus.FAILED,
                error=str(e),
                execution_time_ms=int((time.time() - start) * 1000),
            )

    async def execute_stream(self, skill_id: str, **kwargs):
        """流式执行 Skill，yield 中间结果"""
        if skill_id not in self._handlers:
            yield SkillResult(
                skill_id=skill_id,
                execution_id=f"SKEX-{uuid.uuid4().hex[:12].upper()}",
                status=SkillStatus.FAILED,
                error=f"Skill not found: {skill_id}",
            )
            return

        handler = self._handlers[skill_id]
        start = time.time()
        execution_id = f"SKEX-{uuid.uuid4().hex[:12].upper()}"

        try:
            result = handler(**kwargs)
            if asyncio.iscoroutine(result):
                # 如果 handler 是 async generator，逐个 yield
                if hasattr(result, '__aiter__'):
                    async for chunk in result:
                        yield SkillResult(
                            skill_id=skill_id,
                            execution_id=execution_id,
                            status=SkillStatus.RUNNING,
                            output=chunk,
                            execution_time_ms=int((time.time() - start) * 1000),
                        )
                else:
                    result = await result

            yield SkillResult(
                skill_id=skill_id,
                execution_id=execution_id,
                status=SkillStatus.COMPLETED,
                output=result,
                execution_time_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            yield SkillResult(
                skill_id=skill_id,
                execution_id=execution_id,
                status=SkillStatus.FAILED,
                error=str(e),
                execution_time_ms=int((time.time() - start) * 1000),
            )

    def load_from_disk(self, directories: Optional[List[Path]] = None) -> int:
        """Load skills from SKILL.md files on disk.

        If a skill with the same ID already exists (e.g. registered via
        decorator), its ``instructions`` field is enriched with the
        markdown body from the SKILL.md file.  Otherwise the full
        SkillDefinition is added as a new entry.
        Returns the count of skills processed from disk.
        """
        count = 0
        for skill_def in SkillLoader.discover_skills(directories):
            existing = self._skills.get(skill_def.skill_id)
            if existing is not None:
                # Enrich the decorator-registered skill with instructions
                if skill_def.instructions and not existing.instructions:
                    existing.instructions = skill_def.instructions
                    logger.info(
                        f"Enriched skill with instructions from disk: {skill_def.skill_id}"
                    )
            else:
                self._skills[skill_def.skill_id] = skill_def
                logger.info(f"Loaded skill from disk: {skill_def.skill_id}")
            count += 1
        return count

    def view_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Return full skill details including instructions."""
        skill = self._skills.get(skill_id)
        if not skill:
            return None
        return {
            "skill_id": skill.skill_id,
            "name": skill.name,
            "description": skill.description,
            "category": skill.category,
            "agent_type": skill.agent_type,
            "input_schema": skill.input_schema,
            "output_schema": skill.output_schema,
            "examples": skill.examples,
            "version": skill.version,
            "instructions": skill.instructions,
        }


# Global registry
skill_registry = SkillRegistry()


# ==================== 注册内置 Skills ====================

# --- PM Skills ---
@skill_registry.register(
    skill_id="requirement_analysis",
    name="需求分析",
    description="分析用户需求，生成结构化需求文档",
    category="analysis",
    agent_type="PM",
    input_schema={"user_request": {"type": "string", "description": "用户需求描述"}},
    output_schema={"requirement_doc": {"type": "object", "description": "需求文档"}},
    examples=["分析用户登录功能需求", "生成电商购物车模块PRD"],
)
async def requirement_analysis(user_request: str, **kwargs) -> Dict[str, Any]:
    from app.ai.agents import AgentService, AgentType
    agent = AgentService()
    result = await agent.chat(
        agent_type=AgentType.PM,
        message=f"请分析以下需求并生成结构化需求文档:\n\n{user_request}",
        session_id=kwargs.get("session_id", ""),
    )
    return {"requirement_doc": result}


@skill_registry.register(
    skill_id="task_breakdown",
    name="任务分解",
    description="将需求分解为具体的开发任务",
    category="analysis",
    agent_type="PJM",
    input_schema={"requirement_doc": {"type": "object", "description": "需求文档"}},
    output_schema={"tasks": {"type": "array", "description": "任务列表"}},
)
async def task_breakdown(requirement_doc: str, **kwargs) -> Dict[str, Any]:
    from app.ai.agents import AgentService, AgentType
    agent = AgentService()
    result = await agent.chat(
        agent_type=AgentType.PJM,
        message=f"请将以下需求分解为开发任务:\n\n{requirement_doc}",
        session_id=kwargs.get("session_id", ""),
    )
    return {"tasks": result}


# --- BE Skills ---
@skill_registry.register(
    skill_id="backend_development",
    name="后端开发",
    description="根据需求生成后端代码（API、数据库、业务逻辑）",
    category="development",
    agent_type="BE",
    input_schema={"requirement": {"type": "string"}, "api_contract": {"type": "string"}},
    output_schema={"code": {"type": "object", "description": "生成的代码文件"}},
)
async def backend_development(requirement: str, **kwargs) -> Dict[str, Any]:
    from app.ai.agents import AgentService, AgentType
    agent = AgentService()
    result = await agent.chat(
        agent_type=AgentType.BE,
        message=f"请根据以下需求生成后端代码:\n\n{requirement}",
        session_id=kwargs.get("session_id", ""),
    )
    return {"code": result}


# --- FE Skills ---
@skill_registry.register(
    skill_id="frontend_development",
    name="前端开发",
    description="根据需求生成前端页面代码",
    category="development",
    agent_type="FE",
    input_schema={"requirement": {"type": "string"}, "ui_spec": {"type": "string"}},
    output_schema={"code": {"type": "object", "description": "生成的前端代码"}},
)
async def frontend_development(requirement: str, **kwargs) -> Dict[str, Any]:
    from app.ai.agents import AgentService, AgentType
    agent = AgentService()
    result = await agent.chat(
        agent_type=AgentType.FE,
        message=f"请根据以下需求生成前端代码:\n\n{requirement}",
        session_id=kwargs.get("session_id", ""),
    )
    return {"code": result}


@skill_registry.register(
    skill_id="ui_preview",
    name="UI预览生成",
    description="根据需求描述生成UI预览HTML",
    category="development",
    agent_type="FE",
    input_schema={"requirement": {"type": "string"}},
    output_schema={"html": {"type": "string", "description": "UI预览HTML"}},
)
async def ui_preview(requirement: str, **kwargs) -> Dict[str, Any]:
    from app.ai.agents import AgentService, AgentType
    agent = AgentService()
    result = await agent.chat(
        agent_type=AgentType.FE,
        message=f"请根据以下需求生成UI预览HTML（使用Vue 2 + antd-vue 1.x风格，包含CDN引用，可直接浏览器打开）:\n\n{requirement}",
        session_id=kwargs.get("session_id", ""),
    )
    return {"html": result}


# --- QA Skills ---
@skill_registry.register(
    skill_id="code_review",
    name="代码审查",
    description="审查代码质量、安全性和最佳实践",
    category="testing",
    agent_type="QA",
    input_schema={"code": {"type": "string"}, "requirement": {"type": "string"}},
    output_schema={"review_result": {"type": "object", "description": "审查结果"}},
)
async def code_review(code: str, requirement: str = "", **kwargs) -> Dict[str, Any]:
    from app.ai.agents import AgentService, AgentType
    agent = AgentService()
    result = await agent.chat(
        agent_type=AgentType.QA,
        message=f"请审查以下代码:\n\n```\n{code}\n```\n\n需求: {requirement}",
        session_id=kwargs.get("session_id", ""),
    )
    return {"review_result": result}


@skill_registry.register(
    skill_id="test_generation",
    name="测试用例生成",
    description="根据需求生成测试用例",
    category="testing",
    agent_type="QA",
    input_schema={"requirement": {"type": "string"}, "code": {"type": "string"}},
    output_schema={"test_cases": {"type": "array", "description": "测试用例"}},
)
async def test_generation(requirement: str, code: str = "", **kwargs) -> Dict[str, Any]:
    from app.ai.agents import AgentService, AgentType
    agent = AgentService()
    result = await agent.chat(
        agent_type=AgentType.QA,
        message=f"请根据以下需求生成测试用例:\n\n{requirement}\n\n代码:\n{code}",
        session_id=kwargs.get("session_id", ""),
    )
    return {"test_cases": result}


# --- RPT Skills ---
@skill_registry.register(
    skill_id="progress_report",
    name="进度报告",
    description="生成项目进度总结报告",
    category="report",
    agent_type="RPT",
    input_schema={"project_data": {"type": "object"}},
    output_schema={"report": {"type": "object"}},
)
async def progress_report(project_data: str, **kwargs) -> Dict[str, Any]:
    from app.ai.agents import AgentService, AgentType
    agent = AgentService()
    result = await agent.chat(
        agent_type=AgentType.RPT,
        message=f"请根据以下项目数据生成进度报告:\n\n{project_data}",
        session_id=kwargs.get("session_id", ""),
    )
    return {"report": result}


# --- System Skills ---
@skill_registry.register(
    skill_id="knowledge_search",
    name="知识库搜索",
    description="搜索本地知识库获取相关信息",
    category="knowledge",
    agent_type="SYSTEM",
    input_schema={"query": {"type": "string"}, "category": {"type": "string"}},
    output_schema={"results": {"type": "array"}},
)
async def knowledge_search(query: str, category: str = None, **kwargs) -> Dict[str, Any]:
    from app.services.knowledge_service import knowledge_service
    results = await knowledge_service.search_knowledge(
        query=query, category=category, limit=5,
    )
    return {"results": results}


@skill_registry.register(
    skill_id="ai_upgrade_check",
    name="AI技术升级检查",
    description="检查最新的AI技术趋势并进行系统升级分析",
    category="knowledge",
    agent_type="SYSTEM",
    input_schema={},
    output_schema={"upgrade_report": {"type": "object"}},
)
async def ai_upgrade_check(**kwargs) -> Dict[str, Any]:
    from app.services.ai_upgrade_service import ai_upgrade_service
    result = await ai_upgrade_service.run_daily_upgrade()
    return {"upgrade_report": result}


# Load skills from SKILL.md files on disk (after decorator registrations)
skill_registry.load_from_disk()


# ==================== Skill Manager (Self-Improvement) ====================

class SkillManager:
    """Allows agents to create, edit, and delete skills from experience.

    This is the self-improvement loop: after complex tasks succeed,
    agents can save their approach as a reusable skill.
    """

    SKILLS_BASE_DIR = SKILLS_DIR
    USER_SKILLS_DIR = USER_SKILLS_DIR

    MAX_NAME_LENGTH = 64
    MAX_DESCRIPTION_LENGTH = 1024
    MAX_CONTENT_CHARS = 100_000
    VALID_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9._-]*$')

    @staticmethod
    def _validate_name(name: str) -> Optional[str]:
        if not name:
            return "Skill name is required."
        if len(name) > 64:
            return f"Skill name exceeds 64 characters."
        if not re.match(r'^[a-z0-9][a-z0-9._-]*$', name):
            return f"Invalid skill name '{name}'. Use lowercase, hyphens, dots, underscores."
        return None

    @staticmethod
    def _validate_frontmatter(content: str) -> Optional[str]:
        if not content.strip():
            return "Content cannot be empty."
        if not content.startswith("---"):
            return "SKILL.md must start with YAML frontmatter (---)."
        end = content.find("\n---", 3)
        if end == -1:
            return "SKILL.md frontmatter is not closed. Add closing '---'."
        try:
            parsed = yaml.safe_load(content[3:end])
        except yaml.YAMLError as e:
            return f"YAML parse error: {e}"
        if not isinstance(parsed, dict):
            return "Frontmatter must be YAML mapping."
        if "name" not in parsed:
            return "Frontmatter must include 'name'."
        if "description" not in parsed:
            return "Frontmatter must include 'description'."
        body = content[end + 4:].strip()
        if not body:
            return "SKILL.md must have content after frontmatter."
        return None

    @staticmethod
    def _find_skill_dir(name: str) -> Optional[Path]:
        for base_dir in [SKILLS_DIR, USER_SKILLS_DIR]:
            if not base_dir.exists():
                continue
            for skill_md in base_dir.rglob("SKILL.md"):
                if skill_md.parent.name == name:
                    return skill_md.parent
        return None

    @staticmethod
    def create_skill(name: str, content: str, category: str = None) -> Dict[str, Any]:
        """Create a new skill from SKILL.md content."""
        err = SkillManager._validate_name(name)
        if err:
            return {"success": False, "error": err}
        err = SkillManager._validate_frontmatter(content)
        if err:
            return {"success": False, "error": err}
        if len(content) > SkillManager.MAX_CONTENT_CHARS:
            return {"success": False, "error": f"Content exceeds {SkillManager.MAX_CONTENT_CHARS} chars."}

        if SkillManager._find_skill_dir(name):
            return {"success": False, "error": f"Skill '{name}' already exists."}

        if category:
            skill_dir = USER_SKILLS_DIR / category / name
        else:
            skill_dir = USER_SKILLS_DIR / name
        skill_dir.mkdir(parents=True, exist_ok=True)

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(content, encoding="utf-8")

        # Reload into registry
        loaded = SkillLoader.parse_skill_md(skill_md)
        if loaded:
            skill_registry._skills[loaded.skill_id] = loaded

        return {
            "success": True,
            "message": f"Skill '{name}' created.",
            "path": str(skill_dir),
        }

    @staticmethod
    def edit_skill(name: str, content: str) -> Dict[str, Any]:
        """Replace the full SKILL.md of an existing skill."""
        err = SkillManager._validate_frontmatter(content)
        if err:
            return {"success": False, "error": err}

        skill_dir = SkillManager._find_skill_dir(name)
        if not skill_dir:
            return {"success": False, "error": f"Skill '{name}' not found."}

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(content, encoding="utf-8")

        loaded = SkillLoader.parse_skill_md(skill_md)
        if loaded:
            skill_registry._skills[loaded.skill_id] = loaded

        return {"success": True, "message": f"Skill '{name}' updated."}

    @staticmethod
    def patch_skill(name: str, old_string: str, new_string: str) -> Dict[str, Any]:
        """Targeted find-and-replace in a skill's SKILL.md."""
        skill_dir = SkillManager._find_skill_dir(name)
        if not skill_dir:
            return {"success": False, "error": f"Skill '{name}' not found."}

        skill_md = skill_dir / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")

        count = content.count(old_string)
        if count == 0:
            return {"success": False, "error": "old_string not found.", "preview": content[:500]}
        if count > 1:
            return {"success": False, "error": f"Found {count} matches. Be more specific."}

        new_content = content.replace(old_string, new_string, 1)
        err = SkillManager._validate_frontmatter(new_content)
        if err:
            return {"success": False, "error": f"Patch would break structure: {err}"}

        skill_md.write_text(new_content, encoding="utf-8")

        loaded = SkillLoader.parse_skill_md(skill_md)
        if loaded:
            skill_registry._skills[loaded.skill_id] = loaded

        return {"success": True, "message": f"Patched skill '{name}'."}

    @staticmethod
    def delete_skill(name: str) -> Dict[str, Any]:
        """Delete a skill."""
        skill_dir = SkillManager._find_skill_dir(name)
        if not skill_dir:
            return {"success": False, "error": f"Skill '{name}' not found."}

        import shutil
        shutil.rmtree(skill_dir)

        if name in skill_registry._skills:
            del skill_registry._skills[name]

        return {"success": True, "message": f"Skill '{name}' deleted."}


skill_manager = SkillManager()
