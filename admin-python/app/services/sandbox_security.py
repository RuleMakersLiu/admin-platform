"""沙箱安全：生成的代码（LLM 产出，不可信）在 admin-python 内以子进程执行时，
剔除敏感环境变量，防止生成代码 getenv 越权获取 admin 凭据
（DATABASE_URL / JWT_SECRET / *_API_KEY 等）。

适用于 backend_runner（mvn 构建 / java -jar）与 sandbox_preview（git clone / npm install /
vite dev）触发的所有子进程。这是「进程级 env 隔离」——更彻底的隔离（独立容器 / 独立网络 /
非 root 降权）见长期方案，本模块只兜底最直接的凭据泄露面。
"""
from __future__ import annotations

import os

# 敏感关键词（大小写不敏感，key 含任一即剔除）——生成的子进程绝不应继承 admin 凭据。
# 用「包含」而非「前缀」，避免 CLAUDE_API_KEY / X_API_KEY 这类前缀不在列表里的漏网。
SENSITIVE_ENV_KEYWORDS = (
    "DATABASE_URL", "JWT", "REDIS", "API_KEY", "SECRET", "PASSWORD", "TOKEN",
    "_KEY", "POSTGRES", "MYSQL", "PG_", "ZAI", "OPENAI", "ANTHROPIC", "CLAUDE",
    "GOOGLE", "DEEPSEEK", "GEMINI", "CREDENTIAL", "PRIVATE",
)


def sanitized_env(base: dict | None = None) -> dict:
    """返回剔除敏感 key 后的环境变量副本，供生成的子进程使用。

    用「关键词包含」匹配（大小写不敏感），覆盖各种 *_API_KEY / *_SECRET / 提供商前缀。
    backend_runner 另在白名单里单独注入指向 mysql-sandbox 的沙箱凭据。
    宁严勿松：误剔某个非敏感 env，好过泄露凭据给不可信的生成代码。
    """
    src = base if base is not None else os.environ
    return {
        k: v for k, v in src.items()
        if not any(kw in k.upper() for kw in SENSITIVE_ENV_KEYWORDS)
    }
