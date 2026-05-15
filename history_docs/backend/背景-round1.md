toolName: todo_write
            
status: success
          
Todos updated: 3 items
          
以下是完整的对话总结，按模块整理：

---

# 项目对话总结

## 项目背景

一个基于 **Quart**（异步 Web 框架）+ **Vue 3** 的全栈项目，核心功能是**爬虫任务调度系统**。数据库使用 MySQL + Redis + MongoDB，项目目录为 `BackEnd/`。

---

## 一、Puller（延迟任务拉取器）— 已实现并稳定

### 文件位置
`background/puller.py` + `config/puller_config.py`

### 核心功能
- 从 Redis ZSet 拉取到期任务，放入 `asyncio.Queue`
- 状态枚举 `PullerState`: `INITIALIZED → RUNNING → BACKPRESSURE → STOPPED`
- **双阈值回滞**背压控制（默认 high=0.8, low=0.6）
- **指数退避**空轮询休眠（0.1s → 5.0s）
- `PullerStats` 统计指标：total_fetched, total_empty_polls, backpressure_enter/exit_count, backpressure_duration
- 模块级单例管理：`init_puller()` / `get_puller()` / `start_puller()` / `stop_puller()`

### 测试覆盖
- 47 个单元测试（mock，零外部依赖）
- 11 个集成测试（需真实 Redis，独立目录 `test/puller_integration/`）
- Puller 测试全部通过

---

## 二、Worker（任务执行器 + WorkerPool）— 已实现并稳定

### 文件位置
`background/worker.py` + `config/worker_config.py`

### 架构设计
- **回调注入模式**：`execute_func: Callable[[str], Coroutine]` 从外部传入
- **状态枚举** `WorkerState`: `IDLE → BUSY → STOPPED`
- **签名约定**：`async (task: str) -> None`，成功不返回值，失败抛异常
- **事件上报**：执行结果通过 `event_queue` 上报，与 Monitor 解耦

### WorkerPool
- 常驻 20 个 Worker（基准），支持动态增删
- `add_worker()` / `remove_worker()`（仅移除空闲 Worker，保护正在执行的任务）
- `start()` / `stop()` + 模块级单例管理
- 属性：`idle_count` / `busy_count` / `total_count`

### dummy_execute（虚拟执行器）
- 用于开发和测试阶段
- `force_result=True` 必定成功 / `force_result=False` 必定失败 / `None` 50% 随机

### 测试覆盖
- 27 个单元测试全部通过

---

## 三、Monitor（系统状态监视器）— 已实现

### 文件位置
`background/monitor.py` + `config/monitor_config.py` + `utils/system_monitor.py`

### MonitorConfig 参数
| 参数 | 默认值 | 说明 |
|---|---|---|
| `interval` | 10 | 轮询间隔（秒） |
| `max_events_per_cycle` | 500 | 单次最多消费事件数 |
| `scale_up_step` | 2 | 每次扩容加几个 Worker |
| `scale_down_step` | 1 | 每次缩容减几个 Worker |

### 单轮 8 步骤
1. **采集 Puller 指标** — state, stats, 队列饱和度
2. **采集 WorkerPool 指标** — idle/busy/total count
3. **消费 Worker 事件队列** — `success` 计数，`failure`/`cancelled` 写 MySQL + WebSocket 推送
4. **采集系统资源**（CPU/内存）— `psutil` 通过 `asyncio.to_thread` 异步调用
5. **三数据库健康检查**（MySQL/Redis/MongoDB）— 新增 `DatabaseLayer.ping_all()`
6. **伸缩决策** — 背压时扩容（上限 WorkerConfig.max_count=40），空闲时缩容（基准 20）
7. **输出报告日志**

### utils/system_monitor.py
- `async get_system_health() -> dict`，用 `asyncio.to_thread` 封装 `psutil`

### 数据库健康检查（在 `db/database.py` 新增）
- `ping_mysql()` — 从连接池借连接执行 SELECT 1
- `ping_redis()` — 调用 `client.ping()`
- `ping_mongodb()` — 调用 `client.admin.command("ping")`
- `ping_all()` — 用 `asyncio.gather` 并行检查三个数据库

---

## 四、WebSocket 推送 — 已实现

### 文件
`utils/websocket.py` + `routes/websocket.py`

### WebSocket 管理器
- 维护 `admin_id → set[WebSocket]` 映射
- `register()` / `unregister()` / `push(admin_id, message)` / `broadcast()`
- 推送失败自动移除连接

### WebSocket 路由
- 端点 `/ws/notifications?user_id=xxx`
- **当前使用 `user_id` 查询参数占位**，后续替换为真实 token/JWT 认证

