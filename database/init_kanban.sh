#!/bin/bash

# 看板系统数据库初始化脚本
# 用于创建看板相关的数据表和初始数据

set -e

echo "======================================"
echo "看板系统数据库初始化"
echo "======================================"

# 数据库连接参数
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-admin_platform}"
DB_USER="${DB_USER:-postgres}"
DB_PASSWORD="${DB_PASSWORD:-postgres}"

# SQL文件路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KANBAN_SCHEMA="${SCRIPT_DIR}/kanban_schema.sql"

# 检查SQL文件是否存在
if [ ! -f "$KANBAN_SCHEMA" ]; then
    echo "❌ 错误: 找不到SQL文件 $KANBAN_SCHEMA"
    exit 1
fi

echo "📋 SQL文件: $KANBAN_SCHEMA"
echo "🔗 数据库: $DB_HOST:$DB_PORT/$DB_NAME"
echo ""

# 设置环境变量
export PGPASSWORD="$DB_PASSWORD"

# 执行SQL脚本
echo "⏳ 正在执行SQL脚本..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$KANBAN_SCHEMA"

# 检查执行结果
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 看板系统数据库初始化完成！"
    echo ""
    echo "📊 已创建的表:"
    echo "  - agents (智能体表)"
    echo "  - tasks (任务表)"
    echo "  - agent_sessions (智能体会话表)"
    echo "  - collaboration_records (协作记录表)"
    echo "  - session_messages (会话消息表)"
    echo ""
    echo "🤖 已插入的智能体:"
    echo "  - BE  (后端开发)"
    echo "  - FE  (前端开发)"
    echo "  - PJM (项目经理)"
    echo "  - QA  (测试工程师)"
    echo "  - ARCH (系统架构师)"
    echo "  - CR  (代码审查)"
    echo ""
    echo "======================================"
else
    echo ""
    echo "❌ 数据库初始化失败！"
    echo "请检查数据库连接和SQL脚本"
    exit 1
fi
