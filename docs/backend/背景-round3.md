# Crawler 包深化 + 数据库设计审查 + 版本历史 — Round 3 对话总结

> 时间：2026-05-03 ~ 2026-05-05
> 范围：Fetcher 双引擎拆分 → Parser → Storage → 数据库审查重构 → 上下架 → 版本历史表 → 手动事务

---

## 一、Crawler 包 — 从单引擎到双引擎

### 1.1 决策：ApiFetcher + BrowserFetcher

**背景**：旧版只有一个 Playwright `BrowserFetcher`，但 `movie_crawl` 类型走的是 JSON API（`/j/chart/top_list`），不需要浏览器。

**决策**：新增 `ApiFetcher`（aiohttp 轻量客户端），与 `BrowserFetcher`（Playwright）形成双引擎。

| 引擎 | 工具 | 适用场景 | 单次耗时 |
|------|------|------|:--:|
| `ApiFetcher` | aiohttp | JSON API + 非受限页面 | ~0.5s |
| `BrowserFetcher` | Playwright | 受 SHA-512 保护的 HTML | ~3.7s |

**ApiFetcher 实现要点**：
- 懒初始化 `aiohttp.ClientSession`（复用连接池）
- 自动判断 Content-Type：`json` → `json.loads()`，否则 → `str`
- gzip/brotli 解压：`auto_decompress=False` + 手动 `_decompress(raw, encoding)`
- Cookie 注入支持（爬虫登录态）
- 代理轮换 + 直连兜底（与 BrowserFetcher 一致的 ProxyPool 接口）

### 1.2 任务分派矩阵

```
task.type = "movie_crawl"     → ApiFetcher.fetch(JSON API)
                               → parse_movie_list(list)
                               → save_movies(MovieService → MySQL)

task.type = "review_crawl"    → BrowserFetcher.fetch(HTML 列表页)
                               → parse_review_list(html)
                               → foreach review_id:
                                   ApiFetcher.fetch(/j/review/{id}/full)
                                   parse_review_full(json)
                               → save_reviews(MongoDB)

task.type = "comment_crawl"   → BrowserFetcher.fetch(HTML)
                               → parse_comments(html)
                               → save_comments(MongoDB)
```

### 1.3 app.py 切换

```diff
- execute_func=dummy_execute,
+ execute_func=crawler_execute,
```

同时 `init_crawler(browser, movie_service=app.movie_service)` 注入 MovieService。

---

## 二、Parser — 四个纯函数

### 2.1 设计原则

- **Regex 优先**：豆瓣 HTML 结构固定，`re.DOTALL` 比引入 selectolax/BS4 更轻量
- **纯函数**：零外部依赖，输入→输出，无副作用
- **异常契约**：空输入 → `ValueError`

### 2.2 函数清单

| 函数 | 输入 | 输出 | 验证 |
|------|------|------|:--:|
| `parse_movie_list(list)` | `/j/chart/top_list` JSON | `list[dict]` (douban_id, title, score, types, regions, actors...) | 11/11 |
| `parse_review_list(html)` | `/subject/{id}/reviews` HTML | `list[dict]` (review_id, title, author, useful_count, date) — 17 条 | 5/5 |
| `parse_review_full(dict)` | `/j/review/{id}/full` JSON | `dict` (html, text 纯文本, votes) | 5/5 |
| `parse_comments(html)` | `/subject/{id}/comments` HTML | `list[dict]` (comment_id, author, rating, text, date, useful_count) — 20 条 | 7/7 |

**评分映射**：`allstar50→5.0` / `allstar40→4.0` / ... / `allstar05→0.5`

---

## 三、Storage — MySQL + MongoDB 持久化

### 3.1 写入顺序（遵守外键依赖）

```
save_movies() → 逐电影:
  1. 去重: get_movie_by_douban_id(douban_id) → 存在则跳过
  2. create_movie(douban_id, title, ...)       → movies
  3. _find_or_create_person(name, douban_id)   → people
  4. add_credit(movie_id, person_id, "actor")  → movie_credits
  5. _resolve_type_num(type_name)              → crawl_progress（只查不建）
  6. add_genre_to_movie(movie_id, type_num)    → movie_genres
  7. _find_or_create_region(name)              → regions
  8. add_region_to_movie(movie_id, region_id)  → movie_regions
  9. set_rating(score, vote_count)             → movie_ratings（幂等）
```

