"""激活体验API测试"""
import asyncio
import json
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock

from app.main import app
from app.services.activation_service import activation_service


@pytest.fixture
def mock_glm_response():
    """模拟GLM响应"""
    class MockMessage:
        content = "这是测试响应内容，用于验证激活流程。"
    return MockMessage()


@pytest.mark.asyncio
async def test_warmup():
    """测试预热接口"""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.post("/api/v1/activation/warmup")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200


@pytest.mark.asyncio
async def test_start_activation():
    """测试开始激活流程"""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/activation/start",
            json={
                "userId": 123,
                "tenantId": 1,
                "userName": "测试用户"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "activationId" in data["data"]
        assert "welcomeMessage" in data["data"]
        assert len(data["data"]["suggestedPrompts"]) > 0


@pytest.mark.asyncio
async def test_get_templates():
    """测试获取模板"""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/activation/templates")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert len(data["data"]["templates"]) > 0
        assert len(data["data"]["categories"]) > 0


@pytest.mark.asyncio
async def test_activation_chat_non_stream():
    """测试激活对话（非流式）"""
    # 先创建激活会话
    session = await activation_service.start_activation(
        user_id=123,
        tenant_id=1,
        user_name="测试用户"
    )
    
    with patch.object(
        activation_service.client, 
        'ainvoke', 
        new_callable=AsyncMock
    ) as mock_invoke:
        # 模拟AI响应
        class MockMessage:
            content = "这是测试响应"
        mock_invoke.return_value = MockMessage()
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            timeout=30.0
        ) as client:
            response = await client.post(
                "/api/v1/activation/chat",
                json={
                    "activationId": session.activation_id,
                    "message": "你好",
                    "useStream": False
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "reply" in data["data"]


@pytest.mark.asyncio
async def test_activation_chat_stream():
    """测试激活对话（SSE流式）"""
    # 先创建激活会话
    session = await activation_service.start_activation(
        user_id=123,
        tenant_id=1,
        user_name="测试用户"
    )
    
    with patch.object(
        activation_service.client, 
        'astream'
    ) as mock_stream:
        # 模拟流式响应
        async def mock_generator():
            chunks = ["你", "好", "！"]
            for chunk in chunks:
                yield f'data: {json.dumps({"type": "chunk", "content": chunk, "done": False})}\n\n'
            yield f'data: {json.dumps({"type": "done", "done": True})}\n\n'
        
        mock_stream.return_value = mock_generator()
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            timeout=30.0
        ) as client:
            response = await client.post(
                "/api/v1/activation/chat",
                json={
                    "activationId": session.activation_id,
                    "message": "你好",
                    "useStream": True
                }
            )
            
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            
            # 验证响应内容
            content = response.text
            assert "data:" in content
            assert "chunk" in content


@pytest.mark.asyncio
async def test_complete_activation():
    """测试完成激活"""
    # 先创建激活会话
    session = await activation_service.start_activation(
        user_id=123,
        tenant_id=1,
        user_name="测试用户"
    )
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/activation/complete",
            json={
                "activationId": session.activation_id,
                "rating": 5,
                "feedback": "体验很好！"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["status"] == "completed"
        assert len(data["data"]["nextSteps"]) > 0


@pytest.mark.asyncio
async def test_get_activation_status():
    """测试获取激活状态"""
    # 先创建激活会话
    session = await activation_service.start_activation(
        user_id=123,
        tenant_id=1,
        user_name="测试用户"
    )
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get(
            f"/api/v1/activation/status/{session.activation_id}"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["status"] == "ready"
        assert data["data"]["messageCount"] == 0


@pytest.mark.asyncio
async def test_invalid_activation_id():
    """测试无效的激活ID"""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        # 测试对话
        response = await client.post(
            "/api/v1/activation/chat",
            json={
                "activationId": "invalid_id",
                "message": "你好",
                "useStream": False
            }
        )
        assert response.status_code == 404
        
        # 测试完成
        response = await client.post(
            "/api/v1/activation/complete",
            json={
                "activationId": "invalid_id",
                "rating": 5
            }
        )
        assert response.status_code == 200
        assert response.json()["code"] == 500
        
        # 测试状态
        response = await client.get("/api/v1/activation/status/invalid_id")
        assert response.status_code == 404


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])
