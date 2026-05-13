# MySQL 连接器文档

## 功能概述

MySQL 连接器提供异步连接池管理，支持参数化查询（防止 SQL 注入）、分页查询、参数校验等安全机制。

---

## 核心方法

| 方法 | 用途 | 参数说明 | 返回值 | 示例 |
|------|------|---------|--------|------|
| `init_mysql()` | 初始化 MySQL 连接池 | 无 | `None` | 应用启动时调用 |
| `close_mysql()` | 关闭 MySQL 连接池 | 无 | `None` | 应用关闭时调用 |
| `get_mysql_pool()` | 获取连接池实例 | 无 | `Pool` | 内部使用 |
| `execute_query(sql, args)` | 执行查询（返回多行） | `sql`: SQL 语句<br>`args`: 参数元组 | `List[dict]` | 查询用户列表 |
| `execute_one(sql, args)` | 执行查询（返回单行） | `sql`: SQL 语句<br>`args`: 参数元组 | `Optional[dict]` | 查询单个用户 |
| `execute_update(sql, args)` | 执行更新（INSERT/UPDATE/DELETE） | `sql`: SQL 语句<br>`args`: 参数元组 | `int` (影响行数) | 更新用户信息 |
| `execute_insert(sql, args)` | 执行插入（返回自增ID） | `sql`: SQL 语句<br>`args`: 参数元组 | `int` (自增ID) | 插入新用户 |
| `execute_paginated_query(sql, args, page, page_size)` | 分页查询 | `sql`: 基础查询SQL<br>`args`: 参数元组<br>`page`: 页码<br>`page_size`: 每页条数 | `Tuple[List[dict], int]` | 分页获取用户列表 |

---

## 使用示例

### 1. 查询多行数据

```python
from db.mysql import execute_query

# 查询所有活跃用户
sql = "SELECT id, name, email FROM users WHERE status = %s"
args = ("active",)
users = await execute_query(sql, args)

# 返回结果
# [
#   {"id": 1, "name": "Alice", "email": "alice@example.com"},
#   {"id": 2, "name": "Bob", "email": "bob@example.com"}
# ]
```

### 2. 查询单行数据

```python
from db.mysql import execute_one

# 查询指定用户
sql = "SELECT * FROM users WHERE id = %s"
args = (123,)
user = await execute_one(sql, args)

# 返回结果
# {"id": 123, "name": "Alice", "email": "alice@example.com", "status": "active"}
```

### 3. 执行更新操作

```python
from db.mysql import execute_update

# 更新用户信息
sql = "UPDATE users SET name = %s, email = %s WHERE id = %s"
args = ("Alice Zhang", "alice.zhang@example.com", 123)
affected = await execute_update(sql, args)

# 返回影响行数
# 1
```

### 4. 执行插入操作

```python
from db.mysql import execute_insert

# 插入新用户
sql = "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)"
args = ("Charlie", "charlie@example.com", "hashed_password")
user_id = await execute_insert(sql, args)

# 返回自增主键 ID
# 124
```

### 5. 分页查询

```python
from db.mysql import execute_paginated_query

# 分页查询用户列表
sql = "SELECT id, name, email FROM users WHERE status = %s ORDER BY created_at DESC"
args = ("active",)
users, total = await execute_paginated_query(
    sql=sql,
    args=args,
    page=1,
    page_size=20
)

# 返回结果
# users: [list of 20 users]
# total: 150 (总用户数)
```

---

## 安全特性

✅ **参数化查询**：强制使用 `%s` 占位符，禁止 SQL 拼接  
✅ **参数校验**：过滤恶意内容（如 `UNION`, `DROP`, `;` 等）  
✅ **连接池复用**：提升性能，避免频繁创建连接  
✅ **异常捕获**：完善的日志记录和错误处理  

---

## 最佳实践

- ✅ 使用 `execute_query()` 和 `execute_one()` 替代手写 SQL
- ✅ 分页查询使用 `execute_paginated_query()`（自动处理 LIMIT/OFFSET）
- ✅ 插入操作使用 `execute_insert()` 获取自增 ID
- ✅ 更新操作使用 `execute_update()` 检查影响行数

---

## 📖 相关文档

- [Redis 连接器](./Redis连接器文档.md)
- [MongoDB 连接器](./MongoDB连接器文档.md)
- [数据库连接器总览](./数据库连接器总览.md)

---

**最后更新**: 2026-04-15
