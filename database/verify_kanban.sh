#!/bin/bash

# 看板系统数据库验证脚本
# 用于验证看板相关的数据表和初始数据

set -e

echo "======================================"
echo "看板系统数据库验证"
echo "======================================"

# 数据库连接参数
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-admin_platform}"
DB_USER="${DB_USER:-postgres}"
DB_PASSWORD="${DB_PASSWORD:-postgres}"

# 设置环境变量
export PGPASSWORD="$DB_PASSWORD"

echo "🔗 数据库: $DB_HOST:$DB_PORT/$DB_NAME"
echo ""

# 1. 检查表是否存在
echo "📋 检查表是否存在..."
TABLES=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND table_name IN ('agents', 'tasks', 'agent_sessions', 'collaboration_records', 'session_messages')
ORDER BY table_name;
")

if [ -z "$TABLES" ]; then
    echo "❌ 未找到看板相关表！请先执行 init_kanban.sh"
    exit 1
fi

echo "✅ 找到以下表:"
echo "$TABLES"
echo ""

# 2. 检查智能体数据
echo "🤖 检查智能体数据..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "
SELECT 
    code AS 编码, 
    name AS 名称, 
    max_concurrent_tasks AS 最大并发,
    status AS 状态
FROM agents 
ORDER BY code;
"
echo ""

# 3. 检查表的字段数量
echo "📊 表结构统计..."
for TABLE in agents tasks agent_sessions collaboration_records session_messages; do
    COUNT=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "
    SELECT COUNT(*) 
    FROM information_schema.columns 
    WHERE table_schema = 'public' AND table_name = '$TABLE';
    ")
    echo "  - $TABLE: $(echo $COUNT) 个字段"
done
echo ""

# 4. 检查索引
echo "🔍 检查索引..."
INDEX_COUNT=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "
SELECT COUNT(*)
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('agents', 'tasks', 'agent_sessions', 'collaboration_records', 'session_messages');
")
echo "  总索引数: $(echo $INDEX_COUNT)"
echo ""

# 5. 检查外键约束
echo "🔗 检查外键约束..."
FK_COUNT=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "
SELECT COUNT(*)
FROM information_schema.table_constraints
WHERE constraint_type = 'FOREIGN KEY'
  AND table_schema = 'public'
  AND table_name IN ('agents', 'tasks', 'agent_sessions', 'collaboration_records', 'session_messages');
")
echo "  外键约束数: $(echo $FK_COUNT)"
echo ""

echo "======================================"
echo "✅ 验证完成！"
echo ""
echo "📚 提示:"
echo "  - 查看 README: cat database/KANBAN_README.md"
echo "  - 连接数据库: psql -h $DB_HOST -U $DB_USER -d $DB_NAME"
echo "  - 查看表结构: \d agents"
echo "======================================"
