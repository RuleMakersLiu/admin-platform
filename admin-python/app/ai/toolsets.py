"""Toolset system for composable skill grouping.

Groups skills by scenario (development, testing, analysis, etc.)
with support for composition and resolution.
"""

TOOLSETS = {
    "analysis": {
        "description": "Requirements analysis and planning skills",
        "skills": ["requirement_analysis", "task_breakdown"],
        "includes": [],
    },
    "development": {
        "description": "Code generation and UI development skills",
        "skills": ["backend_development", "frontend_development", "ui_preview"],
        "includes": [],
    },
    "testing": {
        "description": "Code review and test generation skills",
        "skills": ["code_review", "test_generation"],
        "includes": [],
    },
    "report": {
        "description": "Progress reports and summaries",
        "skills": ["progress_report"],
        "includes": [],
    },
    "knowledge": {
        "description": "Knowledge base and AI upgrade skills",
        "skills": ["knowledge_search", "ai_upgrade_check"],
        "includes": [],
    },
    "full_pipeline": {
        "description": "Complete development pipeline - all skills",
        "skills": [],
        "includes": ["analysis", "development", "testing", "report"],
    },
    "devops": {
        "description": "Development and deployment workflow",
        "skills": [],
        "includes": ["development", "testing"],
    },
}


def resolve_toolset(name: str, visited: set = None) -> list[str]:
    """Recursively resolve a toolset to get all skill IDs."""
    if visited is None:
        visited = set()
    if name in {"all", "*"}:
        all_skills = set()
        for ts_name in TOOLSETS:
            all_skills.update(resolve_toolset(ts_name, visited.copy()))
        return sorted(all_skills)
    if name in visited:
        return []
    visited.add(name)

    toolset = TOOLSETS.get(name)
    if not toolset:
        return []

    skills = set(toolset.get("skills", []))
    for included in toolset.get("includes", []):
        skills.update(resolve_toolset(included, visited))
    return sorted(skills)


def get_all_toolsets() -> dict:
    """Return all toolsets with resolved skill lists."""
    result = {}
    for name, ts in TOOLSETS.items():
        resolved = resolve_toolset(name)
        result[name] = {
            "name": name,
            "description": ts["description"],
            "skills": resolved,
            "skill_count": len(resolved),
        }
    return result


def get_toolset_info(name: str) -> dict | None:
    """Get detailed info about a specific toolset."""
    if name not in TOOLSETS:
        return None
    ts = TOOLSETS[name]
    resolved = resolve_toolset(name)
    return {
        "name": name,
        "description": ts["description"],
        "direct_skills": ts.get("skills", []),
        "includes": ts.get("includes", []),
        "resolved_skills": resolved,
        "skill_count": len(resolved),
    }