### 3.2 电影爬取逻辑确认

**API 参数**：
- `/j/chart/top_list?type=11&interval_id=100:90&start=0&limit=20`
- `type` = 豆瓣类型编号（11=剧情, 24=喜剧...）
- `interval_id` = 评分区间（如 `100:90` = 9.0~10.0）
- `limit` 固定 20

**总量 API**：`/j/chart/top_list_count?type=&interval_id=` → `{"playable_count":583, "total":744, ...}`

**分页进度**：`crawl_progress` 表，`crawled` 等价于下次 `start`。每爬一批 `crawled += 20`，`start + 20 > total` 时停止。单批内个别失败不阻塞 cursor 推进。

---

## 四、数据库设计审查 — 三轮 DDL 演进

### 4.1 Round 1：基础修复

| 表 | 操作 | 原因 |
|------|------|------|
| `movies` | +`douban_id VARCHAR(32) UNIQUE` | 同一电影从不同 (type, interval) 爬入时不重复创建 |
| `movies` | -`release_region` | 地区关系由 `movie_regions` N:N 表管理 |
| `movies` | `release_year` → NULL | 部分 API 不返回年份 |
| `crawl_progress` | -`type_name` | 最初设计 `genres` 表覆盖名称 |
| `task_failures` | +`task_id BIGINT` | 从 task JSON 提取 snowflake ID 单独存 |
| `people` | +`UNIQUE(name)` | `_find_or_create_person` 幂等保护 |

### 4.2 Round 2：genres 合并到 crawl_progress

**决策**：删除 `genres` 表，`crawl_progress` 同时承担类型字典 + 爬取进度。

**原因**：`genres` 是 `crawl_progress` 的子集——每个类型必定出现在至少一个 `(type, interval)` 组合中。

| 表 | 操作 |
|------|------|
| `genres` | DROP |
| `crawl_progress` | +`type_name`（补回，它现在是唯一的类型字典） |
| `movie_genres` | `genre_id` → `type_num`（FK 到 genres 已删） |
| `people` | +`douban_id VARCHAR(32) UNIQUE`（从详情页 personage URL 提取） |

**MovieService 适配**：
- `list_genres()` → `SELECT DISTINCT type_num, type_name FROM crawl_progress`
- `add_genre_to_movie(movie_id, type_num)` — 参数从 `genre_id` 变为 `type_num`
- `get_movie_detail()` → JOIN `crawl_progress` 取类型名
- 新增 `get_movie_by_douban_id()` — 按豆瓣 ID 去重

### 4.3 Round 3：上下架 + 版本历史 + 事务

**新增字段**：
- `movies.is_published` — 电影上下架
- `crawl_progress.is_published` — 类型上下架
- MongoDB `reviews/comments.is_published` — 评论上下架

**新增方法**：
- `MovieService.set_movie_published(id, False/True)`
- `MovieService.set_type_published(type_num, interval_id, False/True)`
- `MovieService.list_movies(published_only=True)`
- `MovieService.list_genres(published_only=True)`

---

## 五、版本历史表设计

### 5.1 方案选型

| 方案 | 描述 | 选择 |
|------|------|:--:|
| A 全量快照 | 每表一张 `_history`，复制全部字段 | ❌ |
| B 字段级日志 | 一张表 `data_versions`，`field_name + old_value + new_value` | ❌ |
| C 独立快照表 | 每业务表一张 `_history`，实体 ID + 变更后全量快照 + change_type + changed_by | ✅ |

### 5.2 实现

```sql
movies_history (id, movie_id, douban_id, title, ..., is_published,
                created_at, updated_at,
                change_type, changed_by, changed_at)

people_history (id, person_id, douban_id, name,
                change_type, changed_by, changed_at)

movie_credits_history (id, movie_id, person_id, role_type,
                       change_type, changed_by, changed_at)

movie_regions_history (id, movie_id, region_id,
                       change_type, changed_by, changed_at)

movie_genres_history (id, movie_id, type_num,
                      change_type, changed_by, changed_at)
```

**写入规则**：

| 操作 | 快照内容 | change_type |
|------|------|:--:|
| INSERT | 插入后的完整行 | `create` |
| UPDATE | 更新后的完整行 | `update` |
| DELETE | 删除前的完整行 | `delete` |

**不在版本范围**：`movie_ratings`（统计数据）、`crawl_progress`（内部状态）、`task_failures`（日志）。

