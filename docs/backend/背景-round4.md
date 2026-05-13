# 2026-05-04 对话总结

> 覆盖范围：Crawler 原子化、失败事件合同、崩溃自愈、失败任务认领机制、认证授权系统

---

## 一、movie_crawl 原子化

### 原始设计（拆分）

```
movie_crawl      → ApiFetcher → save_movies (电影+演员)
director_crawl   → BrowserFetcher → save_directors (导演)
```

问题：导演和演员不在同一事务内入库，数据完整性有时差。

### 变更后（原子化）

```
movie_crawl → ApiFetcher → save_movies (电影+演员+类型+地区+评分)
            → BrowserFetcher 逐部获取详情页 → save_directors (导演)
              ↑ asyncio.gather × 20, BROWSER_SEMAPHORE=2
              ↑ 单部失败不中断整批
```

文件：[`crawler/__init__.py`](file:///e:/QuartEdition/BackEnd/crawler/__init__.py) `_handle_movie_crawl`

`director_crawl` 保留为**存量补录工具**（已入库但缺导演的电影）。

### 导演跳过优化

[`movie_service.py`](file:///e:/QuartEdition/BackEnd/services/movie_service.py) 新增 `has_director(movie_id)`：
`SELECT 1 FROM movie_credits WHERE movie_id=%s AND role_type='director' LIMIT 1`

`_fetch_directors_for_movie` 在 `BrowserFetcher.fetch` 之前调用，已有导演 → 跳过（~3.7s/部 节省）。

---

## 二、DatabaseLayer → DatabaseLayerV2（切除旧引用）

| 文件 | 变更 |
|------|------|
| `background/puller.py` | `from db.database import DatabaseLayer` → `from db.database_v2 import DatabaseLayerV2` |
| `background/monitor.py` | 2 处 docstring 更新 |
| `db/database.py` | **保留不动**（测试和运维脚本仍用旧引用） |

---

## 三、失败事件合同 `failure_service.py`

### 变更前

```python
event_queue.put({"type": "failure", "worker_id": 3, "task": "...", "reason": str(e), ...})
```

问题：字段散落三处、无错误分类、无法统计。

### 变更后

[`crawler/failure_service.py`](file:///e:/QuartEdition/BackEnd/crawler/failure_service.py)：

```python
EventType (str, Enum):   SUCCESS / FAILURE / CANCELLED
FailureKind (str, Enum): NETWORK / TIMEOUT / HTTP / PARSE / STORAGE / ABUSE / VALIDATION / BROWSER / UNKNOWN
WorkerEvent (Pydantic):  强类型事件合同
classify_exception(exc):  从异常对象自动推导 FailureKind
```

Worker → `WorkerEvent(...).model_dump()` → event_queue → Monitor → `WorkerEvent.model_validate(raw)`

### 改动文件

| 文件 | 变更 |
|------|------|
| `crawler/failure_service.py` | **新建** |
| `background/worker.py` | 3 处 `dict` → `WorkerEvent.model_dump()` |
| `background/monitor.py` | `_drain_events` → `model_validate`；`_write_failure_event` 强类型参数 |
| `task_failures` 表 | `kind VARCHAR(16)` 列 |
| `docs/mysql-design.md` | DDL + 状态机 |

---

## 四、BrowserFetcher 崩溃自愈

### 问题

1 Chromium 进程被 5 Worker 共享，崩了全废。

### 方案（`crawler/fetcher.py` 内部闭环）

```python
class BrowserFetcher:
    def __init__(self, browser, playwright=None, ...):
        self._playwright = playwright
        self._restart_lock = asyncio.Lock()

    async def _restart_browser(self):
        async with self._restart_lock:          # 防 5 Worker 同时重启
            if self.browser.is_connected():
                return
            await self.browser.close()
            self.browser = await self._playwright.chromium.launch(headless=True)

    # _do_fetch 的 except Exception:
    except Exception:
        if not self.browser.is_connected():    # 检测崩溃
            await self._restart_browser()      # 自动重启
        return "", False
```

### 设计取舍

| 决策 | 理由 |
|------|------|
| 不加新异常类 | `is_connected()` 比异常类名更可靠 |
| `asyncio.Lock` | 首个检测到的 Worker 重启，其他排队 |
| 不碰 Worker | 崩溃视为"这次 fetch 失败"，下个任务自动用新浏览器 |

文档：[`docs/browser-crash-recovery.md`](file:///e:/QuartEdition/BackEnd/docs/browser-crash-recovery.md)

---

## 五、失败任务认领机制

### DDL（task_failures 扩展为 17 列）

```sql
ALTER TABLE task_failures ADD:
  status            VARCHAR(16)  DEFAULT 'pending'
  claimed_by        INT          DEFAULT 0
  claimed_at        DATETIME     NULL
  resolved_at       DATETIME     NULL
  parent_failure_id BIGINT       DEFAULT 0
  scope             VARCHAR(10)  DEFAULT 'batch'
  item_douban_id    VARCHAR(32)  DEFAULT ''
  item_title        VARCHAR(256) DEFAULT ''
  kind              VARCHAR(16)  DEFAULT 'unknown'
```

### 状态机

```
Monitor INSERT → status='pending'
管理员认领 → UPDATE WHERE status='pending' (原子，先到先得)
  ├─ 重爬 → Push Redis
  │   ├─ 成功 → status='resolved'
  │   └─ 再失败 → INSERT 新行 (parent_failure_id 指向前一行)
  └─ 放弃 → status='pending'
```

### scope 维度

| scope | 含义 | 重爬行为 | 写入方 |
|------|------|------|------|
| `batch` | 整批任务失败 | 重新投 batch JSON → Redis | Monitor |
| `item` | 单部电影失败 | 投 `director_crawl` 小任务 → Redis | `_report_item_failure` 在 `_handle_movie_crawl` 内 |

### API 端点

| 方法 | 路径 | 权限 |
|------|------|------|
| `GET` | `/admin/failures` | — |
| `POST` | `/admin/failures/<id>/claim` | `crawler:manage` |
| `POST` | `/admin/failures/<id>/release` | `crawler:manage` |
| `POST` | `/admin/failures/<id>/resolve` | `crawler:manage` |
| `POST` | `/admin/failures/<id>/retry` | `crawler:manage` |

文件：[`services/task_failure_service.py`](file:///e:/QuartEdition/BackEnd/services/task_failure_service.py) | [`routes/admin/__init__.py`](file:///e:/QuartEdition/BackEnd/routes/admin/__init__.py)

---

## 六、认证授权系统

### 设计决策

- **不设 `role` 字段** — 角色由 `user_permissions` 的权限集合推导
- **权限字典独立成表** — `permissions(code PK)`，支持细粒度 RBAC
- **JWT 鉴权** — 替代旧的 `X-Admin-Id` 请求头

### 三张表

```sql
users:             id, username, password_hash(bcrypt), display_name, is_active, created_at, updated_at
permissions:       code, name, description  (7 条预置)
user_permissions:  user_id, permission_code, granted_by, granted_at  PK(user_id, permission_code)
```

### 7 条权限 → 6 条权限

| code | 名称 | 超级管理员 | 爬虫管理员 | 内容管理员 |
|------|------|:--:|:--:|:--:|
| `user:manage` | 用户管理 | ✅ | | |
| `crawler:manage` | 爬虫管理 | ✅ | ✅ | |
| `movie:manage` | 电影管理 | ✅ | | ✅ |
| `movie:read` | 查看电影数据 | ✅ | | ✅ |
| `comment:read` | 评论查看 | ✅ | | ✅ |
| `comment:manage` | 评论管理 | ✅ | | ✅ |

### 认证链路

```
POST /auth/login → bcrypt.checkpw → JWT(HS256, 7天, sub=user_id)
后续请求：Authorization: Bearer <token>
  → get_current_user() → verify_token + is_active 检查
  → @require_permission(code) → check_permission(user_id, code)
     → user_permissions 查表 → 401/403/放行
```

### 文件清单

| 文件 | 说明 |
|------|------|
| `config/settings.py` | JWT (secret/algorithm/expire) + bcrypt rounds |
| `models/user.py` | UserCreate / UserUpdate / UserRead / UserLogin |
| `models/permission.py` | PermissionRead |
| `models/user_permission.py` | UserPermissionAssign / UserPermissionRead + 白名单校验 |
| `services/auth_service.py` | 11 方法：用户CRUD + 认证 + 权限校验 + 权限管理 |
| `utils/auth.py` | `@require_permission` 装饰器 + `get_current_user()` |
| `routes/auth.py` | POST /auth/login + GET /auth/me |
| `scripts/seed_auth.py` | 建表 + 7 条权限 + admin/admin123 超级管理员 |

### 种子默认管理员

```
username: admin
password: admin123  (ADMIN_PASSWORD 环境变量可覆盖)
```

---

## 七、全项目当前状态快照

### 18 张 MySQL 表

| 类型 | 表 |
|------|------|
| 主表 | movies |
| 字典 | people, regions, permissions |
| N:N | movie_credits, movie_genres, movie_regions, user_permissions |
| 1:1 | movie_ratings |
| 进度+字典 | crawl_progress |
| 日志 | task_failures |
| 版本 | movies_history, people_history, movie_credits_history, movie_regions_history, movie_genres_history |
| 认证 | users |

### 缺陷清单

| # | 问题 | 状态 |
|---|------|:--:|
| 1 | `type_num` 无 FK 约束（crawl_progress.type_num 不唯一） | ⚠️ 已知，当前能满足查询 |
| 2 | `save_movies` 内单部写入失败被吞掉（未写 item failure） | ⚠️ 待补 |
| 3 | Worker 自身宕机导致槽位丢失 | ⚠️ 待 Monitor 检测 |
| 4 | 爬虫集成测试 | 🔲 未写 |
| 5 | 前端（Vue 3）| 🔲 未开始 |
