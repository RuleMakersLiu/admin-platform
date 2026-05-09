<?php

declare(strict_types=1);

namespace App\Services;

use Swoole\WebSocket\Server;
use Swoole\Table;
use Swoole\Timer;
use Illuminate\Support\Facades\Redis;
use Illuminate\Support\Facades\Log;

/**
 * AI协作看板 - WebSocket服务
 * 
 * 功能:
 * 1. 房间管理 - 支持多个房间订阅
 * 2. 广播机制 - 智能体状态、任务状态实时推送
 * 3. 心跳检测 - 30秒间隔,90秒超时
 * 4. 连接管理 - 用户认证、连接追踪
 */
class WebSocketService
{
    private Server $server;
    private Table $connectionTable;  // 连接信息表
    private Table $roomTable;        // 房间成员表
    private array $config;

    /**
     * 初始化WebSocket服务
     */
    public function __construct(array $config = [])
    {
        $this->config = array_merge([
            'host' => env('WS_HOST', '0.0.0.0'),
            'port' => env('WS_PORT', 9501),
            'heartbeat_interval' => 30000,    // 30秒
            'heartbeat_timeout' => 90000,     // 90秒
            'max_connections' => 1000,
        ], $config);

        $this->initTables();
        $this->initServer();
    }

    /**
     * 初始化Swoole内存表
     */
    private function initTables(): void
    {
        // 连接信息表
        $this->connectionTable = new Table($this->config['max_connections']);
        $this->connectionTable->column('fd', Table::TYPE_INT);
        $this->connectionTable->column('user_id', Table::TYPE_STRING, 36);
        $this->connectionTable->column('rooms', Table::TYPE_STRING, 1024);
        $this->connectionTable->column('last_ping', Table::TYPE_INT);
        $this->connectionTable->column('ip', Table::TYPE_STRING, 45);
        $this->connectionTable->create();

        // 房间成员表 (room => [fd1, fd2, ...])
        $this->roomTable = new Table(100);
        $this->roomTable->column('members', Table::TYPE_STRING, 8192);
        $this->roomTable->create();
    }

    /**
     * 初始化Swoole WebSocket服务器
     */
    private function initServer(): void
    {
        $this->server = new Server(
            $this->config['host'],
            $this->config['port'],
            SWOOLE_PROCESS,
            SWOOLE_SOCK_TCP | SWOOLE_SSL
        );

        $this->server->set([
            'worker_num' => env('WS_WORKER_NUM', 4),
            'task_worker_num' => env('WS_TASK_WORKER_NUM', 2),
            'max_conn' => $this->config['max_connections'],
            'heartbeat_check_interval' => 30,
            'heartbeat_idle_time' => 90,
            'ssl_cert_file' => env('SSL_CERT_FILE'),
            'ssl_key_file' => env('SSL_KEY_FILE'),
            'enable_coroutine' => true,
        ]);

        $this->registerEventHandlers();
    }

    /**
     * 注册事件处理器
     */
    private function registerEventHandlers(): void
    {
        // 连接建立
        $this->server->on('open', [$this, 'onOpen']);

        // 接收消息
        $this->server->on('message', [$this, 'onMessage']);

        // 连接关闭
        $this->server->on('close', [$this, 'onClose']);

        // 任务处理 (用于异步广播)
        $this->server->on('task', [$this, 'onTask']);
        $this->server->on('finish', [$this, 'onFinish']);

        // Worker启动
        $this->server->on('workerStart', [$this, 'onWorkerStart']);
    }

    /**
     * 连接建立事件
     */
    public function onOpen(Server $server, $request): void
    {
        $fd = $request->fd;
        $token = $request->get['token'] ?? '';

        // 验证Token
        $user = $this->authenticateToken($token);
        if (!$user) {
            $server->push($fd, json_encode([
                'type' => 'error',
                'message' => 'Authentication failed'
            ]));
            $server->close($fd);
            return;
        }

        // 记录连接信息
        $this->connectionTable->set($fd, [
            'fd' => $fd,
            'user_id' => $user['id'],
            'rooms' => json_encode([]),
            'last_ping' => time(),
            'ip' => $request->server['remote_addr'] ?? '',
        ]);

        // 存储到Redis (用于跨Worker通信)
        Redis::hset('ws:connections', $fd, json_encode([
            'user_id' => $user['id'],
            'connected_at' => time(),
        ]));

        $server->push($fd, json_encode([
            'type' => 'connected',
            'message' => 'WebSocket connection established',
            'fd' => $fd,
        ]));

        Log::info("WebSocket connection opened", ['fd' => $fd, 'user' => $user['id']]);
    }

