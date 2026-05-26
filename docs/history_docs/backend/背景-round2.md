# Crawler 包与三层架构 — Round 2 对话总结

> 时间：2026-04-28
> 范围：数据库重构 → 三层架构搭建 → Crawler 包设计 → Playwright 迁移决策

---

## 一、数据库层

### 1.1 表结构调整

**决策**：将 `movie_directors` + `movie_actors` 合并为 `movie_credits(movie_id, person_id, role_type)`，三元组联合主键。

**原因**：原两张表无法优雅处理「自导自演」场景。同一个人对同一部电影可以既导又演，加上 `role_type` 才能保证唯一。

**设计选择**：
- `role_type` 使用 `VARCHAR(20)`（而非 ENUM），后端 Python 枚举传入
- 初期仅设计 `'director'` 和 `'actor'` 两种角色
- 外键类型必须与父表严格一致（`bigint` 有符号，不能是 `BIGINT UNSIGNED`）

**最终 8 张业务表**：movies / people / genres / regions / movie_ratings / movie_genres / movie_regions / movie_credits

> **2026-05-04 更新**：当前 18 张表。新增了 `crawl_progress`、`task_failures`、5 张 `_history`、`users`、`permissions`、`user_permissions`。`genres` 表已删除（合并进 `crawl_progress`）。

### 1.2 模拟数据注入

种子数据：5 部电影，14 人，6 类型，2 地区，完整多对多关联。

**关键经验**：
- `aiomysql` 参数化查询不识别 Python `dict` 和 `date` 类型 → 需 `json.dumps()` 和 `str(date)` 转字符串
- 使用"名字→ID"映射表管理动态生成的自增主键
- `VALUES(col)` 语法在 MySQL 8.0.20+ 已弃用 → 改用 `AS alias`

### 1.3 MongoDB 评论存储

电影评论不存 MySQL，用 MongoDB `reviews` 集合。文档结构：

```json
{
  "movie_id": 2,
  "douban_subject_id": "1292052",
  "author": "影**张",       // 昵称脱敏：首尾字符保留，中间 * 掩码
  "rating": 4.5,
  "content": "...",
  "likes": 1234,
  "crawled_at": "2026-04-28T12:00:00Z"
}
```

---

## 二、三层架构

### 2.1 整体分层

```
请求/调用方
    │
service 层（MovieService）   ← 业务逻辑封装、复合查询编排、数据转换
    │
models 层（Pydantic）        ← 数据契约、类型校验、序列化
    │
db 层（DatabaseLayer）       ← 参数化查询、连接池管理（已有）
```

### 2.2 Models 层 — 10 个 Pydantic 模型

| 模型 | 映射 | 用途 |
|------|------|------|
| `MovieCreate` | movies | 创建入参，不含 id |
| `MovieUpdate` | movies | 更新入参，全部可选 |
| `MovieRead` | movies | 读出结果 |
| `PeopleRead` | people | 人员，`created_at` 设为 Optional（聚合查询不一定取到） |
| `GenreRead` | genres | 类型字典 |
| `RegionRead` | regions | 地区字典 |
| `RatingRead` | movie_ratings | 评分，`distribution` 通过 `field_validator` 自动处理 JSON→dict |
| `RatingCreate` | movie_ratings | 评分入参 |
| `CreditRead` | movie_credits | 角色关联 + JOIN people 后的 `person_name` |
| `MovieDetail` | 聚合 | movie + rating + directors + actors + genres |
| `GenreStat` | 统计 | 类型名 + 电影数 + 平均分 |

### 2.3 Service 层 — 17 个业务方法

**字典表**：`list_genres()` / `list_regions()`

**CRUD**：`create_movie()` / `get_movie()` / `update_movie()`（只更新非 None 字段）/ `delete_movie()`

**评分**：`set_rating()`（幂等 INSERT ON DUPLICATE）/ `get_rating()`

**关联**：`add_credit()` / `remove_credit()` / `add_genre_to_movie()` / `remove_genre_from_movie()`

**复合查询**（核心价值）：
- `get_movie_detail(id)` — 4 次查询拼装聚合视图（方案 A：多次查询，非大 JOIN）
- `search_movies(title_keyword, genre_id, page, page_size)` — 参数化 LIKE + 子查询
- `get_movies_by_director(person_id)` — JOIN movie_credits
- `get_credits_by_person(person_id)` — JOIN people

**统计**：`get_genre_stats()` — GROUP BY + AVG

### 2.4 MovieService 的 N+1 防护

