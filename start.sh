#!/bin/bash

# 后台管理系统启动脚本
# 使用方法: ./start.sh [all|backend|gateway|generator|deploy|config|python|frontend|eval|sandbox-controller|egress|eval-infra|eval-migrate|stop]

cd "$(dirname "$0")"
PROJECT_ROOT="$(pwd)"

export PATH=/usr/local/go/bin:$PATH

safe_eval_defaults() {
    # Local startup must remain fail-closed. These values cannot enable external
    # Agent execution, sandbox mutation, or egress even if a developer forgets
    # to configure the security approvals.
    export EVAL_EXECUTION_ENABLED=false
    export SANDBOX_EXECUTION_ENABLED=false
    export EGRESS_EXECUTION_ENABLED=false
    export EGRESS_BUDGET_STORE=disabled
    export EGRESS_DESTINATIONS_JSON='[]'
}

ensure_eval_internal_token() {
    if [ -n "${EVAL_INTERNAL_SERVICE_TOKEN:-}" ]; then
        return
    fi
    if command -v openssl >/dev/null 2>&1; then
        EVAL_INTERNAL_SERVICE_TOKEN="$(openssl rand -hex 32)"
    else
        EVAL_INTERNAL_SERVICE_TOKEN="$(python -c 'import secrets; print(secrets.token_hex(32))')"
    fi
    export EVAL_INTERNAL_SERVICE_TOKEN
    echo "已生成仅当前启动会话使用的测评内部令牌（不会写入文件）。"
}

eval_python() {
    if [ -x "admin-eval/.venv/bin/python" ]; then
        echo "$PROJECT_ROOT/admin-eval/.venv/bin/python"
    elif [ -x ".venv/bin/python" ]; then
        echo "$PROJECT_ROOT/.venv/bin/python"
    else
        command -v python
    fi
}

prepare_eval_python() {
    local python_bin
    python_bin="$(eval_python)"
    if ! "$python_bin" -c 'import fastapi, sqlalchemy, asyncpg, aiokafka' >/dev/null 2>&1; then
        echo "安装 admin-eval 依赖..."
        "$python_bin" -m pip install -e ./admin-eval
    fi
}

start_eval_service() {
    prepare_eval_python
    local python_bin
    python_bin="$(eval_python)"
    (
        cd admin-eval
        exec "$python_bin" -m uvicorn app.main:app --host 0.0.0.0 --port 8091
    )
}

start_sandbox_controller() {
    (
        cd admin-sandbox-controller
        exec go run ./cmd/controller
    )
}

start_egress_gateway() {
    (
        cd admin-egress-gateway
        exec go run ./cmd/gateway
    )
}

start_eval_infra() {
    (
        cd docker
        docker compose -f docker-compose.eval.yml up -d
    )
}

apply_eval_migrations() {
    echo "应用 Agent 测评数据库迁移..."
    for migration in \
        database/migrations/006_agent_evaluation_platform.up.sql \
        database/migrations/009_eval_golden_case.up.sql \
        database/migrations/018_agent_eval_dataset_workflow.up.sql; do
        echo "  - $migration"
        docker compose -f docker/docker-compose.infra.yml exec -T postgres \
            psql -v ON_ERROR_STOP=1 -U postgres -d admin_platform < "$migration"
    done
    echo "Agent 测评数据库迁移完成。"
}

safe_eval_defaults

