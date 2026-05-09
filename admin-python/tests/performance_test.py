#!/usr/bin/env python3
"""激活体验性能测试脚本"""
import asyncio
import json
import time
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx


class ActivationPerformanceTest:
    """激活体验性能测试"""
    
    def __init__(self, base_url: str = "http://localhost:8081"):
        self.base_url = base_url
        self.results = []
    
    async def test_warmup_time(self):
        """测试预热时间"""
        print("\n📊 测试预热时间...")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            start = time.time()
            response = await client.post(f"{self.base_url}/api/v1/activation/warmup")
            elapsed = time.time() - start
            
            if response.status_code == 200:
                print(f"✅ 预热完成: {elapsed:.2f}秒")
                return elapsed
            else:
                print(f"❌ 预热失败: {response.status_code}")
                return None
    
    async def test_start_activation_time(self):
        """测试启动激活时间"""
        print("\n📊 测试启动激活时间...")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            start = time.time()
            response = await client.post(
                f"{self.base_url}/api/v1/activation/start",
                json={
                    "userId": 1,
                    "tenantId": 1,
                    "userName": "性能测试用户"
                }
            )
            elapsed = time.time() - start
            
            if response.status_code == 200:
                data = response.json()["data"]
                print(f"✅ 启动完成: {elapsed:.2f}秒")
                print(f"   Activation ID: {data['activationId']}")
                return data["activationId"]
            else:
                print(f"❌ 启动失败: {response.status_code}")
                return None
    
    async def test_first_response_time(self, activation_id: str):
        """测试首字响应时间（TTFB）"""
        print("\n📊 测试首字响应时间 (TTFB)...")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            start = time.time()
            first_chunk_time = None
            full_response = ""
            
            async with client.stream(
                "POST",
                f"{self.base_url}/api/v1/activation/chat",
                json={
                    "activationId": activation_id,
                    "message": "你好，介绍一下这个系统",
                    "useStream": True
                }
            ) as response:
                if response.status_code != 200:
                    print(f"❌ 对话失败: {response.status_code}")
                    return None, None
                
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    
                    if first_chunk_time is None:
                        first_chunk_time = time.time() - start
                    
                    try:
                        data = json.loads(line[6:])
                        if data.get("type") == "chunk":
                            full_response += data.get("content", "")
                        elif data.get("type") == "done":
                            total_time = time.time() - start
                            break
                    except:
                        continue
            
            ttfb = first_chunk_time if first_chunk_time else 0
            total_time = time.time() - start
            
            print(f"✅ 首字延迟 (TTFB): {ttfb:.2f}秒")
            print(f"   总耗时: {total_time:.2f}秒")
            print(f"   响应长度: {len(full_response)}字符")
            
            # 性能评估
            if ttfb < 2.0:
                print(f"   🎯 性能优秀 (<2秒)")
            elif ttfb < 3.0:
                print(f"   ⚠️ 性能良好 (2-3秒)")
            else:
                print(f"   ❌ 性能需要优化 (>3秒)")
            
            return ttfb, total_time
    
    async def test_template_loading_time(self):
        """测试模板加载时间"""
        print("\n📊 测试模板加载时间...")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            start = time.time()
            response = await client.get(f"{self.base_url}/api/v1/activation/templates")
            elapsed = time.time() - start
            
            if response.status_code == 200:
                data = response.json()["data"]
                print(f"✅ 模板加载完成: {elapsed:.2f}秒")
                print(f"   模板数量: {len(data['templates'])}")
                print(f"   分类数量: {len(data['categories'])}")
                return elapsed
            else:
                print(f"❌ 模板加载失败: {response.status_code}")
                return None
    
    async def test_complete_activation_time(self, activation_id: str):
        """测试完成激活时间"""
        print("\n📊 测试完成激活时间...")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            start = time.time()
            response = await client.post(
                f"{self.base_url}/api/v1/activation/complete",
                json={
                    "activationId": activation_id,
                    "rating": 5,
                    "feedback": "性能测试反馈"
                }
            )
            elapsed = time.time() - start
            
            if response.status_code == 200:
                data = response.json()["data"]
                print(f"✅ 完成激活: {elapsed:.2f}秒")
                print(f"   状态: {data['status']}")
                return elapsed
            else:
                print(f"❌ 完成失败: {response.status_code}")
                return None
    
    async def run_full_test(self):
        """运行完整性能测试"""
        print("=" * 60)
        print("🚀 激活体验性能测试")
        print("=" * 60)
        
        results = {}
        
        # 1. 预热测试
        results["warmup"] = await self.test_warmup_time()
        
        # 2. 启动激活测试
        activation_id = await self.test_start_activation_time()
        if not activation_id:
            print("\n❌ 无法继续测试，启动激活失败")
            return
        
        # 3. 首字延迟测试（核心指标）
        ttfb, total_time = await self.test_first_response_time(activation_id)
        results["ttfb"] = ttfb
        results["total_chat_time"] = total_time
        
        # 4. 模板加载测试
        results["templates"] = await self.test_template_loading_time()
        
        # 5. 完成激活测试
        results["complete"] = await self.test_complete_activation_time(activation_id)
        
        # 输出总结
        print("\n" + "=" * 60)
        print("📊 性能测试总结")
        print("=" * 60)
        
        if results.get("ttfb"):
            print(f"🎯 核心指标 - 首字延迟 (TTFB): {results['ttfb']:.2f}秒")
            if results['ttfb'] < 2.0:
                print("   ✅ 达到目标 (<2秒)")
            else:
                print("   ⚠️ 未达到目标，需要优化")
        
        print(f"\n⏱️ 其他指标:")
        if results.get("warmup"):
            print(f"   - 预热时间: {results['warmup']:.2f}秒")
        if results.get("templates"):
            print(f"   - 模板加载: {results['templates']:.2f}秒")
        if results.get("total_chat_time"):
            print(f"   - 完整对话: {results['total_chat_time']:.2f}秒")
        if results.get("complete"):
            print(f"   - 完成激活: {results['complete']:.2f}秒")
        
        print("=" * 60)


async def main():
    """主函数"""
    test = ActivationPerformanceTest()
    
    try:
        await test.run_full_test()
    except httpx.ConnectError:
        print("\n❌ 无法连接到服务器")
        print("请确保服务已启动: uvicorn app.main:app --reload")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
