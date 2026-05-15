# MySQL 数据库设计文档

> 扫描日期：2026-05-05
> 数据库：movie_db (MySQL 8.0 / Docker)
> 表数量：18 张
> 最后 DDL 变更：2026-05-05（新增 users / permissions / user_permissions）

---

## 一、表概览

| 表名 | 类型 | 主键 | 说明 |
|------|------|------|------|
| `movies` | 主表 | BIGINT AUTO_INCREMENT | 电影基本信息 |
| `people` | 字典 | BIGINT AUTO_INCREMENT | 人员（含 douban_id） |
| `regions` | 字典 | INT AUTO_INCREMENT | 地区字典 |
| `movie_credits` | N:N | (movie_id, person_id, role_type) | 角色关联 |
| `movie_genres` | N:N | (movie_id, type_num) | 类型关联 |
| `movie_regions` | N:N | (movie_id, region_id) | 地区关联 |
| `movie_ratings` | 1:1 | movie_id (PK) | 评分 |
| `task_failures` | 日志 | BIGINT AUTO_INCREMENT | 任务失败记录 |
| `crawl_progress` | 进度+字典 | INT AUTO_INCREMENT | 爬取进度 AND 类型字典 |
| `movies_history` | 版本 | BIGINT AUTO_INCREMENT | 电影变更历史 |
| `people_history` | 版本 | BIGINT AUTO_INCREMENT | 人员变更历史 |
| `movie_credits_history` | 版本 | BIGINT AUTO_INCREMENT | 角色关联变更历史 |
| `movie_regions_history` | 版本 | BIGINT AUTO_INCREMENT | 地区关联变更历史 |
| `movie_genres_history` | 版本 | BIGINT AUTO_INCREMENT | 类型关联变更历史 |
| `users` | 主表 | INT AUTO_INCREMENT | 用户（管理员） |
| `permissions` | 字典 | VARCHAR(32) CODE PK | 权限字典 |
| `user_permissions` | N:N | (user_id, permission_code) | 用户-权限关联 |

> 5 张 `_history` 表记录"谁在何时做了什么变更"。每次 INSERT/UPDATE/DELETE 同步写入变更后的完整快照。

---

## 二、逐表分析

### 2.1 movies — 电影主表

```sql
CREATE TABLE `movies` (
  `id`              bigint NOT NULL AUTO_INCREMENT,
  `douban_id`       varchar(32) NULL COMMENT '豆瓣电影ID',
  `title`           varchar(512) NOT NULL,
  `original_title`  varchar(512) DEFAULT NULL,
  `release_year`    smallint DEFAULT NULL,
  `release_date`    date DEFAULT NULL,
  `duration`        smallint DEFAULT NULL,
  `poster_url`      varchar(2048) DEFAULT NULL,
  `imdb_id`         varchar(20) DEFAULT NULL,
  `is_published`    tinyint(1) NOT NULL DEFAULT 1 COMMENT '0=下架 1=上架',
  `created_at`      datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`      datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_douban_id` (`douban_id`),
  UNIQUE KEY `uk_imdb_id` (`imdb_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

| 写入方 | 读取方 |
|------|------|
| `MovieService.create_movie(MovieCreate)` → INSERT | `MovieService.get_movie(id)` → SELECT |
| `storage.save_movies()` → 先 `get_movie_by_douban_id()` 去重，再 `create_movie()` | `MovieService.get_movie_by_douban_id(did)` → 去重用 |
| `MovieService.set_movie_published(id, True/False)` → UPDATE | `MovieService.list_movies(published_only=True)` → 上架列表 |

**2026-05 变更**：
- ✅ 新增 `douban_id` UNIQUE — 同一电影从不同 (type, interval) 组合爬入时去重
- ✅ `release_region` 已删除 — 地区关系由 `movie_regions` N:N 表管理
- ✅ `release_year` 改可为空 — 部分 API 不返回年份
- ✅ 新增 `is_published` — 管理员上下架控制（默认上架）

---

### 2.2 people — 人员表