---

## 六、Snowflake ID 生成器

```python
# utils/snowflake.py
EPOCH = 2026-01-01  # 1767225600000 ms
MACHINE_BITS = 10    # 0~1023
SEQUENCE_BITS = 12   # 0~4095
```

- 线程安全：`threading.Lock` 保护
- 时钟回拨：< 1s 自旋等待，≥ 1s 抛 RuntimeError
- 模块级单例：`init_snowflake(machine_id=1)` → `generate_id()`

---

## 七、DatabaseLayer → DatabaseLayerV2（手动事务）

### 7.1 问题

旧版 `DatabaseLayer` 每个 CRUD 操作用独立的 `pool.acquire()`，`autocommit=True`。主表写入和 history 写入在两个不同连接上，无法保证原子性。

### 7.2 方案

**决策**：创建 `db/database_v2.py`（基于原 `database.py` 复制修改），保持旧版不动。

**新增组件**：

```
DatabaseLayerV2.transaction()     ← @asynccontextmanager
  ├── pool.acquire()              ← 借连接
  ├── conn.begin()                ← 关闭 autocommit
  ├── yield TransactionContext    ← 同一连接上的 insert/find_one/update/delete
  ├── conn.commit()               ← 正常退出
  └── conn.rollback()             ← 异常退出

TransactionContext
  ├── insert(table, data, return_id=True)
  ├── find_one(table, conditions)
  ├── update(table, conditions, data)
  ├── delete(table, conditions)
  └── execute_raw(sql, params)
  ↑ 所有 SQL 走同一连接 → 同一事务
  ↑ 所有 SQL 走 %s 占位符 → 防注入不变
```

**使用方式（以 create_movie 为例）**：

```python
async with self.db.transaction() as tx:
    mid = await tx.insert("movies", values, return_id=True)
    row = await tx.find_one("movies", {"id": mid})
    await self._write_history("movies", ..., tx=tx)  # ← 传入 tx，走事务内
# 退出 → COMMIT（两写同命运）
```

### 7.3 全部走事务的写方法（10 个）

`create_movie` / `update_movie` / `delete_movie` / `set_movie_published` / `add_credit` / `remove_credit` / `add_genre_to_movie` / `remove_genre_from_movie` / `add_region_to_movie` / `remove_region_from_movie`

### 7.4 文件结构

| 文件 | 状态 |
|------|------|
| `db/database.py` | 保留不动（旧版，puller/monitor/部分测试引用） |
| `db/database_v2.py` | 新 — `TransactionContext` + `DatabaseLayerV2` |
| `services/movie_service.py` | 全部写方法改用 `self.db.transaction()` |
| `app.py` | `DatabaseLayer` → `DatabaseLayerV2` |

---

## 八、MySQL 最终表设计（15 张）

| 表 | 类型 | 说明 |
|------|------|------|
| `movies` | 主表 | +douban_id, -release_region, +is_published, release_year→NULL |
| `people` | 字典 | +douban_id, UNIQUE(name), UNIQUE(douban_id) |
| `regions` | 字典 | 地区字典 |
| `movie_credits` | N:N | (movie_id, person_id, role_type) — 支持自导自演 |
| `movie_genres` | N:N | (movie_id, type_num) — type_num 对应 crawl_progress |
| `movie_regions` | N:N | (movie_id, region_id) |
| `movie_ratings` | 1:1 | INSERT ON DUPLICATE KEY UPDATE |
| `task_failures` | 日志 | +task_id |
| `crawl_progress` | 进度+字典 | type_num, type_name, interval_id, crawled, total, is_published |
| `movies_history` | 版本 | 电影变更全量快照 |
| `people_history` | 版本 | 人员变更快照 |
| `movie_credits_history` | 版本 | 角色关联变更 |
| `movie_regions_history` | 版本 | 地区关联变更 |
| `movie_genres_history` | 版本 | 类型关联变更 |

> `data_versions` + `data_versions_meta` 已删除（残留旧表，代码中零引用）。

---

## 九、已完成模块清单

