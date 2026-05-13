# API 手册

> 前端开发唯一需要的 API 文档。所有端点、请求格式、返回示例、权限要求。
> Base URL: `http://localhost:8000`

---

## 一、认证

### 登录

```
POST /auth/login
Content-Type: application/json

请求:
  {"username": "admin1", "password": "admin123"}

返回 200:
  {
    "token": "eyJhbGci...",
    "user": {
      "id": 1,
      "username": "admin1",
      "display_name": "超级管理员",
      "permissions": ["user:manage", "crawler:task:read", ...]
    }
  }

返回 401:
  {"error": "用户名或密码错误", "code": "UNAUTHORIZED"}
```

**后续所有请求**带 `Authorization: Bearer <token>` 头部。

### 获取当前用户

```
GET /auth/me
Authorization: Bearer <token>

返回: 同登录返回的 user 对象
```

---

## 二、用户端（普通用户）

> 只需 JWT，不需要管理端权限。

| 方法 | 路径 | 参数 | 说明 |
|------|------|------|------|
| `GET` | `/user/filter-packet` | — | 筛选器选项（类型列表 + 评分区间） |
| `GET` | `/user/movies` | `?type_num=11&interval_id=100:90&page=1&page_size=20` | 电影列表 |
| `GET` | `/user/movies/<id>` | — | 电影详情（含演职人员、评分、类型、地区） |
| `GET` | `/user/genres` | — | 所有类型 |
| `GET` | `/user/genre-stats` | — | 各类型电影数 |
| `GET` | `/user/reviews` | `?movie_id=1&page=1` | 长评列表 |
| `GET` | `/user/comments` | `?movie_id=1&rating=5&page=1` | 短评列表（可按评分过滤） |

---

## 三、管理端 — 仪表盘

### 系统实时状态

```
GET /admin/status
需要: system:monitor

返回 200:
{
  "puller_state": "running",
  "puller_fetched": 21,
  "queue_size": 0,
  "queue_saturation": 0.0,
  "worker_alive": 5, "worker_busy": 0, "worker_dead": 0, "worker_stuck": 0,
  "cpu_percent": 18.5,
  "memory_percent": 84.9,
  "db_mysql": true, "db_redis": true, "db_mongodb": true,
  "cookie_saved_at": "2026-05-10T12:00:00+08:00",
  "cookie_has_dbcl2": true,
  "cookie_valid": true,
  "proxy": {"alive": 3, "suspicious": 1, "banned": 2, "total": 6}
}
```

### 任务队列快照

```
GET /admin/tasks/queue
需要: system:monitor

返回 200:
{
  "redis_size": 5,          // Redis ZSET 中排队的任务数
  "queue_size": 2,          // asyncio.Queue 中待领取的任务数
  "worker_busy": 3,         // 正在执行的 Worker 数
  "worker_idle": 2           // 空闲 Worker 数
}

GET /admin/tasks/queue?details=1   ← 带详情
{
  // 上面 4 个字段加上以下 3 个:
  "redis_tasks": [
    {"type": "movie_crawl", "task_id": 123, "admin_id": 1, "type_num": 11, "interval_id": "100:90", "label": "补充ID: type=11 interval=100:90"},
    {"type": "movie_scrape_task", "task_id": 124, "admin_id": 1, "douban_id": "1292052", "cookie_id": "main", "proxy_key": "1.2.3.4:3128", "label": "爬取影片: 肖申克的救赎"}
  ],
  "queue_tasks": [
    {"type": "movie_scrape_task", "task_id": 125, "admin_id": 1, "douban_id": "1292064", "label": "爬取影片: 楚门的世界"}
  ],
  "in_flight": [
    {"type": "movie_scrape_task", "task_id": 124, "admin_id": 1, "worker_id": 0, "busy_seconds": 12.3, "stage": "📡 正在请求详情页 (第1次): https://..."},
    {"type": "review_body_crawl", "task_id": 126, "admin_id": 1, "worker_id": 1, "busy_seconds": 5.1, "stage": "📝 正在解析长评正文"}
  ]
}
```

`in_flight` 中的 `stage` 字段来自 Crawler 实时上报的进度事件，同时通过 WebSocket 推送给提交者。`busy_seconds` 是该 Worker 从领取任务开始的已用时长（含 jitter sleep）。

### 日志查询

```
GET /admin/logs?level=ERROR&limit=20
需要: system:monitor
```

### 限流事件

```
GET /admin/rate-limit-events?minutes=60
需要: system:monitor
```

