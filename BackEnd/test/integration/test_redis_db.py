"""
Redis 数据库层集成测试
"""

import pytest
import asyncio
import time
import json

from db.database_v2 import DatabaseLayerV2
from db.redis import (
    init_redis,
    close_redis,
    get_redis,
    add_delayed_task,
    batch_pop_due_tasks,
    get_earliest_score,
    add_delayed_task_with_limit,
    redis_incr_expire,
    redis_get,
)
from config.db_config import get_redis_config


# ==================== SC-R-01 Redis 连接池管理与初始化 ====================

@pytest.mark.integration
@pytest.mark.db
class TestRedisConnection:
    """Redis 连接测试"""

    async def test_init_redis_success(self):
        """TC-R-01-01: 正常初始化 Redis"""
        await init_redis()
        client = get_redis()
        assert client is not None
        await close_redis()

    async def test_reinit_redis(self):
        """TC-R-01-02: 重复初始化 Redis"""
        await init_redis()
        await init_redis()  # 重复初始化应该不报错
        client = get_redis()
        assert client is not None
        await close_redis()

    async def test_close_and_reinit_redis(self):
        """TC-R-01-03: 关闭并重新初始化 Redis"""
        await init_redis()
        await close_redis()
        with pytest.raises(RuntimeError):
            get_redis()
        await init_redis()
        client = get_redis()
        assert client is not None
        await close_redis()

    async def test_ping_redis(self, db_redis: DatabaseLayerV2):
        """TC-R-01-04: ping_redis 健康检查"""
        result = await db_redis.ping_redis()
        assert result is True


# ==================== SC-R-02 Redis 基础 CRUD 操作 ====================

@pytest.mark.integration
@pytest.mark.db
class TestRedisBasicCRUD:
    """Redis 基础 CRUD 测试"""

    async def test_set_get_string(self, redis_pool):
        """TC-R-02-01: SET/GET 字符串"""
        test_key = "test:string"
        test_value = "hello, redis!"
        await redis_pool.set(test_key, test_value)
        result = await redis_pool.get(test_key)
        assert result == test_value

    async def test_del_key(self, redis_pool):
        """TC-R-02-02: DEL 删除 key"""
        test_key = "test:delete"
        await redis_pool.set(test_key, "value")
        deleted = await redis_pool.delete(test_key)
        assert deleted == 1
        result = await redis_pool.get(test_key)
        assert result is None

    async def test_exists_key(self, redis_pool):
        """TC-R-02-03: EXISTS 检查存在性"""
        test_key = "test:exists"
        exists = await redis_pool.exists(test_key)
        assert exists == 0
        await redis_pool.set(test_key, "value")
        exists = await redis_pool.exists(test_key)
        assert exists == 1

    async def test_expire_ttl(self, redis_pool):
        """TC-R-02-04: EXPIRE 设置过期"""
        test_key = "test:expire"
        await redis_pool.set(test_key, "value")
        await redis_pool.expire(test_key, 10)
        ttl = await redis_pool.ttl(test_key)
        assert ttl > 0 and ttl <= 10


# ==================== SC-R-03 Redis 延迟队列功能 ====================

@pytest.mark.integration
@pytest.mark.db
class TestRedisDelayedQueue:
    """Redis 延迟队列测试"""

    async def test_add_delayed_task(self, redis_pool):
        """TC-R-03-01: 添加延迟任务"""
        task_json = json.dumps({"id": "test1", "data": "test"})
        execute_at = time.time() + 3600  # 1小时后
        added = await add_delayed_task(task_json, execute_at)
        assert added == 1

    async def test_get_earliest_score(self, redis_pool):
        """TC-R-03-02: 获取最早任务 score"""
        # 先添加几个任务
        now = time.time()
        task1 = json.dumps({"id": "t1"})
        task2 = json.dumps({"id": "t2"})
        await add_delayed_task(task1, now + 3600)
        await add_delayed_task(task2, now + 1800)
        
        earliest = await get_earliest_score()
        assert earliest is not None
        assert abs(earliest - (now + 1800)) < 1

    async def test_batch_pop_due_tasks(self, redis_pool):
        """TC-R-03-03: 批量弹出到期任务"""
        now = time.time()
        task1 = json.dumps({"id": "due1"})
        task2 = json.dumps({"id": "due2"})
        task3 = json.dumps({"id": "not_due"})
        
        # 添加到期任务
        await add_delayed_task(task1, now - 3600)
        await add_delayed_task(task2, now - 1800)
        # 添加未到期任务
        await add_delayed_task(task3, now + 3600)
        
        popped = await batch_pop_due_tasks(now, 10)
        assert len(popped) == 2
        task_ids = [json.loads(t)["id"] for t in popped]
        assert "due1" in task_ids
        assert "due2" in task_ids

    async def test_batch_pop_limit(self, redis_pool):
        """TC-R-03-04: 弹出数量限制"""
        now = time.time()
        for i in range(5):
            task = json.dumps({"id": f"t{i}"})
            await add_delayed_task(task, now - 3600)
        
        popped = await batch_pop_due_tasks(now, 2)
        assert len(popped) == 2

    async def test_add_delayed_task_with_limit(self, redis_pool):
        """TC-R-03-05: 带限速添加任务"""
        task = json.dumps({"id": "rate_test"})
        cooldown = 1.0
        execute_at = await add_delayed_task_with_limit(task, cooldown)
        assert execute_at is not None
        # 允许小的时间偏差
        assert execute_at >= time.time() - 1.0

    async def test_add_delayed_task_no_limit(self, redis_pool):
        """TC-R-03-06: 不限速添加任务"""
        task = json.dumps({"id": "no_rate_test"})
        execute_at = await add_delayed_task_with_limit(task, 0.0)
        now = time.time()
        # 不限速时 execute_at 应该接近当前时间
        assert abs(execute_at - now) < 1