```sql
CREATE TABLE `people` (
  `id`         bigint NOT NULL AUTO_INCREMENT,
  `douban_id`  varchar(32) NULL COMMENT '豆瓣人员ID（来自详情页 personage URL）',
  `name`       varchar(256) NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_name` (`name`),
  UNIQUE KEY `uk_people_douban` (`douban_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**2026-05 变更**：✅ 新增 `douban_id` — 从详情页 HTML 的 personage URL 提取（如 `/personage/27218173/` → `"27218173"`）。优先按 `douban_id` 去重，不存在时回退到 `name`。

---

### 2.3 regions — 地区字典表

```sql
CREATE TABLE `regions` (
  `id`   int NOT NULL AUTO_INCREMENT,
  `name` varchar(128) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB;
```

✅ `storage.py` 中 `_find_or_create_region()` 负责幂等写入。

---

### 2.4 crawl_progress — 爬取进度 + 类型字典（双重角色）

```sql
CREATE TABLE `crawl_progress` (
  `id`            int NOT NULL AUTO_INCREMENT,
  `type_num`      int NOT NULL COMMENT '豆瓣类型编号, 如 11=剧情',
  `type_name`     varchar(64) NOT NULL DEFAULT '' COMMENT '类型名称',
  `interval_id`   varchar(16) NOT NULL COMMENT '评分区间, 如 100:90',
  `crawled`       int NOT NULL DEFAULT 0 COMMENT '已爬取条数，等价于下次 start 参数',
  `total`         int NOT NULL DEFAULT 0 COMMENT '豆瓣平台该组合的电影总数（由 /j/chart/top_list_count 获取）',
  `is_published`  tinyint(1) NOT NULL DEFAULT 1 COMMENT '0=下架 1=上架 — 管理员可见性控制',
  `updated_at`    datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_type_interval` (`type_num`, `interval_id`)
) ENGINE=InnoDB;
```

**双重角色**：
1. **进度追踪**：每个 `(type_num, interval_id)` 一条记录。`crawled` = 下次分页 `start` 参数；`total` = 该组合在豆瓣的总电影数。是否爬完由 **`crawled >= total`** 计算得出，不存状态字段。
2. **类型字典**（替代已删除的 `genres` 表）：通过 `SELECT DISTINCT type_num AS id, type_name AS name, is_published` 查询所有类型

> ⚠️ `type_num` 在此表中不唯一（同一个类型号对应多个评分区间），因此 `movie_genres.type_num` 无法建立物理 FK。详见 [2.6 movie_genres](#26-movie_genres--类型关联nn) 的说明。

**增量爬取**：定时任务重新请求 `/j/chart/top_list_count` 更新 `total`。若 `crawled < total`（新片上映导致），自动继续爬——无需维护状态字段。

> 2026-05 移除了 `status` 列。`pending/active/done` 三态是过度设计：`done` 的真理即 `crawled >= total`，无需单独存储；`pending`/`active` 对调度器无区分价值。`is_published` 是管理员手动控制的用户端可见性。

---

### 2.5 movie_credits — 角色关联（N:N）

```sql
CREATE TABLE `movie_credits` (
  `movie_id`  bigint NOT NULL,
  `person_id` bigint NOT NULL,
  `role_type` varchar(20) NOT NULL,
  PRIMARY KEY (`movie_id`, `person_id`, `role_type`),
  KEY `person_id` (`person_id`),
  FOREIGN KEY ... ON DELETE CASCADE
) ENGINE=InnoDB;
```

✅ `role_type` 用 `"actor"` / `"director"` 区分角色类型，PK `(movie_id, person_id, role_type)` 支持同一人既是导演又是演员（自导自演）。

### 2.6 movie_genres — 类型关联（N:N）

```sql
CREATE TABLE `movie_genres` (
  `movie_id` bigint NOT NULL,
  `type_num` int NOT NULL,
  PRIMARY KEY (`movie_id`,`type_num`),
  CONSTRAINT `movie_genres_ibfk_1` FOREIGN KEY (`movie_id`) REFERENCES `movies` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB;
```

**2026-05 变更**：`genre_id` → `type_num`，FK 到 `genres` 已删除。类型名 JOIN `crawl_progress` 获取。

**`type_num` 无法加外键的说明**：

`crawl_progress.type_num` 不唯一——同一个 `type_num`（如 11=剧情）在 `crawl_progress` 中对应多个评分区间（100:90, 90:80, ...），因此 MySQL 拒绝建立 FK（被引用列必须有 UNIQUE 或 PK）。此表的 `type_num` 是**逻辑引用**而非物理 FK。

之所以不构成实际风险：

| 理论风险 | 实际影响 | 防御机制 |
|------|------|------|
| 孤儿行 — `crawl_progress` 中删了某条记录后 `movie_genres` 仍持有该 `type_num` | 无影响。删除一个评分区间的进度记录是正常操作，该类型的其他区间仍在。`type_num` 是类型编号而非进度记录ID，电影挂的是"类型"不是"进度行" | `_resolve_type_num()` 按 `type_name` 查已有行，不存在则不写入→不会产生脏数据 |
| 写入错误 — 手误写了一个不存在的 `type_num` | 不会发生。前端用下拉框选择类型，数据源来自配置接口（`GET /admin/tasks` 返回的 `DISTINCT type_num`），不存在手写拼错 | `_resolve_type_num()` 查不到则跳过，`LEFT JOIN crawl_progress` 查类型名时返回空但不会报错 |
| 查询时返回不完整 — JOIN 取不到类型名 | 应用层可处理：查询时 LEFT JOIN，前端判断 `type_name` 为空则显示"未知类型"或直接过滤 | `get_movie_detail()` 用 `GROUP BY` 去重后返回，已有同一 `type_num` 的多次出现合并为一条 |

**结论**：去除物理 FK 是 `genres` 表合并入 `crawl_progress` 后的设计取舍，应用层已有完整防御。后续如需加 `DELETE /admin/tasks/<id>` 端点删除某条爬取进度，直接执行即可——`movie_genres` 不受影响。

### 2.7 movie_regions — 地区关联（N:N）

✅ 设计正确。

### 2.8 movie_ratings — 评分（1:1）

✅ 设计正确。`INSERT ... ON DUPLICATE KEY UPDATE`（幂等）。

### 2.9 task_failures — 任务失败记录

```sql
CREATE TABLE `task_failures` (
  `id`                bigint NOT NULL AUTO_INCREMENT,
  `task_id`           bigint NOT NULL DEFAULT 0 COMMENT 'snowflake 任务ID',
  `worker_id`         int NOT NULL,
  `task_json`         text NOT NULL,
  `event_type`        varchar(20) NOT NULL COMMENT 'failure 或 cancelled',
  `kind`              varchar(16) NOT NULL DEFAULT 'unknown' COMMENT '错误分类',
  `reason`            text NOT NULL,
  `created_at`        datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `admin_id`          int NOT NULL DEFAULT 0 COMMENT '提交任务的管理员ID',
  `status`            varchar(16) NOT NULL DEFAULT 'pending' COMMENT 'pending/claimed/resolved',
  `claimed_by`        int NOT NULL DEFAULT 0 COMMENT '认领的管理员ID',
  `claimed_at`        datetime NULL,
  `resolved_at`       datetime NULL,
  `parent_failure_id` bigint NOT NULL DEFAULT 0 COMMENT '关联的上一次失败记录ID（重爬链路），首败=0',
  `scope`             varchar(10) NOT NULL DEFAULT 'batch' COMMENT 'batch=整批失败 / item=单部电影失败',
  `item_douban_id`    varchar(32) NOT NULL DEFAULT '' COMMENT '失败的电影 douban_id（scope=item 时有值）',
  `item_title`        varchar(256) NOT NULL DEFAULT '' COMMENT '失败的电影名（scope=item 时有值）',
  `retry_count`       int NOT NULL DEFAULT 0 COMMENT '重试次数，每重爬一次 +1，上限为 2',
  PRIMARY KEY (`id`),
  KEY `idx_created_at` (`created_at`),
  KEY `idx_status` (`status`),
  KEY `idx_scope_status` (`scope`, `status`)
) ENGINE=InnoDB;

**scope 字段说明**：
- `batch` — 整批任务失败（top_list API 不可达 / 整批解析失败），`item_douban_id` 和 `item_title` 为空
- `item`  — 批次内单部电影失败（某部电影的详情页获取失败 / 导演解析失败），`item_douban_id` 和 `item_title` 有值

**状态机**：
- Monitor 写入 → `status='pending'`, `claimed_by=0`
- 管理员认领 → `UPDATE SET status='claimed', claimed_by=<admin_id>`（WHERE status='pending' 原子）
- 重爬：
  - `scope='batch'` → 重新投整个 batch 任务到 Redis
  - `scope='item'`  → 投 `director_crawl` 小任务（`{"type":"director_crawl", "douban_id":"...", "movie_id":...}`）
- 重爬又失败 → Monitor 写入新行，`parent_failure_id` 指向前一行
- 标记解决 → `UPDATE SET status='resolved', resolved_at=NOW()`
- 放弃认领 → `UPDATE SET status='pending', claimed_by=0`

**2026-05 变更**：新增 `task_id`、`kind`、`status`、`claimed_by`、`claimed_at`、`resolved_at`、`parent_failure_id`、`scope`、`item_douban_id`、`item_title` 列。

### 2.10 users — 用户表

```sql
CREATE TABLE users (
  id            INT           NOT NULL AUTO_INCREMENT,
  username      VARCHAR(64)   NOT NULL,
  password_hash VARCHAR(256)  NOT NULL,
  display_name  VARCHAR(64)   NOT NULL DEFAULT '',
  is_active     TINYINT(1)    NOT NULL DEFAULT 1,
  created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

- `is_active=0` → 禁用，JWT 校验时返回 403
- `is_active=1` → 正常，恢复即改回 1
- 不设 `role` 字段——角色由 `user_permissions` 的权限集合推导

### 2.11 permissions — 权限字典

```sql
CREATE TABLE permissions (
  code        VARCHAR(32)  NOT NULL,
  name        VARCHAR(64)  NOT NULL,
  description VARCHAR(256) NOT NULL DEFAULT '',
  PRIMARY KEY (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

预设 7 条：

| code | name | 说明 |
|------|------|------|
| user:manage | 用户管理 | 创建/禁用/恢复/删除用户，分配权限 |
| crawler:manage | 爬虫管理 | 提交爬虫任务 / 查看状态 / 管理失败任务 |
| movie:manage | 电影管理 | 编辑/上下架 movies/people/credits |
| movie:read | 查看电影数据 | 只读 |
| comment:read | 评论查看 | 查看 MongoDB reviews/comments |
| comment:manage | 评论管理 | 上下架 MongoDB reviews/comments |

### 2.12 user_permissions — 用户-权限关联

```sql
CREATE TABLE user_permissions (
  user_id         INT         NOT NULL,
  permission_code VARCHAR(32) NOT NULL,
  granted_by      INT         NOT NULL DEFAULT 0,
  granted_at      DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, permission_code),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (permission_code) REFERENCES permissions(code) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

三种预设管理员权限集合：
- **超级管理员**：全部 6 条
- **爬虫管理员**：`crawler:manage`
- **内容管理员**：`movie:manage` / `movie:read` / `comment:read` / `comment:manage`

---

## 三、ER 关系图

```
movies (1) ────< (N) movie_credits (N) >──── (1) people
  │                    │ role_type
  │                    │ ("director"/"actor")
  │
  ├──< movie_genres  >── type_num ──参照──> crawl_progress
  │
  ├──< movie_regions >── regions
  │
  └── movie_ratings (1:1)

task_failures  ← Monitor 写入
```

---

## 四、版本历史表设计

5 张 `_history` 表的设计原则完全相同，以 `movies_history` 为例：

```sql
CREATE TABLE movies_history (
    id              BIGINT AUTO_INCREMENT,
    movie_id        BIGINT NOT NULL,         -- 原表主键（去掉了 AUTO_INCREMENT）
    douban_id       VARCHAR(32),             -- 与 movies 表字段一致
    title, original_title, release_year, ... -- 全量字段快照
    is_published    TINYINT(1) DEFAULT 1,
    created_at      DATETIME,                -- 原表 created_at（不同于 changed_at）
    updated_at      DATETIME,                -- 原表 updated_at
    change_type     VARCHAR(16) NOT NULL,    -- "create" / "update" / "delete"
    changed_by      VARCHAR(64) NOT NULL DEFAULT '',
    changed_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_mv_ver (movie_id, changed_at)
);
```

**写入规则**：
| 操作 | 快照内容 | change_type | 原子性 |
|------|------|:--:|------|
| INSERT | 插入后的完整行 | `create` | ✅ 主表 + history 同一事务 |
| UPDATE | 更新后的完整行 | `update` | ✅ 主表 + history 同一事务 |
| DELETE | 删除前的完整行 | `delete` | ✅ 先记历史 → 再删数据，同一事务 |

**与其他时间列的区别**：
- `movies.created_at` — 电影首次录入的时间（拷贝到 history）
- `movies.updated_at` — 电影最后修改时间（拷贝到 history）
- `history.changed_at` — **这条版本记录写入的时间**（`DEFAULT CURRENT_TIMESTAMP`）

**N:N 关联表**（movie_credits/movie_regions/movie_genres）的 history 简化设计：
- 无 `create`/`update` 区分——关联只有增删
- `change_type` 为 `"create"` 或 `"delete"`
- 删除时记录被删的那一行关联（movie_id, person_id, role_type）

**版本记录范围**：
- ✅ movies / people / movie_credits / movie_regions / movie_genres
- ❌ movie_ratings — 统计数据，不是"纠错"场景
- ❌ crawl_progress — 爬虫内部状态
- ❌ task_failures — 日志表，只增不删不改

---

## 五、ID 类型约定

| 表 | ID 列 | 类型 | 来源 |
|------|------|------|------|
| movies | id | BIGINT AUTO_INCREMENT | MySQL 自增 |
| movies | douban_id | VARCHAR(32) UNIQUE | 豆瓣 API 返回 |
| people | id | BIGINT AUTO_INCREMENT | MySQL 自增 |
| task_failures | task_id | BIGINT | Snowflake snowflake.generate_id() |
| crawl_progress | id | INT AUTO_INCREMENT | MySQL 自增 |
| 任务 (task JSON) | id | BIGINT | Snowflake 生成 |