---

## 四、管理端 — 任务

### 权限码速查

| 权限码 | 可访问的端点 |
|--------|------|
| `crawler:task:read` | 查看爬取进度 / 任务历史 / douban-ids 列表 |
| `crawler:task:write` | 提交任务 / 添加 douban-id / 认领 douban-id |
| `crawler:failure:manage` | 失败任务认领/释放/解决/重爬 |
| `movie:read` | 查看电影列表/详情 |
| `movie:manage` | 编辑基本信息 / 上下架 / 演职人员 / 类型 / 地区 / 评分 |
| `comment:read` | 查看评论列表 |
| `comment:manage` | 上架/下架评论 |
| `user:manage` | 用户管理 |
| `system:monitor` | 系统监控（status/queue/logs/限流/代理/Cookie） |

### 提交爬取任务

```
POST /admin/tasks
需要: crawler:task:write

// movie_crawl — 对某分类-评分批量获取 douban_id
{"type": "movie_crawl", "type_num": 11, "interval_id": "100:90"}

// movie_scrape_task — 爬取单部电影详情（不含演职人员，系统自动创建子任务补爬）
{"type": "movie_scrape_task", "douban_id": "1292052", "cookie_id": "main", "proxy_key": "1.2.3.4:3128"}
  → 自动链式: 详情页入库后自动 ZADD director_crawl 子任务
  → 管理员可在 task-history 看到两个独立条目（父：movie_scrape_task / 子：director_crawl）

// director_crawl — 独立补爬演职人员（失败管理"重爬"也使用此类型）
{"type": "director_crawl", "douban_id": "1292052", "movie_id": 42}
  注意: movie_scrape_task 自动注入此任务，管理员通常无需手动提交
  场景: 从失败管理点"重爬"时自动构造此类型

// review_crawl — 顺延采集长评摘要（每次取5条，自动从已有数量处顺延）
{"type": "review_crawl", "subject_id": "1292052", "movie_id": 42}
  可选: "cookie_id": "main", "proxy_key": "1.2.3.4:3128"   ← 显式指定身份，不传则游客+代理池轮转

// review_body_crawl — 正文爬取批次模式（取 movie_review 中所有 pending 条目，串行处理）
{"type": "review_body_crawl", "douban_id": "1292052", "movie_id": 42}
  可选: "cookie_id": "main", "proxy_key": "1.2.3.4:3128"   ← 显式指定身份
  说明: v3版本取消max_count参数，改为取同一电影所有pending条目串行处理

// comment_crawl — 爬取短评（一次到位，不需要解耦）
{"type": "comment_crawl", "subject_id": "1292052", "movie_id": 42, "comment_pages": 5}
  可选: "cookie_id": "main", "proxy_key": "1.2.3.4:3128"   ← 显式指定身份

返回 201:
{"task_id": 9876543210, "type": "movie_crawl", "execute_at": 1778300000.0, "message": "movie_crawl 任务已提交"}
```

### 爬取进度

```
GET /admin/tasks?type_num=11&page=1&page_size=100
需要: crawler:task:read

返回 200:
{
  "items": [{
    "type_num": 11, "type_name": "剧情", "interval_id": "100:90",
    "douban_total": 50,
    "crawled_count": 50,       // 豆瓣 ID 获取进度（douban_ids 表入库数）
    "scraped_count": 42,       // 电影详情爬取进度（movies 表入库数）
    "completed_count": 38,     // 演职人员爬取进度（movie_credits 表关联数）
    "done": true               // crawled_count >= douban_total
  }],
  "page": 1, "page_size": 100, "total": 5
}
```

三个指标语义：
- `crawled_count` — 豆瓣榜单 ID 已全部获取（movie_crawl 完成）
- `scraped_count` — 电影基础信息已入库（movie_scrape_task 完成）
- `completed_count` — 演职人员也已入库（director_crawl 完成）
- `done` — 仅指 ID 获取完成（crawled_count >= douban_total）

### 任务历史

```
GET /admin/task-history?admin_id=1&task_type=movie_crawl&status=running&keyword=肖&since=2026-05-01&until=2026-05-11&page=1&page_size=20
需要: crawler:task:read

状态: submitted → running → done / failed
message: running 期间实时更新为当前进度描述（如 "📡 正在请求详情页..."）

GET /admin/task-history/<id>    单条详情（含关联失败记录）
需要: crawler:task:read
```

---

## 五、管理端 — douban_id 资产

