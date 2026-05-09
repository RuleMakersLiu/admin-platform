"""埋点数据分析服务 - ClickHouse写入和分析"""
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from asynch import connect
from asynch.cursors import DictCursor
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)


class ClickHouseConfig:
    """ClickHouse配置"""

    def __init__(self):
        self.host = getattr(settings, 'clickhouse_host', 'localhost')
        self.port = getattr(settings, 'clickhouse_port', 9000)
        self.database = getattr(settings, 'clickhouse_database', 'analytics')
        self.user = getattr(settings, 'clickhouse_user', 'default')
        self.password = getattr(settings, 'clickhouse_password', '')

        self.connection = None

    async def connect(self):
        """连接到ClickHouse"""
        try:
            self.connection = await connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
            )
            logger.info(f"[ClickHouse] Connected to {self.host}:{self.port}/{self.database}")
        except Exception as e:
            logger.error(f"[ClickHouse] Connection failed: {e}")
            raise

    async def close(self):
        """关闭连接"""
        if self.connection:
            await self.connection.close()
            logger.info("[ClickHouse] Connection closed")

    async def execute(
        self, query: str, params: Optional[Dict] = None
    ) -> List[Dict]:
        """执行查询"""
        try:
            async with self.connection.cursor(cursor=DictCursor) as cursor:
                await cursor.execute(query, params or {})
                if cursor.description:
                    return await cursor.fetchall()
                return []
        except Exception as e:
            logger.error(f"[ClickHouse] Query failed: {e}\nQuery: {query}")
            raise