### 推送流程
```
Worker 失败 → event_queue → Monitor 消费
  → 解析 task 中的 admin_id
  → INSERT INTO task_failures
  → ws_manager.push(admin_id, {type: "task_failure", ...})
```

---

## 五、数据库设计 — 电影数据结构（已建表，待注入模拟数据）

### 数据库
`movie_db`（MySQL），当前 18 张表（2026-05-04 更新）

> **2026-05-04 更新**：DatabaseLayer → DatabaseLayerV2（`background/puller.py` + `background/monitor.py` 已切换）。表数量 10 → 18。

### 9 张电影相关表

| 表 | 类型 | 说明 |
|---|---|---|
| `movies` | 主表 | id, title, original_title, release_year, release_date, release_region, duration, poster_url, imdb_id |
| `people` | 人员表 | id, name |
| `movie_credits` | N:N | movie_id, person_id, role_type("director"/"actor") — 联合主键 **(2026-05 修正：原设计 movie_directors/movie_actors 两张独立表已合并为单表)** |
| `genres` | 字典 | id, name — UNIQUE |
| `movie_genres` | N:N | movie_id, genre_id |
| `regions` | 字典 | id, name — UNIQUE |
| `movie_regions` | N:N | movie_id, region_id |
| `movie_ratings` | 1:1 | movie_id(PK), average(DECIMAL 3,1), count, distribution(JSON) |
| `task_failures` | 记录 | 任务失败事件（Monitor 消费 Worker 事件时写入） |
| `crawl_progress` | 爬取进度 | type_num, type_name, interval_id, crawled, total, is_published — 每个 (type, interval) 组合一条记录 **(2026-05 新增，后移除 status 列)** |

### 设计要点
- 导演/演员共用 `people` 表，通过 `movie_credits.role_type` 区分（`"director"` / `"actor"`）
- 评分单独成表（易变数据与稳定数据分离）
- `distribution` 用 JSON 存 1~5 星占比（如 `{"1":0.2, "2":0.3, "3":2.5, "4":22.0, "5":75.0}`）
- 所有外键 `ON DELETE CASCADE`
- 多对多表 PRIMALY KEY (movie_id, xxx_id)

### 当前状态（做完任务2，待做任务3）
- 旧数据结构已清理
- **9 张电影表已建好，全部为空**
- **任务 3 待完成**：编写专用脚本注入模拟电影数据

---

## 六、下一步要做的事

### 优先级 1：任务 3 — 专用数据注入脚本
编写 Python 脚本，向 9 张表插入模拟电影数据（至少 3~5 部电影，涵盖多对多关系）。

### 优先级 2：crawler 包实现
`crawler/` 目录下实现：
- `crawler/fetcher.py` — 用 `aiohttp` 做 HTTP 请求
- `crawler/parser.py` — 用 `selectolax` 解析 HTML（比 BS4 更轻更快）
- `crawler/storage.py` — 按上述表结构写入 MySQL
- `crawler/__init__.py` — 暴露 `async execute(task: str) -> None`，编排三步流程
- 安装依赖：`pip install aiohttp selectolax`

### 优先级 3：app.py 替换
- 把 `execute_func=dummy_execute` 替换为 `execute_func=crawler.execute`

### 优先级 4：认证系统
- 目前 `utils/auth.py`、`routes/auth.py` 均为空文件
- WebSocket 的 `_resolve_admin_id()` 使用 `user_id` 查询参数占位
- 后续实现 JWT 认证后替换

### 其他
- `crawler/failure_service.py` 为空文件，未来可扩展为事件合同定义
- `utils/auth.py` / `routes/auth.py` / `utils/middleware/auth.py` 均为空

---

## 七、架构原则（供后续参考）

| 原则 | 体现 |
|---|---|
| **回调注入** | Worker 的 `execute_func` 从外部传入 |
| **状态枚举** | Puller/Worker/Monitor 全部用 Enum 规范化 |
| **模块级单例** | init/get/start/stop 四件套 |
| **事件解耦** | Worker 通过 event_queue 上报，Monitor 消费 |
| **背压控制** | 双阈值回滞 + 指数退避 |
| **可配置参数** | 每个组件有独立的 `config/*_config.py` |
| **无回归** | 85 个测试全部通过 |

---

## 八、测试现状

```
test/puller/                    47 单元测试（mock）
test/worker/                    27 单元测试（mock）
test/puller_integration/        11 集成测试（需真实 Redis）
──────────────────────────────────────
总计                            85 全部通过
```

Worker 的集成测试和 Monitor 的单元测试**尚未编写**。

---

如果有需要补充或修正的地方，告诉我。