```
GET /admin/douban-ids?is_acquired=0&keyword=肖&page=1&page_size=20
  需要: crawler:task:read
  is_scraped 参数: 默认 0（只返回未爬取的已认领列表），传 1 查已爬完的，传 -1 查全部
  admin_id=me 参数可选 — 自动过滤当前管理员认领的 ID

返回 200:
{
  "items": [{
    "douban_id":"1292052","title":"肖申克的救赎",
    "is_acquired":0, "is_scraped":0,
    "admin_id": null, "claimed_by_name": null,   ← 认领人信息
    ...
  }],
  "total": 50, "page": 1, "page_size": 20
}

POST /admin/douban-ids
  需要: crawler:task:write
  {"douban_id": "1292052", "title": "肖申克的救赎",
   "type_num": 11, "interval_id": "100:90"}    ← type_num 和 interval_id 必填，需合法

POST /admin/douban-ids/<id>/acquire
  需要: crawler:task:write
  认领原子操作 — 返回 200 成功 / 409 已被别人抢走或已爬取完成
  约束：is_scraped=1 的已完成 ID 不可认领

POST /admin/douban-ids/<id>/release
  需要: crawler:task:write
  释放认领（仅限本人认领且未爬取完成的 ID） — 返回 200 / 409 不是自己认领的或已爬取完成
  约束：is_scraped=1 的已完成 ID 不可释放
```

---

## 六、管理端 — 失败管理

```
GET /admin/failures?status=pending&page=1&page_size=20
需要: crawler:failure:manage

GET /admin/failures/<id>               单条详情
POST /admin/failures/<id>/claim         认领（原子）
POST /admin/failures/<id>/release       放弃认领
POST /admin/failures/<id>/resolve       标记已解决
POST /admin/failures/<id>/retry         重爬 → 投回 Redis ZSET
```

---

## 七、管理端 — 电影/评论管理

```
电影:
  GET  /admin/movies?keyword=肖&published=1&type_num=11&page=1&page_size=20     [movie:read]
  GET  /admin/movies/<id>                                                              [movie:read]
  PATCH /admin/movies/<id>                                                             [movie:manage]
    {"title": "新标题", "release_year": 2024}   ← 所有字段可选，只更新传入的非 null 字段
  POST /admin/movies/<id>/publish                                                      [movie:manage]
  POST /admin/movies/<id>/unpublish                                                    [movie:manage]
  POST /admin/movies/<id>/credits                                                      [movie:manage]
    {"person_id": 42, "role_type": "director"}
  DELETE /admin/movies/<id>/credits                                                    [movie:manage]
    {"person_id": 42, "role_type": "director"}
  POST /admin/movies/<id>/genres                                                       [movie:manage]
    {"type_num": 11}
  DELETE /admin/movies/<id>/genres/<type_num>                                           [movie:manage]
  POST /admin/movies/<id>/regions                                                      [movie:manage]
    {"region_id": 1}
  DELETE /admin/movies/<id>/regions/<region_id>                                         [movie:manage]
  PUT  /admin/movies/<id>/rating                                                       [movie:manage]
    {"average": 8.5, "count": 120000}

评论:
  GET  /admin/reviews?movie_id=1&page=1                                                 [comment:read]
  POST /admin/reviews/<id>/publish                                                      [comment:manage]
  POST /admin/reviews/<id>/unpublish                                                    [comment:manage]
  GET  /admin/comments?movie_id=1&rating=5&page=1                                       [comment:read]
  POST /admin/comments/<id>/publish                                                     [comment:manage]
  POST /admin/comments/<id>/unpublish                                                   [comment:manage]
```

---

## 八、管理端 — 用户管理

```
GET  /admin/users                                                                      [user:manage]
POST /admin/users
  需要: user:manage
  {"username": "admin_new", "password": "xxx", "display_name": "管理员"}

PATCH /admin/users/<id>
  需要: user:manage
  {"is_active": false}   → 禁用用户（不能登录）
  {"is_active": true}    → 恢复用户
  {"display_name": "新名"}  → 改昵称
  仅更新传入的字段，未传入的字段保持不变
  注意: 不能禁用自己的账号 → 返回 422 + SELF_DISABLE_FORBIDDEN

POST /admin/users/<id>/permissions
  需要: user:manage
  {"permission_codes": ["crawler:task:read", "system:monitor"]}
  // 传空数组 [] = 清空所有权限
```

---

## 九、管理端 — 基础设施

> 全部端点需 `system:monitor` 权限

### 代理池

