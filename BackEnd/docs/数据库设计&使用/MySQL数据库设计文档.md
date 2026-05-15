# MySQL 数据库设计文档

> 数据库：movie_db (MySQL 8.0)
> 表数量：21 张
> 最后更新：2026-05-15
> 14 条权限码 · 3 类角色 · 5 张版本历史表

---

## 一、表概览

### 1.1 21 表分类

| 分类 | 数量 | 表名 |
|------|:----:|------|
| **核心业务** | 9 | `movies` `people` `regions` `movie_credits` `movie_genres` `movie_regions` `movie_ratings` `douban_ids` `crawl_progress` |
| **用户与权限** | 3 | `users` `permissions` `user_permissions` |
| **任务与日志** | 4 | `task_history` `task_failures` `movie_review` `review_summary` |
| **版本历史** | 5 | `movies_history` `people_history` `movie_credits_history` `movie_genres_history` `movie_regions_history` |

### 1.2 表索引速查

| 表名 | 主键 | 主要索引/唯一键 | 说明 |
|------|------|------|------|
| `movies` | INT AUTO_INCREMENT | idx_douban(douban_id) | 电影主表 |
| `people` | INT AUTO_INCREMENT | — | 演职人员 |
| `regions` | INT AUTO_INCREMENT | — | 地区字典 |
| `movie_credits` | (movie_id, person_id, role_type) PK | — | N:N 角色关联 |
| `movie_genres` | (movie_id, type_num) PK | — | N:N 类型关联 |
| `movie_regions` | (movie_id, region_id) PK | — | N:N 地区关联 |
| `movie_ratings` | movie_id (PK) | — | 1:1 评分 |
| `douban_ids` | douban_id (PK) | idx_source(type_num, interval_id) | 豆瓣电影 ID 资产 |
| `crawl_progress` | INT AUTO_INCREMENT | uk_type_interval(type_num, interval_id) | 爬取进度+类型字典 |
| `users` | INT AUTO_INCREMENT | uk_username(username), uuid UNIQUE | 用户 |
| `permissions` | code (PK) VARCHAR(32) | — | 权限字典 |
| `user_permissions` | (user_id, permission_code) PK | FK → users / permissions | N:N 用户权限 |
| `task_history` | BIGINT (snowflake) PK | idx_admin_id, idx_status, idx_task_type, idx_created_at | 任务历史 |
| `task_failures` | INT AUTO_INCREMENT | idx_status, idx_claimed_by, idx_task, idx_kind | 失败任务 |
| `movie_review` | review_id (PK) | idx_movie(movie_id), idx_status | 长评待爬表 |
| `review_summary` | INT AUTO_INCREMENT | uk_movie_id(movie_id), idx_status | AI 长评总结 |
| `movies_history` | INT AUTO_INCREMENT | idx_movie(movie_id) | 电影变更历史 |
| `people_history` | INT AUTO_INCREMENT | idx_person(person_id) | 人员变更历史 |
| `movie_credits_history` | INT AUTO_INCREMENT | idx_mc(movie_id, person_id) | 演职人员变更历史 |
| `movie_genres_history` | INT AUTO_INCREMENT | idx_mg(movie_id) | 类型关联变更历史 |
| `movie_regions_history` | INT AUTO_INCREMENT | idx_mr(movie_id) | 地区关联变更历史 |

---

## 二、核心业务表（9 张）

### 2.1 movies — 电影主表