| 场景 | 策略 |
|------|------|
| 单条 `get_movie_detail()` | 4 次查询拼装，可接受 |
| 批量列表 | 方案 B：拆分 2~3 次批量查询 + Python 层按 movie_id 分组映射 |

---

## 三、Crawler 包设计

### 3.1 包结构

```
crawler/
├── __init__.py           ← execute(task_str) 入口，按 type 分发
├── fetcher.py            ← 核心下载器（aiohttp → Playwright）
├── proxy.py              ← IP 代理池全生命周期管理
├── proxy_fetcher.py      ← 免费代理供给源 + 付费API存根
├── ua.py                 ← UA 轮换（Playwright 方案中删除）
├── parser.py             ← 豆瓣 HTML 解析器
├── storage.py            ← 持久化（MySQL MovieService + MongoDB 评论）
└── failure_service.py    ← 失败记录到 MySQL task_failures
```

### 3.2 两种任务类型

```
type = "movie_crawl"
  任务 JSON: {id, type, url, subject_id, admin_id, created_at}
  流程: fetcher → parser.parse_movie() → storage.save_movie()
  写入: MySQL (8 张表 via MovieService)

type = "review_crawl"
  任务 JSON: {id, type, url, subject_id, movie_id, admin_id, created_at}
  流程: fetcher → parser.parse_reviews() → storage.save_reviews()
  写入: MongoDB (reviews 集合)
```

### 3.3 IP 代理池 — 完整生命周期

**状态机**：

```
UNKNOWN → ALIVE ↔ SUSPICIOUS → BANNED
              ↑ 再次成功          ↑ 连续失败 2 次
```

**代理来源与持久化策略**：

| 来源 | 持久化 | TTL |
|------|:--:|------|
| 免费代理（AUTO） | ❌ 不持久 | 30 分钟 |
| 管理员添加（ADMIN） | ✅ JSON 文件 | 7 天 |
| 封禁代理（BANNED） | ❌ 不持久 | — |

**管理员操作**：
- `POST /admin/proxies` → 添加代理 → 自动校验 → ALIVE 或 BANNED
- `POST /admin/proxies/{ip}/ban` → ALIVE/SUSPICIOUS → BANNED

**启动时序（修正后）**：

```
① load_persisted()          ← 先读 data/proxies.json（管理员历史代理）
   ├── 有效 → ALIVE
   └── TTL 过期 → 丢弃

② 判断池是否为空
   ├── 有代理 → health_check() 异步验证
   └── 空 ────→ fetch_from_paid_api()  ← 付费 API 存根
                   ├── 开发：无 key → 空 → direct_fallback=True → 直连
                   └── 生产：有 key → 待实现
```

### 3.4 免费代理实测结论

10+ 个免费代理全不可用：400 拒绝 / 403 禁止 / 502 上游不通 / timeout 黑洞。

**架构启示**：免费代理在公开列表存活率 < 5%，ProxyPool 状态机天然适配快速轮换模式。开发阶段直连足够。

### 3.5 反向测试数据

```json
data/bad_proxies.json  — 4 种失败模式
16.162.88.123:8080     → 400 Bad Request    代理拒绝请求
43.198.99.209:19035    → 502 Bad Gateway    上游不可达
43.159.28.58:19229     → 403 Forbidden      代理禁止访问
47.94.57.119:80        → timeout 10s        黑洞代理
```

---

## 四、Playwright 迁移决策

### 4.1 决策过程

1. aiohttp 直连 → 返回 JS 验证页（SHA-512 工作量证明），`bid` Cookie 不够
2. requests 同样 → 仍被拦
3. 免费代理全不可用 → 无法通过代理绕过
4. 评估 `selenium` vs `playwright` → 选择 Playwright（async API，与项目一致）
5. **决策：纯 Playwright 方案**

### 4.2 架构影响

**受影响的模块**：

| 模块 | 影响程度 | 变化 |
|------|:--:|------|
| `fetcher.py` | 🔴 重写 | aiohttp → Playwright browser page |
| `ua.py` | 🔴 删除 | 浏览器自带指纹 |
| `worker.py` | 🟡 中等 | WorkerPool → BrowserPool，信号量替代计数 |
| `app.py` | 🟡 中等 | 浏览器生命周期管理 |
| `proxy.py` | 🟢 微调 | 代理通过 `new_context(proxy=...)` 注入 |

**不受影响的模块**：parser / storage / `__init__` / proxy_fetcher / puller / monitor（微调）/ websocket / failure_service / models / services / db