# ==================== SC-R-04 Redis 通用计数器功能 ====================

@pytest.mark.integration
@pytest.mark.db
class TestRedisCounter:
    """Redis 计数器测试"""

    async def test_counter_first_increment(self, redis_pool):
        """TC-R-04-01: 计数器首次递增"""
        test_key = "test:counter:first"
        count = await redis_incr_expire(test_key, 60)
        assert count == 1
        ttl = await redis_pool.ttl(test_key)
        assert ttl > 0 and ttl <= 60

    async def test_counter_multiple_increments(self, redis_pool):
        """TC-R-04-02: 计数器多次递增"""
        test_key = "test:counter:multiple"
        count1 = await redis_incr_expire(test_key, 60)
        count2 = await redis_incr_expire(test_key, 60)
        count3 = await redis_incr_expire(test_key, 60)
        assert count1 == 1
        assert count2 == 2
        assert count3 == 3

    async def test_counter_expire_reset(self, redis_pool):
        """TC-R-04-03: 计数器过期重置"""
        test_key = "test:counter:expire"
        await redis_incr_expire(test_key, 1)
        # 等待过期
        await asyncio.sleep(1.5)
        # 再次递增应该从 1 开始
        count = await redis_incr_expire(test_key, 60)
        assert count == 1

    async def test_get_counter_value(self, redis_pool):
        """TC-R-04-04: 获取计数器值"""
        from db.redis import redis_get
        test_key = "test:counter:get"
        
        # 不存在返回 0
        val = await redis_get(test_key)
        assert val is None
        
        # 递增后能获取正确值
        await redis_incr_expire(test_key, 60)
        val = await redis_get(test_key)
        assert int(val) == 1


# ==================== SC-R-05 Redis Lua 脚本原子性 ====================

@pytest.mark.integration
@pytest.mark.db
class TestRedisLuaScript:
    """Redis Lua 脚本原子性测试"""

    async def test_batch_pop_atomicity(self, redis_pool):
        """TC-R-05-01: 批量弹出原子性"""
        # 先清空队列
        await redis_pool.delete(get_redis_config().delay_queue_key)
        
        now = time.time()
        task = json.dumps({"id": "atomic_test"})
        await add_delayed_task(task, now - 3600)
        
        # 并发弹出
        results = []
        async def pop_task():
            popped = await batch_pop_due_tasks(now, 1)
            if popped:
                results.extend(popped)
        
        tasks = [pop_task() for _ in range(5)]
        await asyncio.gather(*tasks)
        
        # 任务只能被弹出一次
        assert len(results) == 1

    async def test_rate_limit_atomicity(self, redis_pool):
        """TC-R-05-02: 限速写入原子性"""
        task = json.dumps({"id": "rate_atomic_test"})
        cooldown = 1.0
        
        # 并发调用限速写入
        execute_ats = []
        async def add_task():
            at = await add_delayed_task_with_limit(task, cooldown)
            execute_ats.append(at)
        
        tasks = [add_task() for _ in range(3)]
        await asyncio.gather(*tasks)
        
        # 检查任务间隔是否符合限速
        sorted_ats = sorted(execute_ats)
        for i in range(1, len(sorted_ats)):
            diff = sorted_ats[i] - sorted_ats[i-1]
            assert diff >= cooldown - 0.1


# ==================== SC-R-06 DatabaseLayerV2 Redis 接口 ====================

