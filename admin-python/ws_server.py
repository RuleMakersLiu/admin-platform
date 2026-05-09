"""
WebSocket服务 - 智能体协作实时通信

功能：
1. 房间管理 - 按项目/会话分组
2. 心跳检测 - 自动断开无响应连接
3. 消息广播 - 实时推送任务/状态变更
"""
import asyncio
import json
import time
import uuid
from typing import Dict, Set, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ws_server")


class MessageType(str, Enum):
    """WebSocket消息类型"""
    # 连接相关
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    HEARTBEAT = "heartbeat"
    HEARTBEAT_ACK = "heartbeat_ack"
    
    # 房间管理
    JOIN_ROOM = "join_room"
    LEAVE_ROOM = "leave_room"
    ROOM_USERS = "room_users"
    
    # 任务相关
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    TASK_MOVED = "task_moved"
    TASK_DELETED = "task_deleted"
    TASK_ASSIGNED = "task_assigned"
    
    # 智能体相关
    AGENT_STATUS = "agent_status"
    AGENT_PROGRESS = "agent_progress"
    AGENT_MESSAGE = "agent_message"
    AGENT_HANDOFF = "agent_handoff"
    
    # 协作相关
    COLLABORATION_REQUEST = "collaboration_request"
    COLLABORATION_RESPONSE = "collaboration_response"
    REVIEW_REQUEST = "review_request"
    REVIEW_RESULT = "review_result"
    
    # 系统相关
    SYSTEM_NOTICE = "system_notice"
    ERROR = "error"


@dataclass
class WebSocketClient:
    """WebSocket客户端"""
    websocket: WebSocket
    client_id: str
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    agent_id: Optional[str] = None
    agent_type: Optional[str] = None
    rooms: Set[str] = field(default_factory=set)
    last_heartbeat: float = field(default_factory=time.time)
    is_agent: bool = False


class RoomManager:
    """房间管理器"""
    
    def __init__(self):
        # room_id -> set of client_ids
        self._rooms: Dict[str, Set[str]] = {}
        # client_id -> room_id (记录客户端所在的主房间)
        self._client_main_room: Dict[str, str] = {}
    
    def join_room(self, client_id: str, room_id: str, is_main: bool = False) -> int:
        """加入房间，返回房间内人数"""
        if room_id not in self._rooms:
            self._rooms[room_id] = set()
        
        self._rooms[room_id].add(client_id)
        
        if is_main:
            self._client_main_room[client_id] = room_id
        
        return len(self._rooms[room_id])
    
    def leave_room(self, client_id: str, room_id: str) -> int:
        """离开房间，返回房间内剩余人数"""
        if room_id in self._rooms:
            self._rooms[room_id].discard(client_id)
            if not self._rooms[room_id]:
                del self._rooms[room_id]
                return 0
            return len(self._rooms[room_id])
        return 0
    
    def leave_all_rooms(self, client_id: str) -> Set[str]:
        """离开所有房间，返回离开的房间ID集合"""
        left_rooms = set()
        for room_id in list(self._rooms.keys()):
            if client_id in self._rooms[room_id]:
                self._rooms[room_id].discard(client_id)
                if not self._rooms[room_id]:
                    del self._rooms[room_id]
                left_rooms.add(room_id)
        
        if client_id in self._client_main_room:
            del self._client_main_room[client_id]
        
        return left_rooms
    
    def get_room_clients(self, room_id: str) -> Set[str]:
        """获取房间内所有客户端"""
        return self._rooms.get(room_id, set()).copy()
    
    def get_client_rooms(self, client_id: str) -> Set[str]:
        """获取客户端所在的所有房间"""
        rooms = set()
        for room_id, clients in self._rooms.items():
            if client_id in clients:
                rooms.add(room_id)
        return rooms
    
    def get_room_count(self, room_id: str) -> int:
        """获取房间人数"""
        return len(self._rooms.get(room_id, set()))


class ConnectionManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        # client_id -> WebSocketClient
        self._clients: Dict[str, WebSocketClient] = {}
        # 房间管理器
        self._room_manager = RoomManager()
        # 心跳检测配置
        self._heartbeat_interval = 30  # 秒
        self._heartbeat_timeout = 90   # 秒
        # 消息队列（用于广播）
        self._message_queue: asyncio.Queue = asyncio.Queue()
    
    @property
    def room_manager(self) -> RoomManager:
        return self._room_manager
    
    async def connect(self, websocket: WebSocket) -> str:
        """接受新连接，返回client_id"""
        await websocket.accept()
        client_id = f"client_{uuid.uuid4().hex[:12]}"
        
        client = WebSocketClient(
            websocket=websocket,
            client_id=client_id,
        )
        self._clients[client_id] = client
        
        logger.info(f"Client connected: {client_id}")
        return client_id
    
    async def disconnect(self, client_id: str):
        """断开连接"""
        if client_id not in self._clients:
            return
        
        client = self._clients[client_id]
        
        # 离开所有房间
        left_rooms = self._room_manager.leave_all_rooms(client_id)
        
        # 通知其他客户端
        for room_id in left_rooms:
            await self._broadcast_to_room(room_id, {
                "type": MessageType.DISCONNECT.value,
                "data": {
                    "clientId": client_id,
                    "userId": client.user_id,
                    "agentId": client.agent_id,
                }
            }, exclude_client=client_id)
        
        # 删除客户端
        del self._clients[client_id]
        
        logger.info(f"Client disconnected: {client_id}")
    
    def get_client(self, client_id: str) -> Optional[WebSocketClient]:
        """获取客户端"""
        return self._clients.get(client_id)
    
    def register_client(
        self,
        client_id: str,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        agent_type: Optional[str] = None,
        is_agent: bool = False,
    ):
        """注册客户端信息"""
        if client_id not in self._clients:
            return
        
        client = self._clients[client_id]
        client.user_id = user_id
        client.tenant_id = tenant_id
        client.agent_id = agent_id
        client.agent_type = agent_type
        client.is_agent = is_agent
    
    async def join_room(
        self,
        client_id: str,
        room_id: str,
        is_main: bool = False,
    ) -> dict:
        """加入房间"""
        if client_id not in self._clients:
            return {"error": "Client not found"}
        
        client = self._clients[client_id]
        client_count = self._room_manager.join_room(client_id, room_id, is_main)
        client.rooms.add(room_id)
        
        # 通知房间内其他人
        await self._broadcast_to_room(room_id, {
            "type": MessageType.JOIN_ROOM.value,
            "data": {
                "clientId": client_id,
                "userId": client.user_id,
                "agentId": client.agent_id,
                "agentType": client.agent_type,
                "isAgent": client.is_agent,
            }
        }, exclude_client=client_id)
        
        return {
            "roomId": room_id,
            "userCount": client_count,
            "users": self._get_room_users(room_id),
        }
    
    async def leave_room(self, client_id: str, room_id: str) -> dict:
        """离开房间"""
        if client_id not in self._clients:
            return {"error": "Client not found"}
        
        client = self._clients[client_id]
        client_count = self._room_manager.leave_room(client_id, room_id)
        client.rooms.discard(room_id)
        
        # 通知房间内其他人
        await self._broadcast_to_room(room_id, {
            "type": MessageType.LEAVE_ROOM.value,
            "data": {
                "clientId": client_id,
                "userId": client.user_id,
            }
        }, exclude_client=client_id)
        
        return {
            "roomId": room_id,
            "userCount": client_count,
        }
    
    def _get_room_users(self, room_id: str) -> list:
        """获取房间用户列表"""
        client_ids = self._room_manager.get_room_clients(room_id)
        users = []
        for cid in client_ids:
            client = self._clients.get(cid)
            if client:
                users.append({
                    "clientId": cid,
                    "userId": client.user_id,
                    "agentId": client.agent_id,
                    "agentType": client.agent_type,
                    "isAgent": client.is_agent,
                })
        return users
    
    async def send_to_client(self, client_id: str, message: dict):
        """发送消息给指定客户端"""
        if client_id not in self._clients:
            return
        
        client = self._clients[client_id]
        try:
            await client.websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending to {client_id}: {e}")
    
    async def _broadcast_to_room(
        self,
        room_id: str,
        message: dict,
        exclude_client: Optional[str] = None,
    ):
        """广播消息到房间"""
        client_ids = self._room_manager.get_room_clients(room_id)
        
        for client_id in client_ids:
            if client_id == exclude_client:
                continue
            await self.send_to_client(client_id, message)
    
    async def broadcast_to_project(
        self,
        project_id: str,
        message: dict,
        exclude_client: Optional[str] = None,
    ):
        """广播到项目房间"""
        room_id = f"project:{project_id}"
        await self._broadcast_to_room(room_id, message, exclude_client)
    
    async def broadcast_to_session(
        self,
        session_id: str,
        message: dict,
        exclude_client: Optional[str] = None,
    ):
        """广播到会话房间"""
        room_id = f"session:{session_id}"
        await self._broadcast_to_room(room_id, message, exclude_client)
    
    async def broadcast_to_all(self, message: dict):
        """广播给所有客户端"""
        for client_id in self._clients:
            await self.send_to_client(client_id, message)
    
    def update_heartbeat(self, client_id: str):
        """更新心跳时间"""
        if client_id in self._clients:
            self._clients[client_id].last_heartbeat = time.time()
    
    async def check_heartbeats(self):
        """检查心跳，断开超时连接"""
        current_time = time.time()
        timeout_clients = []
        
        for client_id, client in self._clients.items():
            if current_time - client.last_heartbeat > self._heartbeat_timeout:
                timeout_clients.append(client_id)
        
        for client_id in timeout_clients:
            logger.warning(f"Client {client_id} heartbeat timeout, disconnecting")
            client = self._clients.get(client_id)
            if client:
                try:
                    await client.websocket.close(code=1001, reason="Heartbeat timeout")
                except:
                    pass
            await self.disconnect(client_id)
    
    def get_stats(self) -> dict:
        """获取连接统计"""
        user_count = sum(1 for c in self._clients.values() if not c.is_agent)
        agent_count = sum(1 for c in self._clients.values() if c.is_agent)
        
        return {
            "totalConnections": len(self._clients),
            "userConnections": user_count,
            "agentConnections": agent_count,
            "totalRooms": len(self._room_manager._rooms),
        }


