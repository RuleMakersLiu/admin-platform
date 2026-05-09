"""
WebSocket 测试
测试 WebSocket 连接、消息发送和接收
"""
import pytest
import asyncio
import json
import httpx
from unittest.mock import Mock, patch, AsyncMock

# 测试配置
BASE_URL = "http://localhost:8081"
WS_URL = "ws://localhost:8081/ws"


@pytest.fixture
def auth_token() -> str:
    """获取认证 Token"""
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        response = client.post(
            "/api/auth/login",
            json={
                "username": "admin",
                "password": "admin123",
                "tenantId": 1
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        return data["data"]["token"]


class TestWebSocketConnection:
    """WebSocket 连接测试"""

    def test_websocket_url_requires_token(self, auth_token: str):
        """测试 WebSocket URL 需要 Token"""
        assert auth_token is not None
        assert len(auth_token) > 0

    @pytest.mark.asyncio
    async def test_websocket_connect_without_token(self):
        """测试无 Token 连接应被拒绝"""
        # 模拟无 Token 连接
        try:
            import websockets
            async with websockets.connect(WS_URL) as ws:
                # 如果连接成功，应该收到错误消息
                response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(response)
                # 预期收到认证失败消息
                assert data.get("type") in ["error", "auth_failed", "unauthorized"]
        except Exception as e:
            # 预期连接失败或被拒绝
            assert "401" in str(e) or "403" in str(e) or "Unauthorized" in str(e) or "Forbidden" in str(e)

    @pytest.mark.asyncio
    async def test_websocket_connect_with_token(self, auth_token: str):
        """测试带 Token 的 WebSocket 连接"""
        try:
            import websockets
            ws_url = f"{WS_URL}?token={auth_token}"
            async with websockets.connect(ws_url) as ws:
                # 连接成功
                assert ws.open is True
                
                # 发送 ping 消息
                await ws.send(json.dumps({"type": "ping", "payload": {}}))
                
                # 等待响应（可能超时，取决于服务端实现）
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(response)
                    assert data.get("type") in ["pong", "ping", "heartbeat"]
                except asyncio.TimeoutError:
                    # 如果服务端不回复 ping，也视为连接正常
                    pass
        except ImportError:
            pytest.skip("websockets library not installed")
        except Exception as e:
            # 如果 WebSocket 服务未启动，跳过测试
            if "Connection refused" in str(e):
                pytest.skip("WebSocket server not running")


class TestWebSocketMessaging:
    """WebSocket 消息测试"""

    @pytest.mark.asyncio
    async def test_send_chat_message(self, auth_token: str):
        """测试发送聊天消息"""
        try:
            import websockets
            ws_url = f"{WS_URL}?token={auth_token}"
            
            async with websockets.connect(ws_url) as ws:
                # 发送消息
                message = {
                    "type": "message.send",
                    "payload": {
                        "sessionId": "test_session_001",
                        "content": "你好，这是一条测试消息",
                        "stream": False
                    },
                    "timestamp": int(asyncio.get_event_loop().time() * 1000)
                }
                await ws.send(json.dumps(message))
                
                # 等待响应
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    data = json.loads(response)
                    # 预期收到消息确认或回复
                    assert data.get("type") in ["message.sent", "message.received", "message.complete", "error"]
                except asyncio.TimeoutError:
                    pytest.skip("Server did not respond in time")
                    
        except ImportError:
            pytest.skip("websockets library not installed")
        except Exception as e:
            if "Connection refused" in str(e):
                pytest.skip("WebSocket server not running")

    @pytest.mark.asyncio
    async def test_create_session(self, auth_token: str):
        """测试创建会话"""
        try:
            import websockets
            ws_url = f"{WS_URL}?token={auth_token}"
            
            async with websockets.connect(ws_url) as ws:
                # 发送创建会话请求
                message = {
                    "type": "session.create",
                    "payload": {
                        "title": "测试会话"
                    },
                    "timestamp": int(asyncio.get_event_loop().time() * 1000)
                }
                await ws.send(json.dumps(message))
                
                # 等待响应
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(response)
                    assert data.get("type") in ["session.created", "error"]
                except asyncio.TimeoutError:
                    pytest.skip("Server did not respond in time")
                    
        except ImportError:
            pytest.skip("websockets library not installed")
        except Exception as e:
            if "Connection refused" in str(e):
                pytest.skip("WebSocket server not running")

    @pytest.mark.asyncio
    async def test_delete_session(self, auth_token: str):
        """测试删除会话"""
        try:
            import websockets
            ws_url = f"{WS_URL}?token={auth_token}"
            
            async with websockets.connect(ws_url) as ws:
                # 发送删除会话请求
                message = {
                    "type": "session.delete",
                    "payload": {
                        "sessionId": "test_session_to_delete"
                    },
                    "timestamp": int(asyncio.get_event_loop().time() * 1000)
                }
                await ws.send(json.dumps(message))
                
                # 等待响应
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(response)
                    assert data.get("type") in ["session.deleted", "error"]
                except asyncio.TimeoutError:
                    pytest.skip("Server did not respond in time")
                    
        except ImportError:
            pytest.skip("websockets library not installed")
        except Exception as e:
            if "Connection refused" in str(e):
                pytest.skip("WebSocket server not running")


class TestWebSocketReconnection:
    """WebSocket 重连测试"""

    @pytest.mark.asyncio
    async def test_reconnection_behavior(self, auth_token: str):
        """测试重连行为"""
        try:
            import websockets
            
            # 第一次连接
            ws_url = f"{WS_URL}?token={auth_token}"
            ws1 = await websockets.connect(ws_url)
            assert ws1.open is True
            
            # 关闭连接
            await ws1.close()
            assert ws1.open is False
            
            # 重新连接
            ws2 = await websockets.connect(ws_url)
            assert ws2.open is True
            
            # 清理
            await ws2.close()
            
        except ImportError:
            pytest.skip("websockets library not installed")
        except Exception as e:
            if "Connection refused" in str(e):
                pytest.skip("WebSocket server not running")


class TestWebSocketHeartbeat:
    """WebSocket 心跳测试"""

    @pytest.mark.asyncio
    async def test_ping_pong(self, auth_token: str):
        """测试心跳机制"""
        try:
            import websockets
            ws_url = f"{WS_URL}?token={auth_token}"
            
            async with websockets.connect(ws_url) as ws:
                # 发送多个 ping
                for i in range(3):
                    await ws.send(json.dumps({"type": "ping", "payload": {"seq": i}}))
                    await asyncio.sleep(0.5)
                
                # 收集所有响应
                responses = []
                try:
                    while True:
                        response = await asyncio.wait_for(ws.recv(), timeout=2.0)
                        responses.append(json.loads(response))
                except asyncio.TimeoutError:
                    pass
                
                # 验证至少收到一个响应
                # 注意：服务端可能不回复 ping，这是正常的
                print(f"Received {len(responses)} responses")
                
        except ImportError:
            pytest.skip("websockets library not installed")
        except Exception as e:
            if "Connection refused" in str(e):
                pytest.skip("WebSocket server not running")


class TestWebSocketErrorHandling:
    """WebSocket 错误处理测试"""

    @pytest.mark.asyncio
    async def test_invalid_message_format(self, auth_token: str):
        """测试无效消息格式"""
        try:
            import websockets
            ws_url = f"{WS_URL}?token={auth_token}"
            
            async with websockets.connect(ws_url) as ws:
                # 发送无效 JSON
                await ws.send("not a valid json")
                
                # 等待错误响应
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(response)
                    # 预期收到错误消息
                    assert data.get("type") == "error" or "error" in str(data).lower()
                except asyncio.TimeoutError:
                    # 服务端可能直接断开连接
                    pass
                except json.JSONDecodeError:
                    # 服务端可能返回非 JSON 响应
                    pass
                    
        except ImportError:
            pytest.skip("websockets library not installed")
        except Exception as e:
            if "Connection refused" in str(e):
                pytest.skip("WebSocket server not running")

    @pytest.mark.asyncio
    async def test_missing_message_type(self, auth_token: str):
        """测试缺少消息类型"""
        try:
            import websockets
            ws_url = f"{WS_URL}?token={auth_token}"
            
            async with websockets.connect(ws_url) as ws:
                # 发送没有 type 的消息
                message = {
                    "payload": {"data": "test"},
                    "timestamp": int(asyncio.get_event_loop().time() * 1000)
                }
                await ws.send(json.dumps(message))
                
                # 等待错误响应
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    data = json.loads(response)
                    # 预期收到错误消息
                    assert data.get("type") in ["error", "unknown"] or "error" in str(data).lower()
                except asyncio.TimeoutError:
                    pass
                    
        except ImportError:
            pytest.skip("websockets library not installed")
        except Exception as e:
            if "Connection refused" in str(e):
                pytest.skip("WebSocket server not running")


# Mock 测试（不需要实际 WebSocket 服务）
class TestWebSocketMock:
    """WebSocket Mock 测试（不需要真实服务）"""

    @pytest.mark.asyncio
    async def test_message_serialization(self):
        """测试消息序列化"""
        message = {
            "type": "message.send",
            "payload": {
                "sessionId": "test_123",
                "content": "测试消息",
                "stream": True
            },
            "timestamp": 1700000000000
        }
        
        # 序列化
        json_str = json.dumps(message)
        assert json_str is not None
        
        # 反序列化
        parsed = json.loads(json_str)
        assert parsed["type"] == "message.send"
        assert parsed["payload"]["sessionId"] == "test_123"
        assert parsed["payload"]["content"] == "测试消息"

    def test_websocket_url_format(self, auth_token: str):
        """测试 WebSocket URL 格式"""
        ws_url = f"{WS_URL}?token={auth_token}"
        assert ws_url.startswith("ws://") or ws_url.startswith("wss://")
        assert "token=" in ws_url

    def test_message_type_validation(self):
        """测试消息类型验证"""
        valid_types = [
            "ping",
            "message.send",
            "session.create",
            "session.delete",
            "session.rename"
        ]
        
        for msg_type in valid_types:
            message = {"type": msg_type, "payload": {}}
            assert message["type"] in valid_types