| 模块 | 文件 | 行数(约) | 状态 |
|------|------|:--:|:--:|
| Fetcher | `crawler/fetcher.py` | 400 | ✅ |
| Parser | `crawler/parser.py` | 260 | ✅ |
| Storage | `crawler/storage.py` | 430 | ✅ |
| 入口 | `crawler/__init__.py` | 260 | ✅ |
| 代理 | `crawler/proxy.py` | ~300 | ✅ |
| 代理源 | `crawler/proxy_fetcher.py` | ~200 | ✅ |
| 数据库 V2 | `db/database_v2.py` | 560 | ✅ |
| 业务层 | `services/movie_service.py` | ~500 | ✅ |
| 模型层 | `models/movie_models.py` | ~200 | ✅ |
| 雪花 ID | `utils/snowflake.py` | 147 | ✅ |
| 类型配置 | `config/movie_type.py` | 40 | ✅ |
| 监控适配 | `background/monitor.py` | 改 5 行 | ✅ |
| 审计脚本 | `scripts/audit_tables.py` | 43 | ✅ |
| 测试 | `test/browser_pool` `test/crawler` `test/puller` | 133 passed | ✅ |

---

## 十、已完成工作（2026-05-04 更新）

### 10.1 ✅ 评论翻页与登录

- 短评分页 `start += 20` 循环（默认 5 页）
- 长评分页（默认 2 页）
- 豆瓣登录 Cookie 持久化（`scripts/douban_login.py` + `scripts/save_cookies.py`）
- 游客模式优雅降级

### 10.2 ✅ 导演数据 + 详情页

- 电影详情页爬取 `https://movie.douban.com/subject/{douban_id}/`
- 导演提取 `parse_directors(html)` + `save_directors()`
- movie_crawl 原子化（电影+演员+导演在一次任务内完成）
- 已有导演跳过优化（`has_director`）

### 10.3 ✅ crawl_progress 种子数据

- 类型种子 28 种（`scripts/seed_crawl_progress.py`）
- `TYPE_MAP` 同步

### 10.4 ✅ 失败事件合同

- `failure_service.py` — EventType / FailureKind / WorkerEvent / classify_exception
- Worker → Monitor 强类型事件通道

### 10.5 ✅ 浏览器崩溃自愈

- BrowserFetcher 内部检测 `browser.is_connected()` + 自动重启
- `asyncio.Lock` 防 5 Worker 同时重启

### 10.6 ✅ 失败任务认领机制

- `task_failures` 扩展为 17 列（status / claimed_by / scope / kind / parent_failure_id 等）
- `TaskFailureService` — 原子认领（WHERE status='pending'）+ 释放/解决/重爬
- `routes/admin/__init__.py` 6 个端点 + JWT 鉴权

### 10.7 ✅ JWT 认证授权系统

- `users` / `permissions` / `user_permissions` 三张表（18 张总表）
- `AuthService` 11 个方法 — bcrypt + JWT + 权限校验
- `@require_permission(code)` 装饰器
- 种子超级管理员 `admin / admin123`

---

## 十一、当前待完成

| 任务 | 说明 |
|------|------|
| 爬虫集成测试 | ApiFetcher/BrowserFetcher/parse/save 全链路 |
| API 限速 | Semaphore 已就位，速率算法待配 |
| Worker 宕机自检测 | Monitor 需补充 worker_idle 告警 |
| `save_movies` 单部失败未写 item failure | `storage.py` try/except 吞掉 |
| `review_crawl` / `comment_crawl` 翻页失败未写 task_failures | `__init__.py` continue 后无上报 |
| WebSocket JWT 认证 | 当前用 `user_id` 查询参数 |
| `datetime.isoformat()` 散落多文件 | 需抽取 `utils/serializers.py` |
| 前端 Vue 3 | 未开始 |

## 十二、技术债务（2026-05-04 更新）

| 项 | 文件 | 说明 | 状态 |
|------|------|------|:--:|
| `DatabaseLayer` 旧引用 | `background/puller.py` + `monitor.py` | → 已切换 V2 | ✅ |
| `DatabaseLayer` 旧引用 | `test/` 多文件 + `scripts/audit_tables.py` | import 旧版，保留不删 | ⚠️ |
| 日期序列化 | `_write_history` + `storage.py` + `task_failure_service.py` | `hasattr(v, "isoformat")` 散落 3 处 | ⚠️ |
| `type_num` 无 FK | `movie_genres` → `crawl_progress` | crawl_progress.type_num 不唯一 | ⚠️ |
| `except Exception: pass` | `__init__.py` has_director 查询失败 | 静默吞掉 | 🔲 |
| 付费代理 API | `proxy_fetcher.py` | 骨架已搭，实现空 | 🔲 |