# 全局连接管理器
manager = ConnectionManager()


async def handle_message(client_id: str, data: dict):
    """处理客户端消息"""
    message_type = data.get("type")
    payload = data.get("data", {})
    
    if message_type == MessageType.HEARTBEAT.value:
        # 心跳响应
        manager.update_heartbeat(client_id)
        await manager.send_to_client(client_id, {
            "type": MessageType.HEARTBEAT_ACK.value,
            "data": {"timestamp": int(time.time() * 1000)}
        })
    
    elif message_type == MessageType.CONNECT.value:
        # 连接注册
        manager.register_client(
            client_id,
            user_id=payload.get("userId"),
            tenant_id=payload.get("tenantId"),
            agent_id=payload.get("agentId"),
            agent_type=payload.get("agentType"),
            is_agent=payload.get("isAgent", False),
        )
        
        # 如果指定了项目，自动加入项目房间
        project_id = payload.get("projectId")
        if project_id:
            await manager.join_room(client_id, f"project:{project_id}", is_main=True)
        
        # 如果指定了会话，自动加入会话房间
        session_id = payload.get("sessionId")
        if session_id:
            await manager.join_room(client_id, f"session:{session_id}")
        
        await manager.send_to_client(client_id, {
            "type": MessageType.CONNECT.value,
            "data": {
                "clientId": client_id,
                "status": "connected",
            }
        })
    
    elif message_type == MessageType.JOIN_ROOM.value:
        result = await manager.join_room(client_id, payload.get("roomId"))
        await manager.send_to_client(client_id, {
            "type": MessageType.ROOM_USERS.value,
            "data": result,
        })
    
    elif message_type == MessageType.LEAVE_ROOM.value:
        result = await manager.leave_room(client_id, payload.get("roomId"))
        await manager.send_to_client(client_id, {
            "type": MessageType.LEAVE_ROOM.value,
            "data": result,
        })
    
    elif message_type == MessageType.TASK_CREATED.value:
        # 广播任务创建
        project_id = payload.get("projectId")
        if project_id:
            await manager.broadcast_to_project(str(project_id), {
                "type": MessageType.TASK_CREATED.value,
                "data": payload,
            }, exclude_client=client_id)
    
    elif message_type == MessageType.TASK_UPDATED.value:
        # 广播任务更新
        project_id = payload.get("projectId")
        if project_id:
            await manager.broadcast_to_project(str(project_id), {
                "type": MessageType.TASK_UPDATED.value,
                "data": payload,
            }, exclude_client=client_id)
    
    elif message_type == MessageType.TASK_MOVED.value:
        # 广播任务移动
        project_id = payload.get("projectId")
        if project_id:
            await manager.broadcast_to_project(str(project_id), {
                "type": MessageType.TASK_MOVED.value,
                "data": payload,
            }, exclude_client=client_id)
    
    elif message_type == MessageType.AGENT_STATUS.value:
        # 广播智能体状态
        project_id = payload.get("projectId")
        if project_id:
            await manager.broadcast_to_project(str(project_id), {
                "type": MessageType.AGENT_STATUS.value,
                "data": payload,
            })
    
    elif message_type == MessageType.AGENT_PROGRESS.value:
        # 广播智能体进度
        session_id = payload.get("sessionId")
        if session_id:
            await manager.broadcast_to_session(session_id, {
                "type": MessageType.AGENT_PROGRESS.value,
                "data": payload,
            })
    
    elif message_type == MessageType.AGENT_MESSAGE.value:
        # 智能体消息
        session_id = payload.get("sessionId")
        if session_id:
            await manager.broadcast_to_session(session_id, {
                "type": MessageType.AGENT_MESSAGE.value,
                "data": payload,
            })
    
    elif message_type == MessageType.AGENT_HANDOFF.value:
        # 智能体交接
        session_id = payload.get("sessionId")
        if session_id:
            await manager.broadcast_to_session(session_id, {
                "type": MessageType.AGENT_HANDOFF.value,
                "data": payload,
            })
    
    elif message_type == MessageType.COLLABORATION_REQUEST.value:
        # 协作请求
        target_agent_id = payload.get("targetAgentId")
        if target_agent_id:
            # 发送给目标智能体
            for cid, client in manager._clients.items():
                if client.agent_id == target_agent_id:
                    await manager.send_to_client(cid, {
                        "type": MessageType.COLLABORATION_REQUEST.value,
                        "data": payload,
                    })
                    break
    
    elif message_type == MessageType.COLLABORATION_RESPONSE.value:
        # 协作响应
        target_agent_id = payload.get("targetAgentId")
        if target_agent_id:
            for cid, client in manager._clients.items():
                if client.agent_id == target_agent_id:
                    await manager.send_to_client(cid, {
                        "type": MessageType.COLLABORATION_RESPONSE.value,
                        "data": payload,
                    })
                    break
    
    else:
        # 未知消息类型
        await manager.send_to_client(client_id, {
            "type": MessageType.ERROR.value,
            "data": {"message": f"Unknown message type: {message_type}"}
        })


