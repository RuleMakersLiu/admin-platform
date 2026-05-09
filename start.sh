#!/bin/bash

# 后台管理系统启动脚本
# 使用方法: ./start.sh [all|backend|gateway|generator|deploy|config|python|frontend]

cd "$(dirname "$0")"

export PATH=/usr/local/go/bin:$PATH

case "$1" in
    backend)
        echo "启动Python后端..."
        cd admin-python
        source .venv/bin/activate 2>/dev/null || pip install -e . && python -m app.main
        ;;
    gateway)
        echo "启动Go网关..."
        cd admin-gateway
        go run cmd/main.go
        ;;
    generator)
        echo "启动Go代码生成器..."
        cd admin-generator
        go run cmd/server/main.go
        ;;
    deploy)
        echo "启动Go部署服务..."
        cd admin-deploy
        go run cmd/server/main.go
        ;;
    config)
        echo "启动Go配置服务..."
        cd admin-config
        go run cmd/main.go
        ;;
    python)
        echo "启动Python后端..."
        cd admin-python
        python -m app.main
        ;;
    frontend)
        echo "启动React前端..."
        cd admin-frontend
        npm run dev
        ;;
    infra)
        echo "启动基础设施(PostgreSQL + Redis)..."
        cd docker
        docker compose -f docker-compose.infra.yml up -d
        echo "等待数据库启动..."
        sleep 5
        echo "初始化数据库..."
        docker exec -i admin-postgres psql -U postgres -d admin_platform < ../database/schema_agent.sql 2>/dev/null || echo "数据库可能已初始化"
        ;;
    all)
        echo "启动所有服务..."

        # 启动基础设施
        cd docker
        docker compose -f docker-compose.infra.yml up -d
        cd ..
        sleep 5

        # 初始化数据库
        echo "初始化数据库..."
        docker exec -i admin-postgres psql -U postgres -d admin_platform < database/schema_agent.sql 2>/dev/null || echo "数据库可能已初始化"

        # 启动Go网关
        cd admin-gateway
        go run cmd/main.go &
        GATEWAY_PID=$!
        cd ..
        sleep 2

        # 启动Go代码生成
        cd admin-generator
        go run cmd/server/main.go &
        GENERATOR_PID=$!
        cd ..
        sleep 2

        # 启动Go部署服务
        cd admin-deploy
        go run cmd/server/main.go &
        DEPLOY_PID=$!
        cd ..
        sleep 2

        # 启动Go配置服务
        cd admin-config
        go run cmd/main.go &
        CONFIG_PID=$!
        cd ..
        sleep 2

        # 启动Python后端
        cd admin-python
        python -m app.main &
        PYTHON_PID=$!
        cd ..
        sleep 2

        # 启动前端
        cd admin-frontend
        npm run dev &
        FRONTEND_PID=$!
        cd ..

        echo ""
        echo "=========================================="
        echo "服务启动完成:"
        echo "  - 前端:       http://localhost:3000"
        echo "  - 网关:       http://localhost:8080"
        echo "  - Python后端: http://localhost:8081/api"
        echo "  - 代码生成:   http://localhost:8082/generator"
        echo "  - 部署服务:   http://localhost:8083/deploy"
        echo "  - 配置服务:   http://localhost:8085/config"
        echo "=========================================="
        echo ""
        echo "进程ID:"
        echo "  - 网关:       $GATEWAY_PID"
        echo "  - 代码生成:   $GENERATOR_PID"
        echo "  - 部署服务:   $DEPLOY_PID"
        echo "  - 配置服务:   $CONFIG_PID"
        echo "  - Python后端: $PYTHON_PID"
        echo "  - 前端:       $FRONTEND_PID"
        ;;
    stop)
        echo "停止所有服务..."
        cd docker
        docker compose -f docker-compose.infra.yml down
        pkill -f "admin-gateway/cmd" 2>/dev/null
        pkill -f "admin-generator" 2>/dev/null
        pkill -f "admin-deploy" 2>/dev/null
        pkill -f "admin-config" 2>/dev/null
        pkill -f "admin-python" 2>/dev/null
        pkill -f "uvicorn" 2>/dev/null
        pkill -f "vite" 2>/dev/null
        echo "服务已停止"
        ;;
    *)
        echo "使用方法: $0 {all|infra|backend|gateway|generator|deploy|config|python|frontend|stop}"
        exit 1
        ;;
esac