    /**
     * 接收消息事件
     */
    public function onMessage(Server $server, $frame): void
    {
        $fd = $frame->fd;
        $data = json_decode($frame->data, true);

        if (!$data || !isset($data['type'])) {
            $server->push($fd, json_encode([
                'type' => 'error',
                'message' => 'Invalid message format'
            ]));
            return;
        }

        // 更新心跳时间
        $this->connectionTable->set($fd, [
            'last_ping' => time(),
        ]);

        // 路由消息处理
        switch ($data['type']) {
            case 'ping':
                $this->handlePing($server, $fd);
                break;

            case 'subscribe':
                $this->handleSubscribe($server, $fd, $data['room'] ?? '');
                break;

            case 'unsubscribe':
                $this->handleUnsubscribe($server, $fd, $data['room'] ?? '');
                break;

            case 'task_action':
                $this->handleTaskAction($server, $fd, $data);
                break;

            default:
                $server->push($fd, json_encode([
                    'type' => 'error',
                    'message' => 'Unknown message type'
                ]));
        }
    }

    /**
     * 连接关闭事件
     */
    public function onClose(Server $server, $fd): void
    {
        // 获取用户订阅的房间
        $connection = $this->connectionTable->get($fd);
        if ($connection) {
            $rooms = json_decode($connection['rooms'], true);
            foreach ($rooms as $room) {
                $this->leaveRoom($room, $fd);
            }
        }

        // 清理连接表
        $this->connectionTable->del($fd);
        Redis::hdel('ws:connections', $fd);

        Log::info("WebSocket connection closed", ['fd' => $fd]);
    }

    /**
     * Worker启动事件
     */
    public function onWorkerStart(Server $server, int $workerId): void
    {
        // 启动定时器 - 定期推送看板更新
        if ($workerId === 0) {
            Timer::tick(5000, function () {
                $this->broadcastDashboardUpdate();
            });
        }

        // 启动定时器 - 监听Redis消息
        if ($workerId === 1) {
            $this->subscribeToRedisChannels();
        }
    }

    /**
     * 任务处理 (异步广播)
     */
    public function onTask(Server $server, int $taskId, int $workerId, $data): string
    {
        $type = $data['type'] ?? '';
        $payload = $data['data'] ?? [];

        switch ($type) {
            case 'broadcast_room':
                $this->broadcastToRoom($payload['room'], $payload['message']);
                break;

            case 'broadcast_all':
                $this->broadcastToAll($payload['message']);
                break;

            case 'agent_status_update':
                $this->handleAgentStatusUpdate($payload);
                break;

            case 'task_status_update':
                $this->handleTaskStatusUpdate($payload);
                break;
        }

        return 'Task completed';
    }

    /**
     * 任务完成回调
     */
    public function onFinish(Server $server, int $taskId, string $data): void
    {
        // 可用于日志记录等
    }

    /**
     * 处理心跳
     */
    private function handlePing(Server $server, int $fd): void
    {
        $server->push($fd, json_encode([
            'type' => 'pong',
            'timestamp' => time(),
        ]));
    }

    /**
     * 处理房间订阅
     */
    private function handleSubscribe(Server $server, int $fd, string $room): void
    {
        if (empty($room)) {
            $server->push($fd, json_encode([
                'type' => 'error',
                'message' => 'Room name is required'
            ]));
            return;
        }

        // 加入房间
        $this->joinRoom($room, $fd);

        // 更新连接信息
        $connection = $this->connectionTable->get($fd);
        $rooms = json_decode($connection['rooms'], true);
        $rooms[] = $room;
        $this->connectionTable->set($fd, [
            'rooms' => json_encode(array_unique($rooms)),
        ]);

        $server->push($fd, json_encode([
            'type' => 'subscribed',
            'room' => $room,
        ]));

        Log::info("Client subscribed to room", ['fd' => $fd, 'room' => $room]);
    }

    /**
     * 处理取消订阅
     */
    private function handleUnsubscribe(Server $server, int $fd, string $room): void
    {
        $this->leaveRoom($room, $fd);

        // 更新连接信息
        $connection = $this->connectionTable->get($fd);
        $rooms = json_decode($connection['rooms'], true);
        $rooms = array_filter($rooms, fn($r) => $r !== $room);
        $this->connectionTable->set($fd, [
            'rooms' => json_encode($rooms),
        ]);

        $server->push($fd, json_encode([
            'type' => 'unsubscribed',
            'room' => $room,
        ]));
    }

    /**
     * 加入房间
     */
    private function joinRoom(string $room, int $fd): void
    {
        $roomData = $this->roomTable->get($room);
        $members = $roomData ? json_decode($roomData['members'], true) : [];
        $members[] = $fd;
        
        $this->roomTable->set($room, [
            'members' => json_encode(array_unique($members)),
        ]);

        // 同步到Redis
        Redis::hset('ws:rooms', $room, json_encode($members));
    }

    /**
     * 离开房间
     */
    private function leaveRoom(string $room, int $fd): void
    {
        $roomData = $this->roomTable->get($room);
        if ($roomData) {
            $members = json_decode($roomData['members'], true);
            $members = array_filter($members, fn($m) => $m !== $fd);
            $this->roomTable->set($room, [
                'members' => json_encode(array_values($members)),
            ]);

            // 同步到Redis
            Redis::hset('ws:rooms', $room, json_encode(array_values($members)));
        }
    }

    /**
     * 广播消息到房间
     */
    private function broadcastToRoom(string $room, array $message): void
    {
        $roomData = $this->roomTable->get($room);
        if (!$roomData) {
            return;
        }

        $members = json_decode($roomData['members'], true);
        $message['timestamp'] = date('Y-m-d H:i:s');
        $jsonMessage = json_encode($message);

        foreach ($members as $fd) {
            if ($this->server->isEstablished($fd)) {
                $this->server->push($fd, $jsonMessage);
            }
        }
    }