@pytest.mark.integration
@pytest.mark.db
class TestDatabaseLayerRedis:
    """DatabaseLayerV2 Redis 接口测试"""

    async def test_db_add_delayed_task(self, db_redis: DatabaseLayerV2):
        """TC-R-06-01: DatabaseLayer add_delayed_task"""
        task = json.dumps({"id": "db_test"})
        execute_at = time.time() + 3600
        added = await db_redis.add_delayed_task(task, execute_at)
        assert added == 1

    async def test_db_batch_pop_due_tasks(self, db_redis: DatabaseLayerV2, redis_pool):
        """TC-R-06-02: DatabaseLayer batch_pop_due_tasks"""
        now = time.time()
        task = json.dumps({"id": "db_pop_test"})
        await add_delayed_task(task, now - 3600)
        
        popped = await db_redis.batch_pop_due_tasks(now, 10)
        assert len(popped) == 1

    async def test_db_get_earliest_score(self, db_redis: DatabaseLayerV2):
        """TC-R-06-03: DatabaseLayer get_earliest_score"""
        now = time.time()
        task = json.dumps({"id": "db_earliest_test"})
        await add_delayed_task(task, now + 3600)
        
        earliest = await db_redis.get_earliest_score()
        assert earliest is not None

    async def test_db_increment_counter(self, db_redis: DatabaseLayerV2):
        """TC-R-06-04: DatabaseLayer increment_counter"""
        test_key = "test:db:counter"
        count = await db_redis.increment_counter(test_key, 60)
        assert count == 1

    async def test_db_get_counter(self, db_redis: DatabaseLayerV2):
        """TC-R-06-05: DatabaseLayer get_counter"""
        test_key = "test:db:get_counter"
        val = await db_redis.get_counter(test_key)
        assert val == 0
        
        await db_redis.increment_counter(test_key, 60)
        val = await db_redis.get_counter(test_key)
        assert val == 1

    async def test_db_add_delayed_task_with_limit(self, db_redis: DatabaseLayerV2):
        """TC-R-06-06: DatabaseLayer add_delayed_task_with_limit"""
        task = json.dumps({"id": "db_rate_test"})
        execute_at = await db_redis.add_delayed_task_with_limit(task, 1.0)
        assert execute_at is not None


# ==================== SC-R-07 Redis 并发操作 ====================

@pytest.mark.integration
@pytest.mark.db
class TestRedisConcurrency:
    """Redis 并发操作测试"""

    async def test_concurrent_add_delayed_tasks(self, redis_pool):
        """TC-R-07-01: 并发添加延迟任务"""
        # 先清空队列
        await redis_pool.delete(get_redis_config().delay_queue_key)
        
        now = time.time()
        execute_at = now + 3600
        
        async def add_task(i: int):
            task = json.dumps({"id": f"task{i}"})
            await add_delayed_task(task, execute_at)
        
        tasks = [add_task(i) for i in range(10)]
        await asyncio.gather(*tasks)
        
        # 检查所有任务都已添加
        count = await redis_pool.zcard(get_redis_config().delay_queue_key)
        assert count == 10

    async def test_concurrent_increment_counter(self, redis_pool):
        """TC-R-07-02: 并发递增计数器"""
        test_key = "test:concurrency:counter"
        
        async def incr():
            await redis_incr_expire(test_key, 60)
        
        tasks = [incr() for _ in range(10)]
        await asyncio.gather(*tasks)
        
        # 检查最终计数
        val = await redis_get(test_key)
        assert int(val) == 10

    async def test_concurrent_batch_pop(self, redis_pool):
        """TC-R-07-03: 并发批量弹出"""
        # 先清空队列
        await redis_pool.delete(get_redis_config().delay_queue_key)
        
        now = time.time()
        for i in range(10):
            task = json.dumps({"id": f"concurrent_pop{i}"})
            await add_delayed_task(task, now - 3600)
        
        # 分批并发弹出，避免连接数过多
        popped_count = 0
        for batch in range(3):  # 3批，每批5个
            results = []
            async def pop_task():
                popped = await batch_pop_due_tasks(now, 1)
                if popped:
                    results.extend(popped)
            tasks = [pop_task() for _ in range(5)]
            await asyncio.gather(*tasks)
            popped_count += len(results)
        
        # 所有任务都被弹出，且不重复
        assert popped_count == 10


# ==================== SC-R-08 Redis 错误处理与异常 ====================

@pytest.mark.integration
@pytest.mark.db
class TestRedisErrorHandling:
    """Redis 错误处理测试"""

    async def test_invalid_task_json(self):
        """TC-R-08-01: 添加任务参数非法"""
        invalid_json = "{this is not json}"
        execute_at = time.time()
        with pytest.raises(ValueError):
            await add_delayed_task(invalid_json, execute_at)

    async def test_negative_execute_at(self):
        """TC-R-08-02: execute_at 负数"""
        task = json.dumps({"id": "test"})
        with pytest.raises(ValueError):
            await add_delayed_task(task, -100.0)

    async def test_batch_pop_limit_out_of_bounds(self):
        """TC-R-08-03: batch_pop limit 越界"""
        now = time.time()
        with pytest.raises(ValueError):
            await batch_pop_due_tasks(now, 0)
        with pytest.raises(ValueError):
            await batch_pop_due_tasks(now, 1001)

    async def test_redis_not_initialized(self):
        """TC-R-08-04: Redis 未初始化"""
        # 确保 Redis 未初始化
        await close_redis()
        with pytest.raises(RuntimeError):
            get_redis()
        # 重新初始化
        await init_redis()

    async def test_empty_task_json(self):
        """TC-R-08-05: 空 task_json"""
        with pytest.raises(ValueError):
            await add_delayed_task_with_limit("", 1.0)