### 4.3 Worker 架构核心变化

```
aiohttp 模式：                        Playwright 模式：
20 个独立 Worker 协程                 1 个 Chromium 浏览器实例
轻量、无状态                          重资源 ~200MB
每个 aiohttp 请求独立                  5 个并发页面（asyncio.Semaphore）
```

**关键不变**：`execute_func: async (task: str) -> None` 签名——回调注入的价值。

### 4.4 资源对比

| 指标 | aiohttp | Playwright |
|------|:------:|:----------:|
| 内存 | ~5MB | ~250MB |
| 并发 | 20 | 5 |
| 首次启动 | 0ms | 500ms~1s |
| 单页耗时 | 0.3~1s | 0.5~2s |
| 吞吐 | ~20 页/s | ~2~10 页/s |

---

## 五、测试现状

### 5.1 已有测试（67 passed）

```
test/crawler/test_proxy.py            37 passed
test/crawler/test_proxy_fetcher.py    13 passed
test/crawler/test_ua.py               4 passed
test/crawler/test_fetcher.py         13 passed
────────────────────────────────────────────
                                      67 passed
```

### 5.2 集成测试（63 passed）

```
test/movie_service_test.py           63 passed
  覆盖：字典表 / CRUD / 搜索 / 聚合详情 / 导演查询 /
        角色查询 / 评分 / 统计 / 写操作 / 边界
```

### 5.3 总测试量

| 分类 | passed |
|------|:-----:|
| crawler 单元测试 | 67 |
| movie_service 集成测试 | 63 |
| **合计** | **130** |

---

## 六、文件清单

### 本轮新增

```
models/movie_models.py          ← 10 个 Pydantic 模型
services/movie_service.py       ← 17 个业务方法
test/movie_service_test.py      ← 63 个断言集成测试

crawler/proxy.py                ← 代理池核心（状态机/锁/JSON持久化）
crawler/proxy_fetcher.py        ← 免费代理供给源 + 付费API存根
crawler/ua.py                   ← UA 轮换（即将删除）
crawler/fetcher.py              ← 核心下载器（aiohttp 版，即将重写）

scripts/adjust_tables.py        ← 表结构调整
scripts/seed_movies.py          ← 模拟数据注入
scripts/clear_data.py           ← 数据清理
scripts/audit_tables.py         ← 表结构审计
scripts/fetch_sample.py         ← 豆瓣抓取测试
scripts/fetch_requests.py       ← requests 版豆瓣测试

utils/douban_test.py            ← 豆瓣代理测试工具
data/proxies.json               ← 5 个占位代理
data/bad_proxies.json           ← 4 个验证失败代理
test/crawler/test_proxy.py      ← 37 个 proxy 测试
test/crawler/test_proxy_fetcher.py ← 13 个 proxy_fetcher 测试
test/crawler/test_ua.py         ← 4 个 UA 测试
test/crawler/test_fetcher.py    ← 13 个 fetcher 测试

docs/playwright-migration.md    ← Playwright 变更记录
docs/背景-round2.md              ← 本文件
```

### 待完成

```
crawler/fetcher.py      （重写为 Playwright 版本）
crawler/parser.py       （豆瓣 HTML 解析器）
crawler/storage.py      （MySQL + MongoDB 写入）
crawler/__init__.py     （execute 入口分发）
crawler/failure_service.py （失败记录）
background/worker.py    （WorkerPool → BrowserPool）
app.py                  （浏览器生命周期 + execute_func 替换）
```

---

## 七、架构原则回顾

| 原则 | 本轮体现 |
|------|----------|
| **回调注入** | Worker 的 `execute_func` 从 aiohttp 换到 Playwright，签名不变 |
| **关注点分离** | fetcher / parser / storage 三层独立，各自可单独测试 |
| **状态枚举** | ProxyStatus(UNKNOWN/ALIVE/SUSPICIOUS/BANNED) 完整状态机 |
| **模块级单例** | ProxyPool 的 init/get 四件套 |
| **类型分发** | `execute()` 按 `task.type` 路由到不同处理函数 |
| **防注入** | 解析结果通过 Pydantic 校验 + 参数化查询 |
| **依赖注入** | MovieService 接收 DatabaseLayer，不 new 实例 |
| **优雅降级** | Fetcher 代理全失败 → direct_fallback → 直连兜底 |
| **数据隔离** | 读操作用种子数据，写操作创建临时记录并在 finally 清理 |
