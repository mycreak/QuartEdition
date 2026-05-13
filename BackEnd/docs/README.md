# QuartEdition 后端文档

> 豆瓣电影数据平台 — Quart (async Flask) 后端
> 最后更新：2026-05-11

---

## 项目概览

| 维度 | 说明 |
|------|------|
| **框架** | Quart 0.19.x + Python 3.10+ asyncio 全异步 |
| **数据库** | MySQL 8.0 (13 表) + MongoDB 6.0 (2 集合) + Redis 7 (3 Key) |
| **爬虫** | Playwright Chromium + aiohttp，5 Worker 协程池 |
| **认证** | JWT (HS256) + bcrypt 密码哈希 + 9 条权限码 RBAC |
| **测试** | pytest + pytest-asyncio，233 个用例全部通过 |
| **部署** | hypercorn / uvicorn，pydantic-settings 环境变量管理 |

## 代码质量现状

| 指标 | 数据 |
|------|------|
| 代码审查发现 | **135 项**（26 HIGH / 66 MEDIUM / 43 GOOD） |
| 已修复 | **94 项**（24 HIGH / 64 MEDIUM / 6 配置优化） |
| 待修复 | **4 项**（2 项架构重构 + 2 项非阻塞建议） |
| 待开发 | **1 项**（用户个人详情页 + 头像昵称编辑 → [后端 TODO](后端TODO.md)） |
| 测试覆盖 | **233 用例全部通过**，Pydantic V1 deprecation 已消除 |
| 安全审计 | **7 条安全链路** 全部闭环（A~G） |

> 详情见 [代码审查待优化清单](代码审查待优化清单.md)

---

## 文档导航

### 🎯 快速开始

| 文档 | 读者 | 内容 |
|------|:--:|------|
| [**API手册**](使用手册/API手册.md) | 前端开发 | 所有 HTTP 端点、请求/响应格式、权限要求 |
| [**运维手册**](使用手册/运维手册.md) | 部署/值班 | 环境变量、启动命令、已知风险、日志体系 |
| [**架构总览**](基础设施构架/架构总览.md) | 新人入职 | 项目背景、技术栈、数据流向、目录结构 |

### 🔧 基础设施

| 文档 | 读者 | 内容 |
|------|:--:|------|
| [**基础设施治理方案**](基础设施治理方案.md) | 架构决策 | Cookie/IP 绑定、反爬风控策略、爬虫架构演进 |
| [**爬虫引擎协同机制**](基础设施构架/爬虫引擎协同机制.md) | 后端开发 | BrowserPool/Crawler/BrowserFetcher 三层协同 |
| [**认证鉴权全链路**](基础设施构架/认证鉴权全链路.md) | 后端开发 | JWT 签发/校验/刷新 + ContextVar 隔离 |
| [**权限管理系统**](基础设施构架/权限管理系统.md) | 后端开发 | 9 条权限码 + 三张表 + `@require_permission` 装饰器 |

### 🗄️ 数据库

| 文档 | 读者 | 内容 |
|------|:--:|------|
| [**数据库设计**](数据库设计&使用/数据库设计.md) | 所有人 | MySQL 13 表 + MongoDB 2 集合 + Redis 3 Key 全景 |
| [**数据库连接器总览**](数据库设计&使用/数据库连接器总览.md) | 后端开发 | DatabaseLayerV2 用法 |
| [MySQL 连接器](数据库设计&使用/MySQL连接器文档.md) | 后端开发 | 异步连接池 + 参数化查询指南 |
| [MongoDB 连接器](数据库设计&使用/MongoDB连接器文档.md) | 后端开发 | MongoDB 操作指南 |
| [Redis 连接器](数据库设计&使用/Redis连接器文档.md) | 后端开发 | ZSET 延迟队列 + Lua 原子操作 |

### 📋 质量

| 文档 | 内容 |
|------|------|
| [**代码审查待优化清单**](代码审查待优化清单.md) | 9 模块逐文件审查，135 项发现，94 项已修复 |
| [**后端 TODO**](后端TODO.md) | 后续迭代需求记录（个人详情页、头像编辑等） |
| [**测试计划**](测试计划.md) | 完整测试体系设计，从单元到端到端全覆盖 |

---

## 目录结构

