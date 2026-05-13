# Redis 连接器文档

## 功能概述

Redis 连接器提供 Redis 客户端管理，特别针对**延迟队列**场景进行了优化，使用 Lua 脚本保证原子操作。

---

## 核心方法

| 方法 | 用途 | 参数说明 | 返回值 | 示例 |
|------|------|---------|--------|------|
| `init_redis()` | 初始化 Redis 客户端 | 无 | `None` | 应用启动时调用 |
| `close_redis()` | 关闭 Redis 客户端 | 无 | `None` | 应用关闭时调用 |
| `get_redis()` | 获取 Redis 客户端实例 | 无 | `Redis` | 内部使用 |
| `add_delayed_task(task_json, execute_at)` | 添加延迟任务 | `task_json`: 任务数据（JSON 字符串）<br>`execute_at`: 执行时间戳（毫秒） | `int` (添加数量) | 添加定时任务 |
| `batch_pop_due_tasks(now, limit)` | 批量弹出到期任务 | `now`: 当前时间戳<br>`limit`: 最大弹出数量 | `List[str]` (任务 JSON 列表) | 获取到期任务 |
| `get_earliest_score()` | 获取最早任务的执行时间 | 无 | `Optional[float]` | 检查延迟队列 |

---

## 使用示例

### 1. 添加延迟任务

```python
from db.redis import add_delayed_task
import json

# 构建任务数据
task_data = {
    "task_id": 123,
    "task_type": "send_email",
    "user_id": 456,
    "template": "welcome"
}
task_json = json.dumps(task_data)

# 2 小时后执行任务
import time
execute_at = time.time() * 1000 + 2 * 60 * 60 * 1000  # 当前时间 + 2 小时

# 添加延迟任务到 ZSet
added = await add_delayed_task(task_json, execute_at)

# 返回添加数量
# 1
```

### 2. 批量弹出到期任务

```python
from db.redis import batch_pop_due_tasks
import json

# 获取当前时间戳（毫秒）
import time
now = time.time() * 1000

# 批量弹出到期的任务（最多 10 个）
tasks = await batch_pop_due_tasks(now=now, limit=10)

# 返回结果
# [
#   '{"task_id": 123, "task_type": "send_email", ...}',
#   '{"task_id": 124, "task_type": "remind", ...}',
#   ...
# ]

# 处理任务
for task_json in tasks:
    task = json.loads(task_json)
    print(f"处理任务: {task['task_id']}")
```

### 3. 检查最早任务的执行时间

```python
from db.redis import get_earliest_score

# 获取延迟队列中最早任务的执行时间
earliest_time = await get_earliest_score()

if earliest_time:
    print(f"最早任务将在时间戳 {earliest_time} 执行")
else:
    print("延迟队列为空")
```

---

## 延迟队列工作原理

```
┌─────────────────────────────────────────────────────────────┐
│                    Redis ZSet (Score-Member)                │
│                                                             │
│  Score (执行时间戳)     Member (任务 JSON)                  │
│  ─────────────────────────────────────────                 │
│  1678886400000      {"task_id": 101, ...}                  │
│  1678886460000      {"task_id": 102, ...}                  │
│  1678886520000      {"task_id": 103, ...}                  │
│  ...                                                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ 批量弹出到期任务
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Lua 脚本 (原子操作)                       │
│                                                             │
│  1. ZRANGEBYSCORE 获取所有 score <= now 的成员              │
│  2. ZREM 原子删除这些成员                                   │
│  3. 返回被删除的成员列表                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 安全特性

✅ **参数校验**：校验 `execute_at` 为非负数字，`task_json` 为合法 JSON  
✅ **Lua 原子操作**：避免并发竞态，保证弹出和删除的原子性  
✅ **类型安全**：限制 `limit` 在 1-1000 之间  
✅ **异常捕获**：完善的日志记录和错误处理  

---

## 最佳实践

- ✅ 延迟任务使用 JSON 格式存储
- ✅ 批量弹出任务时限制数量（避免内存溢出）
- ✅ 定期检查 `get_earliest_score()` 优化轮询频率
- ✅ 任务处理失败时记录日志，支持重试机制

---

## 📖 相关文档

- [MySQL 连接器](./MySQL连接器文档.md)
- [MongoDB 连接器](./MongoDB连接器文档.md)
- [数据库连接器总览](./数据库连接器总览.md)

---

**最后更新**: 2026-04-15