```
GET /admin/proxies

返回 200:
{
  "proxies": [
    {"host": "1.2.3.4", "port": 3128, "region": "CN", "source": "admin",
     "is_alive": true, "success_rate": 0.85, "avg_latency_ms": 320}
  ],
  "stats": {"total": 6, "alive": 3, "suspicious": 1, "banned": 2}
}
```

```
POST /admin/proxies
Content-Type: application/json

{"host": "1.2.3.4", "port": 3128, "region": "CN"}

返回 201:
{"success": true, "key": "1.2.3.4:3128"}

返回 409:
{"error": "代理已存在或在黑名单中"}
```

```
DELETE /admin/proxies/<host>/<port>

返回 200:
{"success": true, "key": "1.2.3.4:3128"}

返回 404:
{"error": "代理不在池中"}
```

```
POST /admin/proxies/health-check

触发全量代理验证（请求 httpbin.org/ip），返回各代理验证结果。
返回 200: {"alive": [...], "dead": [...], "duration_seconds": 12.3}
```

### Cookie 多账号管理

> CookieManager 管理多个豆瓣账号的登录态，支持按 region 自动匹配代理。
> 账号存储目录：`data/cookies/`（metadata.json + 各账号 JSON 文件）。
> 首次启动时自动检测旧版 `data/douban_storage.json` 并迁移到 `data/cookies/account_main.json`。

```
GET /admin/cookies

列出所有 Cookie 账号及其状态。

返回 200:
{
  "items": [
    {
      "id": "main",
      "label": "主账号",
      "allowed_regions": ["CN"],
      "dbcl2_preview": "abc12345...",
      "saved_at": "2026-05-10T12:00:00+08:00",
      "state": "active",          // active / suspicious / banned
      "last_used_at": 1778300000.0,
      "fail_count": 0,
      "success_count": 42
    }
  ],
  "stats": {
    "total": 1,
    "active": 1,
    "suspicious": 0,
    "banned": 0,
    "by_region": {"CN": 1}
  }
}
```

```
POST /admin/cookies
Content-Type: application/json

{
  "dbcl2": "abc123...",            // 必填，豆瓣登录 Cookie
  "allowed_regions": ["CN"],       // 必填，该账号允许使用的地区
  "bid": "def456",                 // 可选，豆瓣 bid Cookie
  "label": "主账号"                 // 可选，友好标签
}

返回 201:
{"success": true, "account_id": "main"}

返回 400:
{"error": "dbcl2 不能为空"}
{"error": "allowed_regions 必须是非空数组，如 [\"CN\"]"}
```

```
DELETE /admin/cookies/<account_id>

删除指定 Cookie 账号（同时清理 JSON 文件）。

返回 200:
{"success": true, "message": "账号 main 已删除"}

返回 404:
{"error": "账号不存在", "code": "NOT_FOUND"}
```

```
POST /admin/cookies/<account_id>/ban

手动封禁 — 账号状态改为 banned，爬虫不再使用此账号。

返回 200:
{"success": true, "message": "账号 main 已封禁"}
```

```
POST /admin/cookies/<account_id>/unban

恢复封禁 — 账号状态改回 active。

返回 200:
{"success": true, "message": "账号 main 已恢复"}
```

```
GET /admin/cookies/status

汇总状态（简版，适合仪表盘展示）。

返回 200:
{
  "stats": {"total": 1, "active": 1, "suspicious": 0, "banned": 0, "by_region": {"CN": 1}},
  "accounts": [...],           // 同 GET /admin/cookies 的 items
  "has_dbcl2": true,
  "cookie_valid": true
}
```

```
POST /admin/cookies/replace
Content-Type: application/json

{"dbcl2": "xxx", "bid": "yyy"}

兼容旧版单账号模式，内部委托 CookieManager 写入 account_id="main"。
等价于 POST /admin/cookies {"dbcl2":"xxx","allowed_regions":["CN"],"bid":"yyy","label":"主账号","account_id":"main"}

返回 200:
{"success": true, "account_id": "main"}
```

### 账号状态机

```
active ──→ fail_count >= 2 ──→ suspicious ──→ 再失败 ──→ banned
                                   │
                                   └── 成功 ──→ active（自动恢复）
banned ──→ POST .../unban ──→ active（管理员手动恢复）
```

状态转换由 `CookieManager` 自动跟踪（每次爬虫使用后 `report_success` / `report_failure`），管理员也可通过 ban/unban 端点手动干预。

### 身份绑定说明