case "$1" in
    backend)
        echo "启动Python后端..."
        cd admin-python
        if [ -f .venv/bin/activate ]; then
            source .venv/bin/activate
        else
            pip install -e .
        fi
        python -m app.main
        ;;
    gateway)
        echo "启动Go网关..."
        if [ -z "${EVAL_INTERNAL_SERVICE_TOKEN:-}" ]; then
            echo "警告：未设置 EVAL_INTERNAL_SERVICE_TOKEN，Agent 测评控制面请求会被拒绝。"
        fi
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
    eval)
        echo "启动 Agent 测评控制面（执行门禁保持关闭）..."
        if [ -z "${EVAL_INTERNAL_SERVICE_TOKEN:-}" ]; then
            echo "错误：单独启动时必须先设置 EVAL_INTERNAL_SERVICE_TOKEN，并与 Gateway 保持一致。" >&2
            exit 1
        fi
        start_eval_service
        ;;
    sandbox-controller)
        echo "启动沙箱控制器（Kubernetes执行门禁保持关闭）..."
        start_sandbox_controller
        ;;
    egress)
        echo "启动出口网关（外部访问门禁保持关闭）..."
        start_egress_gateway
        ;;
    eval-infra)
        echo "启动测评基础设施（Kafka + ClickHouse + MinIO + OTel）..."
        start_eval_infra
        ;;
    eval-migrate)
        apply_eval_migrations
        ;;
    infra)
        echo "启动基础设施(PostgreSQL + Redis)..."
        cd docker
        docker compose -f docker-compose.infra.yml up -d
        echo "等待数据库启动..."
        sleep 5
        echo "基础设施已启动；不会在启动时重置数据库。"
        ;;
    all)
        echo "启动所有服务..."

        # 启动基础设施
        cd docker
        docker compose -f docker-compose.infra.yml up -d
        cd ..
        start_eval_infra
        sleep 5

        echo "提示：数据库迁移不会自动执行；首次使用测评数据集请运行 ./start.sh eval-migrate。"

        # Gateway and admin-eval must share one in-memory service token. It is
        # generated for this process tree only and is never written to disk.
        ensure_eval_internal_token

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

        # 启动Agent测评控制面（所有执行门禁默认关闭）
        start_eval_service &
        EVAL_PID=$!
        sleep 2

        # 启动沙箱控制器（仅提供策略校验与计划；不创建Kubernetes资源）
        start_sandbox_controller &
        SANDBOX_CONTROLLER_PID=$!
        sleep 2

        # 启动出口网关（无G0/G1审批时拒绝所有代理调用）
        start_egress_gateway &
        EGRESS_PID=$!
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
        echo "  - 测评控制面: http://localhost:8091/health"
        echo "  - 沙箱控制器: http://localhost:8092/health"
        echo "  - 出口网关:   http://localhost:8093/health"
        echo "=========================================="
        echo ""
        echo "进程ID:"
        echo "  - 网关:       $GATEWAY_PID"
        echo "  - 代码生成:   $GENERATOR_PID"
        echo "  - 部署服务:   $DEPLOY_PID"
        echo "  - 配置服务:   $CONFIG_PID"
        echo "  - Python后端: $PYTHON_PID"
        echo "  - 测评控制面: $EVAL_PID"
        echo "  - 沙箱控制器: $SANDBOX_CONTROLLER_PID"
        echo "  - 出口网关:   $EGRESS_PID"
        echo "  - 前端:       $FRONTEND_PID"
        echo ""
        echo "注意：首次使用数据集工厂前，请显式执行 ./start.sh eval-migrate。"
        echo "Agent执行、Kubernetes变更和外部访问门禁仍保持关闭。"
        ;;
    stop)
        echo "停止所有服务..."
        cd docker
        docker compose -f docker-compose.infra.yml down
        docker compose -f docker-compose.eval.yml down
        cd ..
        pkill -f "admin-gateway/cmd" 2>/dev/null
        pkill -f "admin-generator" 2>/dev/null
        pkill -f "admin-deploy" 2>/dev/null
        pkill -f "admin-config" 2>/dev/null
        pkill -f "admin-python" 2>/dev/null
        pkill -f "admin-eval.*uvicorn" 2>/dev/null
        pkill -f "cmd/controller" 2>/dev/null
        pkill -f "cmd/gateway" 2>/dev/null
        pkill -f "uvicorn" 2>/dev/null
        pkill -f "vite" 2>/dev/null
        echo "服务已停止"
        ;;
    *)
        echo "使用方法: $0 {all|infra|eval-infra|eval-migrate|backend|gateway|generator|deploy|config|python|frontend|eval|sandbox-controller|egress|stop}"
        exit 1
        ;;
esac