class TrackingAnalyzer:
    """埋点数据分析服务"""

    def __init__(self, clickhouse: ClickHouseConfig):
        self.clickhouse = clickhouse
        self._batch_buffer: List[Dict] = []
        self._batch_size = 1000
        self._flush_interval = 5  # 秒

    async def init_database(self):
        """初始化数据库和表"""
        # 创建数据库（如果不存在）
        create_db_sql = f"""
        CREATE DATABASE IF NOT EXISTS {self.clickhouse.database}
        """
        await self.clickhouse.execute(create_db_sql)

        # 创建事件表
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS tracking_events (
            event_id String,
            event_type String,
            event_name String,
            timestamp DateTime64(3),
            platform String,
            version String,
            user_id String,
            device_id String,
            session_id String,
            tenant_id String,
            admin_id String,
            username String,
            user_type String,
            device_type String,
            os String,
            os_version String,
            browser String,
            browser_version String,
            screen_width UInt32,
            screen_height UInt32,
            language String,
            ip String,
            country String,
            province String,
            city String,
            page_url String,
            page_title String,
            referrer String,
            page_duration UInt64,
            properties String,
            source String,
            user_agent String,
            created_at DateTime DEFAULT now()
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(timestamp)
        ORDER BY (tenant_id, event_type, timestamp)
        SETTINGS index_granularity = 8192
        """
        await self.clickhouse.execute(create_table_sql)
        logger.info("[TrackingAnalyzer] Database and tables initialized")

    async def insert_event(self, event_dict: Dict):
        """插入单个事件"""
        self._batch_buffer.append(event_dict)

        # 达到批量大小时刷新
        if len(self._batch_buffer) >= self._batch_size:
            await self.flush()

    async def insert_events(self, events: List[Dict]):
        """批量插入事件"""
        self._batch_buffer.extend(events)

        # 达到批量大小时刷新
        if len(self._batch_buffer) >= self._batch_size:
            await self.flush()

    async def flush(self):
        """刷新缓冲区到ClickHouse"""
        if not self._batch_buffer:
            return

        try:
            # 构建批量插入SQL
            insert_sql = """
            INSERT INTO tracking_events (
                event_id, event_type, event_name, timestamp,
                platform, version, user_id, device_id, session_id,
                tenant_id, admin_id, username, user_type,
                device_type, os, os_version, browser, browser_version,
                screen_width, screen_height, language,
                ip, country, province, city,
                page_url, page_title, referrer, page_duration,
                properties, source, user_agent
            ) VALUES
            """

            values = []
            params = {}
            for i, event in enumerate(self._batch_buffer):
                param_name = f"p{i}"
                values.append(f"({param_name})")
                params[param_name] = (
                    event.get('event_id', ''),
                    event.get('event_type', ''),
                    event.get('event_name', ''),
                    event.get('timestamp', datetime.now()),
                    event.get('platform', ''),
                    event.get('version', ''),
                    event.get('user_id', ''),
                    event.get('device_id', ''),
                    event.get('session_id', ''),
                    event.get('tenant_id', ''),
                    event.get('admin_id', ''),
                    event.get('username', ''),
                    event.get('user_type', ''),
                    event.get('device_type', ''),
                    event.get('os', ''),
                    event.get('os_version', ''),
                    event.get('browser', ''),
                    event.get('browser_version', ''),
                    event.get('screen_width', 0),
                    event.get('screen_height', 0),
                    event.get('language', ''),
                    event.get('ip', ''),
                    event.get('country', ''),
                    event.get('province', ''),
                    event.get('city', ''),
                    event.get('page_url', ''),
                    event.get('page_title', ''),
                    event.get('referrer', ''),
                    event.get('page_duration', 0),
                    event.get('properties', '{}'),
                    event.get('source', ''),
                    event.get('user_agent', ''),
                )

            if values:
                insert_sql += ', '.join(values)
                await self.clickhouse.execute(insert_sql, params)

                logger.info(
                    f"[TrackingAnalyzer] Inserted {len(self._batch_buffer)} events"
                )
                self._batch_buffer.clear()

        except Exception as e:
            logger.error(f"[TrackingAnalyzer] Failed to flush: {e}")
            raise

    # ==================== 分析查询 ====================

    async def get_event_count_by_type(
        self,
        tenant_id: str,
        start_time: datetime,
        end_time: datetime,
        event_type: Optional[str] = None,
    ) -> Dict[str, int]:
        """按事件类型统计数量"""
        where_clauses = [
            "tenant_id = %(tenant_id)s",
            "timestamp >= %(start_time)s",
            "timestamp <= %(end_time)s",
        ]
        params = {
            'tenant_id': tenant_id,
            'start_time': start_time,
            'end_time': end_time,
        }

        if event_type:
            where_clauses.append("event_type = %(event_type)s")
            params['event_type'] = event_type

        query = f"""
        SELECT event_type, count() as count
        FROM tracking_events
        WHERE {' AND '.join(where_clauses)}
        GROUP BY event_type
        ORDER BY count DESC
        """

        results = await self.clickhouse.execute(query, params)
        return {row['event_type']: row['count'] for row in results}

    async def get_daily_active_users(
        self,
        tenant_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> List[Dict]:
        """获取每日活跃用户数（DAU）"""
        query = """
        SELECT
            toDate(timestamp) as date,
            uniqExact(user_id) as dau
        FROM tracking_events
        WHERE tenant_id = %(tenant_id)s
            AND timestamp >= %(start_date)s
            AND timestamp <= %(end_date)s
            AND user_id != ''
        GROUP BY date
        ORDER BY date
        """

        results = await self.clickhouse.execute(
            query,
            {
                'tenant_id': tenant_id,
                'start_date': start_date,
                'end_date': end_date,
            },
        )
        return results

    async def get_monthly_active_users(
        self,
        tenant_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> List[Dict]:
        """获取每月活跃用户数（MAU）"""
        query = """
        SELECT
            toYYYYMM(timestamp) as month,
            uniqExact(user_id) as mau
        FROM tracking_events
        WHERE tenant_id = %(tenant_id)s
            AND timestamp >= %(start_date)s
            AND timestamp <= %(end_date)s
            AND user_id != ''
        GROUP BY month
        ORDER BY month
        """

        results = await self.clickhouse.execute(
            query,
            {
                'tenant_id': tenant_id,
                'start_date': start_date,
                'end_date': end_date,
            },
        )
        return results

    async def get_page_views_by_url(
        self,
        tenant_id: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 100,
    ) -> List[Dict]:
        """按URL统计页面浏览量"""
        query = """
        SELECT
            page_url,
            page_title,
            count() as page_views,
            uniqExact(user_id) as unique_visitors,
            avg(page_duration) as avg_duration
        FROM tracking_events
        WHERE tenant_id = %(tenant_id)s
            AND event_type = 'page_view'
            AND timestamp >= %(start_time)s
            AND timestamp <= %(end_time)s
        GROUP BY page_url, page_title
        ORDER BY page_views DESC
        LIMIT %(limit)s
        """

        results = await self.clickhouse.execute(
            query,
            {
                'tenant_id': tenant_id,
                'start_time': start_time,
                'end_time': end_time,
                'limit': limit,
            },
        )
        return results

    async def get_user_retention(
        self,
        tenant_id: str,
        cohort_date: datetime,
    ) -> Dict[str, float]:
        """计算用户留存率（简化版）"""
        # 获取当天的活跃用户
        cohort_users_query = """
        SELECT DISTINCT user_id
        FROM tracking_events
        WHERE tenant_id = %(tenant_id)s
            AND toDate(timestamp) = %(cohort_date)s
            AND user_id != ''
        """

        cohort_users = await self.clickhouse.execute(
            cohort_users_query,
            {'tenant_id': tenant_id, 'cohort_date': cohort_date},
        )

        if not cohort_users:
            return {}

        user_ids = [row['user_id'] for row in cohort_users]
        retention = {}

        # 计算后续每天的留存率
        for day_offset in [1, 3, 7, 14, 30]:
            target_date = cohort_date + timedelta(days=day_offset)

            retained_query = """
            SELECT uniqExact(user_id) as retained
            FROM tracking_events
            WHERE tenant_id = %(tenant_id)s
                AND toDate(timestamp) = %(target_date)s
                AND user_id IN %(user_ids)s
            """

            result = await self.clickhouse.execute(
                retained_query,
                {
                    'tenant_id': tenant_id,
                    'target_date': target_date,
                    'user_ids': user_ids,
                },
            )

            retained_count = result[0]['retained'] if result else 0
            retention[f'day_{day_offset}'] = (
                retained_count / len(user_ids) * 100 if user_ids else 0
            )

        return retention

    async def get_device_distribution(
        self,
        tenant_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> Dict[str, int]:
        """设备分布统计"""
        query = """
        SELECT device_type, count() as count
        FROM tracking_events
        WHERE tenant_id = %(tenant_id)s
            AND timestamp >= %(start_time)s
            AND timestamp <= %(end_time)s
            AND device_type != ''
        GROUP BY device_type
        ORDER BY count DESC
        """

        results = await self.clickhouse.execute(
            query,
            {
                'tenant_id': tenant_id,
                'start_time': start_time,
                'end_time': end_time,
            },
        )
        return {row['device_type']: row['count'] for row in results}

    async def get_geo_distribution(
        self,
        tenant_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[Dict]:
        """地理位置分布"""
        query = """
        SELECT
            province,
            city,
            count() as count,
            uniqExact(user_id) as unique_users
        FROM tracking_events
        WHERE tenant_id = %(tenant_id)s
            AND timestamp >= %(start_time)s
            AND timestamp <= %(end_time)s
            AND province != ''
        GROUP BY province, city
        ORDER BY count DESC
        LIMIT 50
        """

        results = await self.clickhouse.execute(
            query,
            {
                'tenant_id': tenant_id,
                'start_time': start_time,
                'end_time': end_time,
            },
        )
        return results


# 全局实例
_clickhouse_config: Optional[ClickHouseConfig] = None
_tracking_analyzer: Optional[TrackingAnalyzer] = None


async def get_tracking_analyzer() -> TrackingAnalyzer:
    """获取埋点分析器单例"""
    global _clickhouse_config, _tracking_analyzer

    if _tracking_analyzer is None:
        _clickhouse_config = ClickHouseConfig()
        await _clickhouse_config.connect()

        _tracking_analyzer = TrackingAnalyzer(_clickhouse_config)
        await _tracking_analyzer.init_database()

    return _tracking_analyzer


async def close_tracking_analyzer():
    """关闭埋点分析器"""
    global _clickhouse_config

    if _clickhouse_config:
        await _clickhouse_config.close()
        _clickhouse_config = None