创建 `movie_scrape_task` 时可指定 `cookie_id` 和 `proxy_key`：

```json
POST /admin/tasks
{"type": "movie_scrape_task", "douban_id": "1292052", "cookie_id": "main", "proxy_key": "1.2.3.4:3128"}
```

Crawler 引擎自动校验 `account.allowed_regions` 是否包含 `proxy.region`：
- 允许 → 使用该账号的 storage_state 创建 Playwright context，通过该代理发请求
- 不匹配 → 降级为游客模式（日志告警，不阻断任务）

---

## 十、WebSocket 通知

> 实时推送任务执行事件。前端通过 `/ws/notifications?token=<JWT>` 建立单条长连接。
> 不需要管理端 REST 权限码（JWT 认证即够，推送时按 admin_id 路由）。

### 连接方式

```
ws://localhost:8000/ws/notifications?token=<JWT>
```

- 连接建立后后端自动根据 JWT 解析 `admin_id`
- 客户端每 30s 发送 `"ping"` 保持连接，后端回复 `"pong"`
- 断开后前端指数退避重连（1s → 2s → 4s → 8s → max 30s）

### 推送消息格式

#### task_progress — 任务阶段更新

当 Crawler 内部阶段变更时推送给**提交者**。

```json
{
  "type": "task_progress",
  "task_id": 9876543210,
  "stage": "💾 正在写入电影基础信息...",
  "timestamp": 1778300000.0
}
```

#### task_success — 任务执行成功

推送给**提交者**。

```json
{
  "type": "task_success",
  "task_id": 9876543210,
  "worker_id": 3,
  "task_type": "movie_scrape_task",
  "timestamp": 1778300000.0
}
```

#### task_failure — 任务执行失败

推送给**提交者**。

```json
{
  "type": "task_failure",
  "event_type": "failure",
  "task": "{\"id\":9876543210,\"type\":\"movie_scrape_task\",\"douban_id\":\"1292052\",\"admin_id\":1,...}",
  "reason": "请求详情页超时: https://movie.douban.com/subject/1292052/",
  "timestamp": 1778300000.0
}
```

`task` JSON 字符串解析后的字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | number | snowflake task_id |
| `type` | string | 任务类型（6 种，同任务提交） |
| `admin_id` | number | 提交人 user_id |
| `douban_id` | string | 豆瓣电影 ID（统一字段，review_crawl/comment_crawl 同） |
| `movie_id` | number | 可选，本地 MySQL movie_id |
| `type_num` | number | 可选，仅 movie_crawl |
| `interval_id` | string | 可选，仅 movie_crawl |

#### system_status — 仪表盘广播（全体管理员）

Monitor 每 10s 广播给所有连接的管理员，内容同 `GET /admin/status`。

```json
{
  "type": "system_status",
  "puller_state": "running",
  "puller_fetched": 21,
  "worker_alive": 5,
  "worker_busy": 0,
  "queue_size": 0,
  "queue_saturation": 0.0,
  "cpu_percent": 18.5,
  "memory_percent": 84.9,
  "db_mysql": true,
  "db_redis": true,
  "db_mongodb": true,
  "cookie_valid": true,
  "proxy": {"alive": 3, "suspicious": 1, "banned": 2, "total": 6}
}
```

### 消息路由规则

| 消息类型 | 路由目标 | 推送时机 |
|---------|---------|---------|
| `task_progress` | 单播 → 该任务的 `admin_id` | Crawler 阶段变更（约 3~5 次/任务） |
| `task_success` | 单播 → 该任务的 `admin_id` | 任务正常结束 |
| `task_failure` | 单播 → 该任务的 `admin_id` | 任务抛异常 |
| `system_status` | 广播 → 全体管理员 | 每 10s |

---

## 十一、状态码约定

| 状态码 | 含义 | 常见场景 |
|:--:|------|------|
| 200 | 成功 | GET/POST 正常返回 |
| 201 | 创建成功 | POST /admin/tasks, POST /admin/users |
| 400 | 请求参数错误 | JSON 格式错误、缺少必填字段、不支持的任务类型 |
| 401 | 未登录 | token 缺失/过期/用户被禁用 |
| 403 | 无权限 | `@require_permission` 拒绝 |
| 404 | 不存在 | 单条查询无结果 |
| 409 | 冲突 | 认领已被抢走、代理已存在 |
| 422 | 语义错误 | 自己禁用自己、请求语义违反业务规则 |
| 500 | 服务端错误 | 数据库写入失败等 |
