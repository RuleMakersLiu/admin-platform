#!/usr/bin/env python3
"""
激活体验快速演示脚本

使用方法:
1. 启动服务: uvicorn app.main:app --reload --port 8081
2. 运行演示: python activation_demo.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import httpx


async def demo():
    """演示激活体验完整流程"""
    base_url = "http://localhost:8081"
    
    print("=" * 70)
    print("🎬 激活体验演示")
    print("=" * 70)
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1. 预热（模拟登录后调用）
        print("\n[1/6] 🔥 预热AI连接...")
        try:
            response = await client.post(f"{base_url}/api/v1/activation/warmup")
            print(f"     ✅ 预热完成: {response.json()['message']}")
        except Exception as e:
            print(f"     ⚠️ 预热失败: {e}")
        
        # 2. 开始激活
        print("\n[2/6] 🚀 开始激活流程...")
        response = await client.post(
            f"{base_url}/api/v1/activation/start",
            json={
                "userId": 1,
                "tenantId": 1,
                "userName": "演示用户"
            }
        )
        data = response.json()["data"]
        activation_id = data["activationId"]
        print(f"     ✅ 激活ID: {activation_id}")
        print(f"\n{data['welcomeMessage']}")
        
        # 3. 获取模板
        print("\n[3/6] 📋 获取演示模板...")
        response = await client.get(f"{base_url}/api/v1/activation/templates")
        templates = response.json()["data"]["templates"]
        print(f"     ✅ 找到 {len(templates)} 个模板:")
        for i, t in enumerate(templates[:3], 1):
            print(f"        {i}. {t['icon']} {t['title']}: {t['description']}")
        
        # 4. 流式对话
        print("\n[4/6] 💬 开始AI对话（流式响应）...")
        print("     用户: 你好，介绍一下这个系统")
        print("     AI: ", end="", flush=True)
        
        async with client.stream(
            "POST",
            f"{base_url}/api/v1/activation/chat",
            json={
                "activationId": activation_id,
                "message": "你好，介绍一下这个系统",
                "useStream": True
            }
        ) as response:
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                
                try:
                    data = json.loads(line[6:])
                    if data.get("type") == "chunk":
                        print(data["content"], end="", flush=True)
                    elif data.get("type") == "done":
                        print(f"\n\n     ⏱️ 响应耗时: {data.get('elapsed', 0):.2f}秒")
                        break
                except:
                    continue
        
        # 5. 查看状态
        print("\n[5/6] 📊 查看激活状态...")
        response = await client.get(f"{base_url}/api/v1/activation/status/{activation_id}")
        status = response.json()["data"]
        print(f"     状态: {status['status']}")
        print(f"     消息数: {status['messageCount']}")
        
        # 6. 完成激活
        print("\n[6/6] ✅ 完成激活...")
        response = await client.post(
            f"{base_url}/api/v1/activation/complete",
            json={
                "activationId": activation_id,
                "rating": 5,
                "feedback": "体验很好！"
            }
        )
        result = response.json()["data"]
        print(f"     状态: {result['status']}")
        print(f"     消息: {result['message']}")
        print("     后续步骤:")
        for step in result["nextSteps"]:
            print(f"       - {step}")
    
    print("\n" + "=" * 70)
    print("🎉 演示完成！")
    print("=" * 70)


if __name__ == "__main__":
    try:
        asyncio.run(demo())
    except httpx.ConnectError:
        print("\n❌ 无法连接到服务器")
        print("请先启动服务: uvicorn app.main:app --reload --port 8081")
    except KeyboardInterrupt:
        print("\n\n⚠️ 演示已中断")
    except Exception as e:
        print(f"\n❌ 演示失败: {e}")
        import traceback
        traceback.print_exc()