    /**
     * 广播消息到所有连接
     */
    private function broadcastToAll(array $message): void
    {
        $message['timestamp'] = date('Y-m-d H:i:s');
        $jsonMessage = json_encode($message);

        foreach ($this->connectionTable as $row) {
            $fd = $row['fd'];
            if ($this->server->isEstablished($fd)) {
                $this->server->push($fd, $jsonMessage);
            }
        }
    }

    /**
     * 广播看板更新 (5秒一次)
     */
    private function broadcastDashboardUpdate(): void
    {
        // 获取看板数据
        $dashboardData = $this->getDashboardData();

        $this->broadcastToRoom('dashboard', [
            'type' => 'dashboard_update',
            'data' => $dashboardData,
        ]);
    }

    /**
     * 处理智能体状态更新
     */
    private function handleAgentStatusUpdate(array $payload): void
    {
        $this->broadcastToRoom('dashboard', [
            'type' => 'agent_status_update',
            'data' => $payload,
        ]);

        // 如果有特定智能体房间,也推送到那里
        if (isset($payload['agent_id'])) {
            $this->broadcastToRoom("agent_{$payload['agent_id']}", [
                'type' => 'agent_status_update',
                'data' => $payload,
            ]);
        }
    }

    /**
     * 处理任务状态更新
     */
    private function handleTaskStatusUpdate(array $payload): void
    {
        $this->broadcastToRoom('dashboard', [
            'type' => 'task_status_update',
            'data' => $payload,
        ]);

        // 如果有特定任务房间,也推送到那里
        if (isset($payload['task_id'])) {
            $this->broadcastToRoom("task_{$payload['task_id']}", [
                'type' => 'task_status_update',
                'data' => $payload,
            ]);
        }
    }

    /**
     * 订阅Redis频道 (用于跨进程通信)
     */
    private function subscribeToRedisChannels(): void
    {
        // 使用Swoole协程订阅Redis
        go(function () {
            $redis = new \Swoole\Coroutine\Redis();
            $redis->connect(env('REDIS_HOST', '127.0.0.1'), env('REDIS_PORT', 6379));

            $redis->subscribe(['agent_updates', 'task_updates'], function ($redis, $channel, $message) {
                $data = json_decode($message, true);
                
                // 投递到Task Worker处理
                $this->server->task([
                    'type' => $channel === 'agent_updates' ? 'agent_status_update' : 'task_status_update',
                    'data' => $data,
                ]);
            });
        });
    }

    /**
     * 获取看板数据
     */
    private function getDashboardData(): array
    {
        // 从Redis缓存获取
        $cacheKey = 'dashboard:data';
        $data = Redis::get($cacheKey);

        if ($data) {
            return json_decode($data, true);
        }

        // 缓存未命中,从数据库查询
        $agents = \App\Models\Agent::with('currentTask')->get()->toArray();
        $tasks = \App\Models\Task::with('assignedAgents')
            ->whereIn('status', ['pending', 'running'])
            ->orderBy('priority', 'desc')
            ->limit(50)
            ->get()
            ->toArray();

        $statistics = [
            'total_tasks' => \App\Models\Task::count(),
            'completed_tasks' => \App\Models\Task::where('status', 'completed')->count(),
            'running_tasks' => \App\Models\Task::where('status', 'running')->count(),
            'active_agents' => \App\Models\Agent::where('status', 'working')->count(),
        ];

        $data = [
            'agents' => $agents,
            'tasks' => $tasks,
            'statistics' => $statistics,
        ];

        // 缓存5秒
        Redis::setex($cacheKey, 5, json_encode($data));

        return $data;
    }

    /**
     * 验证Token
     */
    private function authenticateToken(string $token): ?array
    {
        try {
            // 这里使用JWT验证
            $payload = \JWTAuth::setToken($token)->getPayload();
            return [
                'id' => $payload->get('sub'),
                'name' => $payload->get('name'),
            ];
        } catch (\Exception $e) {
            return null;
        }
    }

    /**
     * 处理任务动作
     */
    private function handleTaskAction(Server $server, int $fd, array $data): void
    {
        $action = $data['action'] ?? '';
        $taskId = $data['task_id'] ?? '';
        $payload = $data['payload'] ?? [];

        // 调用相应的Controller处理业务逻辑
        // 通过HTTP API调用,这里只做转发
        // 实际生产环境应该使用消息队列

        $server->push($fd, json_encode([
            'type' => 'task_action_ack',
            'action' => $action,
            'task_id' => $taskId,
            'status' => 'processing',
        ]));
    }

    /**
     * 启动服务
     */
    public function start(): void
    {
        Log::info("WebSocket Server starting on {$this->config['host']}:{$this->config['port']}");
        $this->server->start();
    }

    /**
     * 停止服务
     */
    public function stop(): void
    {
        Log::info("WebSocket Server stopping");
        $this->server->shutdown();
    }
}