```sql
CREATE TABLE movies (
  id              INT           NOT NULL AUTO_INCREMENT,
  douban_id       VARCHAR(32)   NOT NULL DEFAULT '',
  title           VARCHAR(256)  NOT NULL DEFAULT '',
  original_title  VARCHAR(256)  NOT NULL DEFAULT '',
  release_year    INT           DEFAULT NULL,
  release_date    VARCHAR(16)   NOT NULL DEFAULT '',
  duration        INT           DEFAULT NULL        COMMENT '片长（分钟）',
  poster_url      VARCHAR(2048) DEFAULT NULL,
  is_published    TINYINT(1)    NOT NULL DEFAULT 0  COMMENT '0=下架 1=上架',
  imdb_id         VARCHAR(20)   DEFAULT NULL,
  created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  INDEX idx_douban (douban_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

| 写入方 | 读取方 |
|--------|--------|
| `crawler/storage.save_movie_basic()` — INSERT | `routes/admin/movie_routes` — 管理端列表/详情 |
| `routes/admin/movie_routes` — PATCH 编辑 | `routes/user/` — 用户端列表/详情 |
| `routes/admin/poster_routes` — 更新 poster_url | `crawler/` — 查重（douban_id 幂等） |

### 2.2 people — 演职人员

```sql
CREATE TABLE people (
  id          INT           NOT NULL AUTO_INCREMENT,
  name        VARCHAR(128)  NOT NULL,
  douban_id   VARCHAR(64)   DEFAULT NULL,
  admin_id    INT           NOT NULL DEFAULT 0 COMMENT '录入的管理员ID，0代表爬虫自动录入',
  is_duplicate TINYINT      NOT NULL DEFAULT 0 COMMENT '重名标记：0=无重名/已确认，1=待确认重名，-1=无效重复记录',
  created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at  DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```
### 新增字段更新SQL（现有数据库执行即可）
```sql
ALTER TABLE people ADD COLUMN admin_id INT NOT NULL DEFAULT 0 COMMENT '录入的管理员ID，0代表爬虫自动录入' AFTER douban_id;
ALTER TABLE people ADD COLUMN is_duplicate TINYINT NOT NULL DEFAULT 0 COMMENT '重名标记：0=无重名/已确认，1=待确认重名，-1=无效重复记录' AFTER admin_id;
```

| 说明 |
|------|
| `storage._find_or_create_person()` 先查 name+ douban_id，不存在再 INSERT |
| 同一人可能对应多个 douban_id（别名/跨语言），不设 UNIQUE 约束 |

### 2.3 regions — 地区字典

```sql
CREATE TABLE regions (
  id          INT           NOT NULL AUTO_INCREMENT,
  name        VARCHAR(64)   NOT NULL,
  created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_regions_name (name) COMMENT '地区名称唯一约束，避免重复国家/地区'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 2.4 movie_credits — 演职人员关联

```sql
CREATE TABLE movie_credits (
  movie_id   INT          NOT NULL,
  person_id  INT          NOT NULL,
  role_type  VARCHAR(16)  NOT NULL COMMENT 'director / actor / writer / producer / …',
  PRIMARY KEY (movie_id, person_id, role_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

| role_type 常见值 | 说明 |
|:--|------|
| `director` | 导演 |
| `actor` | 演员 |
| `writer` | 编剧 |
| `producer` | 制片人 |

### 2.5 movie_genres — 电影类型关联

```sql
CREATE TABLE movie_genres (
  movie_id  INT NOT NULL,
  type_num  INT NOT NULL,
  PRIMARY KEY (movie_id, type_num)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

> `type_num` 逻辑引用 `crawl_progress.type_num`（豆瓣类型编号），非外键约束。

### 2.6 movie_regions — 电影地区关联

```sql
CREATE TABLE movie_regions (
  movie_id   INT NOT NULL,
  region_id  INT NOT NULL,
  PRIMARY KEY (movie_id, region_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 2.7 movie_ratings — 评分统计

```sql
CREATE TABLE movie_ratings (
  movie_id      INT           NOT NULL,
  average       DECIMAL(3,1)  DEFAULT NULL,
  `count`       INT           NOT NULL DEFAULT 0,
  distribution  JSON          DEFAULT NULL        COMMENT '{"1":比例, "2":比例, …}',
  created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (movie_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

| 说明 |
|------|
| 1:1 关系 — 一部电影只有一条评分记录 |
| `storage` 使用 `INSERT … ON DUPLICATE KEY UPDATE` 幂等写入 |
| `average` DECIMAL(3,1) = 最高 9.9 分 |

### 2.8 douban_ids — 豆瓣电影 ID 资产表

```sql
CREATE TABLE douban_ids (
  douban_id     VARCHAR(32)   NOT NULL PRIMARY KEY   COMMENT '豆瓣电影ID',
  title         VARCHAR(128)  NOT NULL               COMMENT '电影名',
  source        VARCHAR(32)   NOT NULL DEFAULT 'dashboard_api' COMMENT '来源',
  type_num      INT           DEFAULT NULL           COMMENT '电影类型编号',
  interval_id   VARCHAR(16)   DEFAULT NULL           COMMENT '评分区间',
  admin_id      INT           DEFAULT NULL           COMMENT '认领人 user_id',
  is_acquired   TINYINT(1)    NOT NULL DEFAULT 0     COMMENT '0=未认领 1=已认领',
  is_scraped    TINYINT(1)    NOT NULL DEFAULT 0     COMMENT '0=未爬 1=已爬取成功',
  acquired_at   DATETIME      DEFAULT NULL,
  task_id       BIGINT        DEFAULT NULL           COMMENT '关联 task_history.id',
  created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_acquired (is_acquired),
  INDEX idx_scraped (is_scraped),
  INDEX idx_task (task_id),
  INDEX idx_source (type_num, interval_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**生命周期状态机**：

```
is_scraped=0, is_acquired=0  →  未认领（movie_crawl 写入）
is_scraped=0, is_acquired=1  →  已认领，排队爬取中
is_scraped=1, is_acquired=1  →  终态：已爬取完成（不可释放/重认领）
```

### 2.9 crawl_progress — 爬取进度 + 类型字典

```sql
CREATE TABLE crawl_progress (
  id           INT NOT NULL AUTO_INCREMENT,
  type_num     INT NOT NULL DEFAULT 0,
  interval_id  VARCHAR(32) NOT NULL DEFAULT '',
  type_name    VARCHAR(64) NOT NULL DEFAULT '',
  is_published TINYINT(1)  NOT NULL DEFAULT 0,
  douban_total INT         NOT NULL DEFAULT 0,
  ids_fetched  INT         NOT NULL DEFAULT 0   COMMENT '已从榜单获取的 douban_id 数',
  PRIMARY KEY (id),
  UNIQUE KEY uk_type_interval (type_num, interval_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

| 双重角色 |
|----------|
| **类型字典**：`type_num` + `type_name` 存储豆瓣电影分类（剧情/喜剧/…） |
| **进度表**：`douban_total` + `ids_fetched` 记录每类的爬取进度 |

> `GET /admin/tasks` 接口用 LEFT JOIN 查出 `crawled_count / scraped_count / completed_count` 三指标。

---

## 三、用户与权限表（3 张）

### 3.1 users — 用户表

```sql
CREATE TABLE users (
  id            INT           NOT NULL AUTO_INCREMENT,
  uuid          BIGINT        NOT NULL UNIQUE      COMMENT 'Snowflake 全局唯一 ID',
  username      VARCHAR(64)   NOT NULL,
  password_hash VARCHAR(256)  NOT NULL             COMMENT 'bcrypt 12 rounds',
  display_name  VARCHAR(64)   NOT NULL DEFAULT '',
  avatar_url    VARCHAR(2048) DEFAULT ''           COMMENT 'TOS 头像签名 URL',
  is_active     TINYINT(1)    NOT NULL DEFAULT 1  COMMENT '0=禁用 1=正常',
  created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

| 字段说明 |
|----------|
| `uuid` — Snowflake 64位 ID，用于前端 URL 路由隐私保护（替代自增 id） |
| `password_hash` — bcrypt 12 rounds，每次登录用 `bcrypt.checkpw()` 验证 |
| `is_active` — 禁用后 JWT 校验返回 403，不可登录 |
| `avatar_url` — 通过 `ALTER TABLE` 后加，默认指向 TOS 默认头像 |
| 不设 `role` 字段 — 角色由 `user_permissions` 的权限集合推导 |

### 3.2 permissions — 权限字典

```sql
CREATE TABLE permissions (
  code        VARCHAR(32)  NOT NULL,
  name        VARCHAR(64)  NOT NULL,
  description VARCHAR(256) NOT NULL DEFAULT '',
  PRIMARY KEY (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**14 条预设权限**：

| code | name | 可访问的端点 |
|------|------|-------------|
| `user:manage` | 用户管理 | 创建/禁用/改名/分配权限 |
| `crawler:task:read` | 任务只读 | 查看爬取进度、任务历史 |
| `crawler:task:write` | 任务提交 | 提交爬虫任务 |
| `crawler:failure:manage` | 失败管理 | 认领/释放/解决/重试失败任务 |
| `movie:manage` | 电影管理 | 编辑基本信息/上下架/演职人员/评分 |
| `movie:read` | 查看电影数据 | 管理端浏览电影详情 |
| `comment:read` | 评论查看 | 浏览长评/短评列表 |
| `comment:manage` | 评论管理 | 长评/短评上下架管理 |
| `system:monitor` | 系统监控 | 查看实时状态/队列/日志/限流事件 |
| `infra:proxy:read` | 代理查看 | 查看代理列表和下拉选项 |
| `infra:proxy:manage` | 代理管理 | 增删改代理+连通性测试 |
| `infra:cookie:read` | Cookie查看 | 查看Cookie列表和下拉选项 |
| `infra:cookie:manage` | Cookie管理 | 增删改Cookie+有效性测试 |
| `infra:sensitive:read` | 敏感信息查看 | 查看代理密码、完整Cookie值 |

**权限兼容规则**：`system:monitor` 持有者自动获得所有 `infra:*` 权限（后端 `auth_service.chack_permission` 和前端 `hasPermission` 均实施此规则）。

### 3.3 user_permissions — 用户权限关联

```sql
CREATE TABLE user_permissions (
  user_id         INT         NOT NULL,
  permission_code VARCHAR(32) NOT NULL,
  granted_by      INT         NOT NULL DEFAULT 0,
  granted_at      DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, permission_code),
  CONSTRAINT fk_up_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_up_perm FOREIGN KEY (permission_code) REFERENCES permissions(code) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**三种预设管理员权限集合**（seed_auth.py 不默认创建，仅作概念参考）：

| 角色 | 权限集合 |
|------|----------|
| 超级管理员 | 全部 14 条 |
| 爬虫管理员 | `crawler:task:read` `crawler:task:write` `crawler:failure:manage` `movie:read` |
| 内容管理员 | `movie:manage` `movie:read` `comment:read` `comment:manage` |

> `POST /admin/users/<id>/permissions` 全量替换权限（空数组 = 清空）。

---

## 四、任务与日志表（4 张）

### 4.1 task_history — 任务历史

```sql
CREATE TABLE task_history (
  id          BIGINT          PRIMARY KEY           COMMENT 'Snowflake ID',
  admin_id    INT             NOT NULL              COMMENT '提交人 user_id',
  task_type   VARCHAR(32)     NOT NULL              COMMENT 'movie_crawl / review_crawl / comment_crawl / director_crawl / ai_review_summary / …',
  task_params JSON                                  COMMENT '任务提交时的完整参数',
  status      VARCHAR(16)     NOT NULL DEFAULT 'submitted' COMMENT 'submitted / running / done / failed',
  message     VARCHAR(512)    DEFAULT NULL          COMMENT '完成/失败时的描述',
  created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_admin_id (admin_id),
  INDEX idx_status (status),
  INDEX idx_task_type (task_type),
  INDEX idx_created_at (created_at),
  CONSTRAINT fk_th_admin FOREIGN KEY (admin_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

| 状态流转 |
|----------|
| `submitted` → `running` → `done` / `failed` |
| `message` 在 running 期间实时更新为当前进度描述 |

### 4.2 task_failures — 失败任务记录

```sql
CREATE TABLE task_failures (
  id                INT           NOT NULL AUTO_INCREMENT PRIMARY KEY,
  task_id           BIGINT        NOT NULL DEFAULT 0,
  worker_id         INT           NOT NULL DEFAULT 0,
  task_json         JSON          NOT NULL,
  event_type        VARCHAR(16)   NOT NULL DEFAULT 'failure'  COMMENT 'failure / cancelled',
  kind              VARCHAR(32)   NOT NULL DEFAULT 'unknown'  COMMENT 'network / timeout / parse / storage / abuse / validation',
  reason            VARCHAR(1024) DEFAULT NULL,
  admin_id          INT           NOT NULL DEFAULT 0,
  status            VARCHAR(16)   NOT NULL DEFAULT 'pending'  COMMENT 'pending / claimed / resolved',
  claimed_by        INT           NOT NULL DEFAULT 0,
  claimed_at        DATETIME      DEFAULT NULL,
  resolved_at       DATETIME      DEFAULT NULL,
  parent_failure_id INT           NOT NULL DEFAULT 0,
  retry_count       INT           NOT NULL DEFAULT 0,
  scope             VARCHAR(16)   NOT NULL DEFAULT 'batch'    COMMENT 'batch / item',
  item_douban_id    VARCHAR(32)   NOT NULL DEFAULT '',
  item_title        VARCHAR(256)  NOT NULL DEFAULT '',
  snapshot          JSON          DEFAULT NULL                COMMENT '执行现场快照',
  created_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at        DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_status (status),
  INDEX idx_claimed_by (claimed_by),
  INDEX idx_task (task_id),
  INDEX idx_kind (kind)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

| Monitor 写入 | 管理员操作 |
|-------------|-----------|
| WorkerEvent(FAILURE) → 写入 `task_failures` | `POST /admin/failures/<id>/claim` / `release` / `resolve` / `retry` |

### 4.3 movie_review — 长评待爬表

```sql
CREATE TABLE movie_review (
  review_id     VARCHAR(32)   NOT NULL PRIMARY KEY   COMMENT '豆瓣长评ID',
  movie_id      INT           NOT NULL               COMMENT '本地 movies.id',
  subject_id    VARCHAR(32)   NOT NULL               COMMENT '豆瓣电影 subject_id',
  title         VARCHAR(256)  NOT NULL DEFAULT ''    COMMENT '长评标题',
  author        VARCHAR(64)   NOT NULL DEFAULT ''    COMMENT '作者昵称',
  useful_count  INT           NOT NULL DEFAULT 0     COMMENT '赞同数',
  `date`        VARCHAR(16)   NOT NULL DEFAULT ''    COMMENT '发布日期',
  status        VARCHAR(16)   NOT NULL DEFAULT 'pending' COMMENT 'pending / done / failed',
  created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_movie (movie_id),
  INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

| 生命周期 |
|----------|
| `review_crawl` 采集摘要 → INSERT status='pending' |
| `review_body_crawl` 爬取正文 → UPDATE status='done' |
| 爬取失败 → UPDATE status='failed' |

### 4.4 review_summary — AI 长评总结

```sql
CREATE TABLE review_summary (
  id            INT UNSIGNED  NOT NULL AUTO_INCREMENT  COMMENT '主键ID',
  movie_id      INT           NOT NULL                 COMMENT '关联电影ID',
  full_summary  TEXT                                   COMMENT '长评综合总结（AI 生成）',
  review_tags   JSON                                   COMMENT '评论标签数组',
  status        VARCHAR(20)   NOT NULL DEFAULT 'pending' COMMENT 'pending / done / failed',
  created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_movie_id (movie_id),
  KEY idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='电影评论AI总结表';
```

| 说明 |
|------|
| `ai_review_summary` 任务拉取全部已上架长评 → 调用 DeepSeek → 写入总结和标签 |
| 一部电影最多一条总结（`uk_movie_id`） |

---

## 五、版本历史表（5 张）

5 张 `_history` 表设计原则完全一致，以 `movies_history` 为例：

```sql
CREATE TABLE movies_history (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  movie_id        INT NOT NULL,           -- 原表主键
  douban_id       VARCHAR(32) DEFAULT '',
  title           VARCHAR(256) DEFAULT '',
  original_title  VARCHAR(256) DEFAULT '',
  release_year    INT DEFAULT NULL,
  release_date    VARCHAR(16) DEFAULT '',
  duration        INT DEFAULT NULL,
  poster_url      VARCHAR(2048) DEFAULT NULL,
  imdb_id         VARCHAR(20) DEFAULT NULL,
  is_published    TINYINT(1) DEFAULT 0,
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  change_type     VARCHAR(16) NOT NULL DEFAULT 'update',
  changed_by      VARCHAR(64) NOT NULL DEFAULT 'system',
  INDEX idx_movie (movie_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 其余 4 张类比：people_history / movie_credits_history /
--     movie_genres_history / movie_regions_history
```

**写入规则**：

| 操作 | 快照内容 | change_type | 原子性 |
|------|----------|:----------:|--------|
| INSERT | 插入后的完整行 | `create` | ✅ 主表 + history 同一事务 |
| UPDATE | 更新后的完整行 | `update` | ✅ 主表 + history 同一事务 |
| DELETE | 删除前的完整行 | `delete` | ✅ 先记历史 → 再删数据，同一事务 |

**时间列区别**：
- `movies.created_at` — 电影首次录入时间（拷贝到 history）
- `movies.updated_at` — 电影最后修改时间（拷贝到 history）
- `history.changed_at` — 版本记录写入时间（`DEFAULT CURRENT_TIMESTAMP`）

**N:N 关联表特殊处理**：`movie_credits_history` / `movie_genres_history` / `movie_regions_history` 无 `create`/`update` 区分，`change_type` 仅为 `create` 或 `delete`。

---

## 六、ER 关系图

```
                    ┌──────────────────────────┐
                    │         users             │
                    │  PK: id                   │
                    │  uuid (snowflake UNIQUE)  │
                    └──────┬───────┬────────────┘
                           │       │
              ┌────────────┘       └──────────────┐
              ▼                                    ▼
    ┌──────────────────┐                ┌──────────────────┐
    │  user_permissions │                │   task_history    │
    │  PK: (user_id,    │                │  PK: id (snowflake)│
    │       perm_code)  │                │  FK: admin_id     │
    └────────┬──────────┘                └──────────────────┘
             │
             ▼
    ┌──────────────────┐
    │   permissions     │
    │  PK: code (14条)  │
    └──────────────────┘

    ┌──────────────────────────────────────────────────────┐
    │                    movies                             │
    │  PK: id           idx_douban(douban_id)               │
    └──┬───────┬──────────┬──────────┬──────────────────────┘
       │       │          │          │
       ▼       ▼          ▼          ▼
  ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────────┐
  │ movie_ │ │ movie_ │ │ movie_ │ │ movie_ratings │
  │ credits│ │ genres │ │ regions│ │ PK: movie_id  │
  │ (id,   │ │ (id,   │ │ (id,   │ │ 1:1           │
  │  pid,  │ │  type) │ │  rid)  │ └──────────────┘
  │  role) │ └────────┘ └───┬────┘
  └───┬────┘                │
      ▼                     ▼
  ┌────────┐          ┌────────┐
  │ people │          │regions │
  └────────┘          └────────┘

    ┌──────────────┐     ┌──────────────────┐
    │ douban_ids   │     │ crawl_progress   │
    │ PK: douban_id│◄───→│ type_num         │
    │ is_acquired  │     │ interval_id      │
    │ is_scraped   │     │ (逻辑引用)        │
    └──────────────┘     └──────────────────┘

    ┌──────────────┐     ┌──────────────────┐
    │ movie_review │     │ review_summary   │
    │ PK: review_id│     │ PK: id           │
    │ FK: movie_id │     │ uk_movie_id      │
    └──────────────┘     └──────────────────┘
```

---

## 七、索引策略

| 索引 | 用途 |
|------|------|
| `douban_ids.idx_source(type_num, interval_id)` | 进度查询 JOIN + GROUP BY |
| `movie_review.idx_movie(movie_id)` | 按电影查待爬长评 |
| `task_history.idx_created_at(created_at)` | 历史按时间倒序 |
| `task_failures.idx_status(status)` + `idx_claimed_by(claimed_by)` | 失败认领管理 |
| `movies.idx_douban(douban_id)` | 爬虫查重（`SELECT id FROM movies WHERE douban_id=?`）|

---

## 八、变更日志

| 日期 | 变更 | 说明 |
|------|------|------|
| 2026-05-14 | 权限码扩充 | `permissions` 从 9 条 → 14 条（新增 infra:* 5 条） |
| 2026-05-13 | `users.avatar_url` | ALTER TABLE 新增，TOS 头像签名 URL |
| 2026-05-13 | `users.uuid` | 新增 Snowflake 全局唯一 ID |
| 2026-05-10 | `review_summary` | 新建表，AI 长评总结 |
| 2026-05-05 | `crawl_progress.ids_fetched` | 新增字段，替代 offset 分页 |
| 2026-05-05 | 权限拆分 | `crawler:manage` → `crawler:task:read` + `crawler:task:write` + `crawler:failure:manage` |
| 2026-05-01 | DDL 重构 | `movies` id BIGINT→INT, douban_id UNIQUE→INDEX, release_date DATE→VARCHAR(16) |
