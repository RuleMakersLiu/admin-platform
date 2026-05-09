#!/usr/bin/env python3
"""手动触发 AI 升级分析（可通过 crontab 调用）

crontab:
  5 2 * * * cd /home/pastorlol/admin-platform/admin-python && python -m scripts.run_ai_upgrade
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    from app.services.ai_upgrade_service import ai_upgrade_service
    result = await ai_upgrade_service.run_daily_upgrade()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    import json
    asyncio.run(main())