```
BackEnd/
├── app.py                  # 应用入口 — 生命周期编排
├── config/                 # 配置层（7 文件，全部 pydantic-settings）
│   ├── settings.py         # 全局设置（JWT_SECRET, SNOWFLAKE_MACHINE_ID, BIND）
│   ├── db_config.py        # 数据库连接配置（MySQL/Redis/MongoDB）
│   ├── crawler_config.py   # 爬虫行为参数（翻页/并发/代理开关）
│   ├── puller_config.py    # Puller 调优（背压/休眠/限速/jitter）
│   ├── monitor_config.py   # Monitor 调优（轮询间隔/事件消费上限）
│   ├── movie_type.py       # 豆瓣类型映射 + 评分区间常量
│   └── openapi.py          # OpenAPI 文档元数据
├── db/                     # 数据库基础层（7 文件，V1/V2 双版本）
│   ├── database_v2.py      # DatabaseLayerV2 — ContextVar 隔离 + 事务支持
│   ├── database.py         # DatabaseLayer V1 — ⚠️ DEPRECATED
│   ├── mysql.py            # MySQL 异步连接池 + 参数化查询
│   ├── mongodb.py          # MongoDB 异步操作
│   ├── redis.py            # Redis ZSET 延迟队列 + Lua 脚本
│   └── query_builder.py    # SQL 查询构建器
├── models/                 # Pydantic V2 模型（5 文件）
│   ├── user.py             # UserCreate/Login/Read/Update
│   ├── movie_models.py     # MovieCreate/Read/Detail + Rating + Genre + Credit
│   ├── permission.py       # Permission 模型
│   └── user_permission.py  # 用户权限关联
├── services/               # 业务服务层（7 文件）
│   ├── movie_service.py    # 电影 CRUD + 评分 + 演职人员
│   ├── auth_service.py     # 用户认证 + JWT 签发 + 权限管理
│   ├── review_service.py   # 评论管理（MongoDB）
│   ├── task_history_service.py  # 任务历史记录
│   ├── task_failure_service.py  # 任务失败记录
│   └── app_services.py     # 类型化服务容器
├── routes/                 # HTTP 路由（蓝图层）
│   ├── public/auth_routes.py     # 登录/注册
│   ├── admin/                    # 10 个管理端点文件
│   └── user/                     # 4 个用户端端点文件
├── background/             # 后台调度（3 文件）
│   ├── puller.py           # 从 Redis 拉取到期任务
│   ├── worker.py           # 5 Worker 协程池 + jitter 错峰
│   └── monitor.py          # 系统监控 + WebSocket 推送
├── crawler/                # 爬虫引擎（9 文件）
│   ├── __init__.py         # CrawlerEngine — 任务路由编排
│   ├── fetcher.py          # BrowserFetcher + ApiFetcher 双引擎
│   ├── parser.py           # HTML/JSON 解析 — 纯函数
│   ├── storage.py          # save_movies — 多表写入
│   ├── proxy.py            # ProxyPool — 状态机管理
│   ├── cookie_manager.py   # 多账号 Cookie 管理 + 状态机
│   ├── identity.py         # IdentityManager — Cookie+IP 绑定
│   ├── proxy_fetcher.py    # 免费代理源爬取 + 验证
│   └── failure_service.py  # WorkerEvent 合同定义
├── utils/                  # 通用工具（9 文件）
│   ├── auth.py             # JWT 装饰器 + get_current_user
│   ├── errors.py           # ServiceError 统一异常体系
│   ├── snowflake.py        # Snowflake ID 生成器
│   ├── rate_limit.py       # 基于 Redis 的限流
│   ├── websocket.py        # WebSocket 管理器
│   ├── logging_config.py   # 结构化 JSON 日志（按日志层分文件）
│   ├── service_access.py   # 统一服务获取入口
│   └── serializers.py      # 序列化工具（to_iso 时区）
├── test/                   # 测试（233 用例）
│   ├── admin_integration/  # 管理员集成测试
│   ├── crawler/            # 爬虫测试
│   ├── monitor/            # Monitor 测试
│   ├── puller/             # Puller 测试
│   └── websocket/          # WebSocket 测试
├── scripts/                # 运维脚本（种子数据/日志分析/迁移）
├── data/                   # 运行时数据
│   ├── cookies/            # Cookie 存储 + metadata.json
│   ├── proxies.json        # 管理员添加的代理持久化
│   └── *.html              # 测试用豆瓣页面快照
└── docs/                   # 本文档目录
```

---

## 技术架构速览

```
┌──────────────────────────────────────────────────────────────────┐
│  Quart HTTP 层                                                    │
│  public/auth_routes ← admin/* ← user/* ← websocket              │
└──────────┬───────────────────────────────────────────────────────┘
           │ JWT 认证 → require_login / require_permission
┌──────────▼───────────────────────────────────────────────────────┐
│  services 业务层                                                  │
│  MovieService / AuthService / ReviewService / TaskHistoryService │
└──────────┬───────────────────────────────────────────────────────┘
           │ AppServices 容器 + _get_*_service() 模块级单例
┌──────────▼───────────────────────────────────────────────────────┐
│  DatabaseLayerV2 — ContextVar 隔离 + 事务                         │
│  MySQL(aiomysql) / MongoDB(motor) / Redis(redis-py)             │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  后台调度（3 协程）                                               │
│  Puller(Redis ZSET → asyncio.Queue) → Worker(5) → Crawler → DB  │
│  Monitor(event_queue → WS push → task_history)                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 已知风险 & 待办

| 优先级 | 项目 | 说明 |
|--------|------|------|
| 🔴 待重构 | 旧 fetch API 统一 | `movie_detail_crawl` 仍走 `self._browser.fetch()`，与 Identity 驱动不一致 |
| 🔴 待重构 | 日志读取优化 | `_load_log_entries()` 全量读 OOM，需 tail/按天分文件 |
| 🟡 建议 | V1 database.py 迁移 | V2 已补全 raw_mongodb/raw_redis，V1 可安全删除 |
| 🟡 建议 | USER_AGENT 动态化 | 当前 5 种轮换，可扩充至按环境变量配置的 User-Agent 池 |

---

## 前端文档

| 文档 | 说明 |
|------|------|
| [前端导航](../../FrontEnd/docs/README.md) | 前端 docs 入口 |
| [前端架构概览](../../FrontEnd/docs/架构概览.md) | 技术栈、路由、权限模型 |