async def heartbeat_checker():
    """心跳检查协程"""
    while True:
        await asyncio.sleep(30)  # 每30秒检查一次
        await manager.check_heartbeats()


# ==================== FastAPI 应用 ====================

app = FastAPI(
    title="WebSocket Server",
    description="智能体协作实时通信服务",
    version="1.0.0",
)

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """健康检查"""
    return {
        "status": "ok",
        "service": "ws_server",
        **manager.get_stats(),
    }


@app.get("/stats")
async def stats():
    """获取连接统计"""
    return manager.get_stats()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket连接端点"""
    client_id = await manager.connect(websocket)
    
    try:
        # 发送连接确认
        await manager.send_to_client(client_id, {
            "type": MessageType.CONNECT.value,
            "data": {
                "clientId": client_id,
                "status": "connected",
                "message": "Please register with CONNECT message",
            }
        })
        
        # 消息循环
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=120.0  # 2分钟超时
                )
                await handle_message(client_id, data)
            except asyncio.TimeoutError:
                # 超时，检查心跳
                await manager.send_to_client(client_id, {
                    "type": MessageType.HEARTBEAT.value,
                    "data": {"message": "Please send heartbeat"}
                })
            except json.JSONDecodeError:
                await manager.send_to_client(client_id, {
                    "type": MessageType.ERROR.value,
                    "data": {"message": "Invalid JSON"}
                })
    
    except WebSocketDisconnect:
        logger.info(f"Client {client_id} disconnected")
    except Exception as e:
        logger.error(f"Error in websocket connection {client_id}: {e}")
    finally:
        await manager.disconnect(client_id)


@app.on_event("startup")
async def startup_event():
    """启动事件"""
    # 启动心跳检查协程
    asyncio.create_task(heartbeat_checker())
    logger.info("🚀 WebSocket Server started")


@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件"""
    logger.info("👋 WebSocket Server shutting down")


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "ws_server:app",
        host="0.0.0.0",
        port=8765,
        reload=True,
        log_level="info",
    )
