# MongoDB 连接器文档

## 功能概述

MongoDB 连接器提供异步客户端管理，支持参数化 CRUD 操作，防止 NoSQL 注入，强制使用安全的操作符。

---

## 核心方法

| 方法 | 用途 | 参数说明 | 返回值 | 示例 |
|------|------|---------|--------|------|
| `init_mongodb()` | 初始化 MongoDB 客户端 | 无 | `None` | 应用启动时调用 |
| `close_mongodb()` | 关闭 MongoDB 客户端 | 无 | `None` | 应用关闭时调用 |
| `get_mongodb()` | 获取 MongoDB 数据库对象 | 无 | `AsyncIOMotorDatabase` | 内部使用 |
| `get_mongo_client()` | 获取 MongoDB 客户端实例 | 无 | `AsyncIOMotorClient` | 高级操作 |
| `get_collection(collection_name)` | 获取集合对象 | `collection_name`: 集合名 | `AsyncIOMotorCollection` | 内部使用 |
| `mongo_find(collection, query, projection, sort, page, page_size)` | 分页查询多条 | `collection`: 集合名<br>`query`: 查询条件<br>`projection`: 投影（字段选择）<br>`sort`: 排序<br>`page`: 页码<br>`page_size`: 每页条数 | `Tuple[List[dict], int]` | 查询用户列表 |
| `mongo_find_one(collection, query, projection)` | 查询单条 | `collection`: 集合名<br>`query`: 查询条件<br>`projection`: 投影 | `Optional[dict]` | 查询单个用户 |
| `mongo_insert_one(collection, document)` | 插入单条 | `collection`: 集合名<br>`document`: 文档数据 | `str` (插入的 ID) | 插入新用户 |
| `mongo_update_one(collection, query, update, upsert)` | 更新单条 | `collection`: 集合名<br>`query`: 查询条件<br>`update`: 更新数据（必须包含 `$set`）<br>`upsert`: 不存在时是否插入 | `int` (修改数量) | 更新用户信息 |
| `mongo_delete_one(collection, query)` | 删除单条 | `collection`: 集合名<br>`query`: 查询条件 | `int` (删除数量) | 删除用户 |

---

## 使用示例

### 1. 分页查询

```python
from db.mongodb import mongo_find

# 查询所有活跃用户
users, total = await mongo_find(
    collection_name="users",
    query={"status": "active"},
    projection={"_id": 1, "name": 1, "email": 1},  # 只返回指定字段
    sort=[("created_at", -1)],  # 按创建时间降序
    page=1,
    page_size=20
)

# 返回结果
# users: [
#   {"_id": ObjectId("..."), "name": "Alice", "email": "alice@example.com"},
#   ...
# ]
# total: 150
```

### 2. 查询单条数据

```python
from db.mongodb import mongo_find_one

# 查询指定用户
user = await mongo_find_one(
    collection_name="users",
    query={"_id": ObjectId("507f1f77bcf86cd799439011")},
    projection={"name": 1, "email": 1, "profile": 1}
)

# 返回结果
# {
#   "_id": ObjectId("..."),
#   "name": "Alice",
#   "email": "alice@example.com",
#   "profile": {"age": 25, "level": 5}
# }
```

### 3. 插入文档

```python
from db.mongodb import mongo_insert_one
from bson import ObjectId

# 插入新用户
user_id = await mongo_insert_one(
    collection_name="users",
    document={
        "name": "Charlie",
        "email": "charlie@example.com",
        "status": "active",
        "profile": {
            "age": 28,
            "level": 1,
            "tags": ["new_user", "premium"]
        },
        "created_at": datetime.utcnow()
    }
)

# 返回插入的 ID（字符串格式）
# "507f1f77bcf86cd799439012"
```

### 4. 更新文档

```python
from db.mongodb import mongo_update_one

# 更新用户信息（必须使用 $set 操作符）
affected = await mongo_update_one(
    collection_name="users",
    query={"_id": ObjectId("507f1f77bcf86cd799439011")},
    update={
        "$set": {
            "name": "Alice Zhang",
            "email": "alice.zhang@example.com"
        },
        "$inc": {
            "profile.level": 1  # 等级 +1
        }
    }
)

# 返回修改数量
# 1
```

### 5. 删除文档

```python
from db.mongodb import mongo_delete_one

# 删除用户（禁止空查询，防止误删全表）
deleted = await mongo_delete_one(
    collection_name="users",
    query={"_id": ObjectId("507f1f77bcf86cd799439011")}
)

# 返回删除数量
# 1
```

---

## 查询条件示例

### 简单条件
```python
# 等于
query = {"status": "active"}

# 数字比较
query = {"age": {"$gt": 18, "$lte": 65}}

# IN 查询
query = {"role": {"$in": ["admin", "editor"]}}

# 正则匹配
query = {"name": {"$regex": "^A", "$options": "i"}}
```

### 复杂条件
```python
# AND 条件
query = {
    "status": "active",
    "age": {"$gt": 18}
}

# OR 条件
query = {
    "$or": [
        {"role": "admin"},
        {"level": {"$gte": 5}}
    ]
}
```

---

## 安全特性

✅ **禁止危险操作符**：`$where`, `$expr`, `$regex`（防止 NoSQL 注入）  
✅ **强制 $set 操作符**：防止全文档覆盖  
✅ **禁止空查询删除**：防止误删全表  
✅ **递归校验**：深度检查查询条件的安全性  
✅ **异常捕获**：完善的日志记录和错误处理  

---

## 最佳实践

- ✅ 查询时使用 `projection` 限制返回字段（减少网络传输）
- ✅ 更新操作必须使用 `$set` 等操作符
- ✅ 删除操作必须提供查询条件（禁止空查询）
- ✅ 复杂查询使用聚合管道（`aggregate`）

---

## 📖 相关文档

- [MySQL 连接器](./MySQL连接器文档.md)
- [Redis 连接器](./Redis连接器文档.md)
- [数据库连接器总览](./数据库连接器总览.md)

---

**最后更新**: 2026-04-15
