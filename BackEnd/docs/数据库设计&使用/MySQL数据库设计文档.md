# MySQL 数据库设计文档

> 数据库：movie_db (MySQL 8.0)
> 表数量：**29 张（24 张活动表 + 5 张版本历史表）**
> 最后更新：2026-05-24
> 14 条权限码 · 3 种角色级别 · 10 维度用户行为评分模型

---

## 一、表全景

### 1.1 29 表分类总览

| 分类 | 数量 | 表名 |
|------|:----:|------|
| **核心业务** | 9 | `movies` `people` `regions` `movie_credits` `movie_genres` `movie_regions` `movie_ratings` `douban_ids` `crawl_progress` |
| **用户与权限** | 3 | `users` `permissions` `user_permissions` |
| **任务与日志** | 5 | `task_history` `task_failures` `movie_review` `movie_style_tag` `movie_style` |
| **AI 与内容** | 1 | `review_summary` |
| **片单** | 1 | `playlists` |
| **演职人员** | 1 | `duplicate_name` |
| **用户行为** | 4 | `user_movie_status` `user_action_log` `user_tag_score` `config_score_weight` |
| **版本历史** | 5 | `movies_history` `people_history` `movie_credits_history` `movie_genres_history` `movie_regions_history` |

### 1.2 表索引速查

| 表名 | 主键 | 主要索引 / 唯一键 | 说明 |
|------|------|------|------|
| `movies` | INT AUTO_INCREMENT → BIGINT | `idx_douban(douban_id)` | 电影主表 |
| `people` | INT AUTO_INCREMENT | `idx_people_name(name)` | 演职人员（含重名标记） |
| `regions` | INT AUTO_INCREMENT | `uk_regions_name(name)` UNIQUE | 地区字典 |
| `movie_credits` | `(movie_id, person_id, role_type)` PK | — | 演职人员 N:N 关联 |
| `movie_genres` | `(movie_id, type_num)` PK | — | 类型 N:N 关联 |
| `movie_regions` | `(movie_id, region_id)` PK | — | 地区 N:N 关联 |
| `movie_ratings` | `movie_id` (PK) | — | 评分 1:1 |
| `douban_ids` | `douban_id` (PK) | `idx_source(type_num, interval_id)`, `idx_acquired`, `idx_scraped`, `idx_task` | 豆瓣 ID 资产 |
| `crawl_progress` | INT AUTO_INCREMENT | `uk_type_interval(type_num, interval_id)` UNIQUE | 爬取进度+类型字典 |
| `users` | INT AUTO_INCREMENT | `uk_username(username)` UNIQUE, `uuid` UNIQUE | 用户 |
| `permissions` | `code` VARCHAR(32) PK | — | 权限字典 (14 条) |
| `user_permissions` | `(user_id, permission_code)` PK | FK→users, FK→permissions | 用户权限 N:N |
| `task_history` | BIGINT (snowflake) PK | `idx_admin_id`, `idx_status`, `idx_task_type`, `idx_created_at` | 任务历史 |
| `task_failures` | INT AUTO_INCREMENT | `idx_status`, `idx_claimed_by`, `idx_task`, `idx_kind` | 失败任务 (18 列) |
| `movie_review` | `review_id` (PK) | `idx_movie(movie_id)`, `idx_status` | 长评待爬表 |
| `movie_style_tag` | INT UNSIGNED AUTO_INCREMENT | `uk_name_dim(name, dimension)` UNIQUE | AI 风格标签字典 |
| `movie_style` | `(movie_id, tag_id)` PK | `idx_tag`, FK→movies, FK→style_tag | 电影↔风格标签 N:N |
| `review_summary` | INT UNSIGNED AUTO_INCREMENT | `uk_movie_id(movie_id)` UNIQUE, `idx_status` | AI 长评总结 |
| `playlists` | BIGINT AUTO_INCREMENT | `idx_sort`, `idx_created_by`, `idx_created_at`, `idx_publish_at` | 管理员片单 |
| `duplicate_name` | INT AUTO_INCREMENT | `uk_pair(person_id1, person_id2)` UNIQUE | 演职人员重名管理 |
| `user_movie_status` | `(user_id, movie_id)` PK | `idx_user_want`, `idx_user_watched`, `idx_user_fav` | 用户标记快照 |
| `user_action_log` | BIGINT (snowflake) PK | `idx_ual_user_movie`, `idx_ual_user_time`, `idx_ual_reverted` | 行为操作流水 |
| `user_tag_score` | `(user_id, dimension, label)` PK | `idx_uts_user_score(user_id, score DESC)` | 用户标签偏好分数 |
| `config_score_weight` | `config_key` VARCHAR(32) PK | — | 评分权重配置 (25 条种子) |
| `movies_history` | INT AUTO_INCREMENT | `idx_movie(movie_id)` | 电影变更历史 |
| `people_history` | INT AUTO_INCREMENT | `idx_person(person_id)` | 人员变更历史 |
| `movie_credits_history` | INT AUTO_INCREMENT | `idx_mc(movie_id, person_id)` | 演职人员变更历史 |
| `movie_genres_history` | INT AUTO_INCREMENT | `idx_mg(movie_id)` | 类型关联变更历史 |
| `movie_regions_history` | INT AUTO_INCREMENT | `idx_mr(movie_id)` | 地区关联变更历史 |

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

> **迁移记录**：`id` 已通过 `upgrade_20260520_user_behavior.sql` 从 INT 升级为 BIGINT，所有关联表（`movie_ratings`、`movie_review`、`movie_credits` 等 10 张）同步修改。

| 写入方 | 读取方 |
|--------|--------|
| `crawler/storage.save_movie_basic()` — INSERT | 管理端列表/详情 |
| `routes/admin/movie_routes` — PATCH 编辑 | 用户端列表/详情 |
| `routes/admin/poster_routes` — 更新 poster_url | 爬虫查重（douban_id 幂等） |

### 2.2 people — 演职人员

```sql
CREATE TABLE people (
  id            INT           NOT NULL AUTO_INCREMENT,
  name          VARCHAR(128)  NOT NULL,
  douban_id     VARCHAR(64)   DEFAULT NULL,
  admin_id      INT           NOT NULL DEFAULT 0  COMMENT '录入的管理员ID，0=爬虫自动录入',
  is_duplicate  TINYINT       NOT NULL DEFAULT 0  COMMENT '重名标记：0=无重名/已确认, 1=待确认重名, -1=无效重复',
  created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  INDEX idx_people_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

> **迁移记录**：`admin_id`、`is_duplicate` 两列由 `upgrade_20250515_people_duplicate.sql` 加入。同一人可能对应多个 `douban_id`（别名/跨语言），不设 UNIQUE 约束。

### 2.3 regions — 地区字典

```sql
CREATE TABLE regions (
  id          INT           NOT NULL AUTO_INCREMENT,
  name        VARCHAR(64)   NOT NULL,
  created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_regions_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

> **迁移记录**：`uk_regions_name` UNIQUE 索引由 `migrate_regions_unique_name.sql` 加入。

### 2.4 movie_credits — 演职人员关联

```sql
CREATE TABLE movie_credits (
  movie_id   BIGINT        NOT NULL,
  person_id  INT           NOT NULL,
  role_type  VARCHAR(16)   NOT NULL  COMMENT 'director / actor / writer / producer / …',
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
  movie_id  BIGINT  NOT NULL,
  type_num  INT     NOT NULL,
  PRIMARY KEY (movie_id, type_num)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

> `type_num` 逻辑引用 `crawl_progress.type_num`（豆瓣类型编号），非外键约束。

### 2.6 movie_regions — 电影地区关联

```sql
CREATE TABLE movie_regions (
  movie_id   BIGINT  NOT NULL,
  region_id  INT     NOT NULL,
  PRIMARY KEY (movie_id, region_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 2.7 movie_ratings — 电影评分

```sql
CREATE TABLE movie_ratings (
  movie_id      BIGINT         NOT NULL,
  average       DECIMAL(3,1)   DEFAULT NULL,
  `count`       INT            NOT NULL DEFAULT 0,
  distribution  JSON           DEFAULT NULL  COMMENT '{"1":0.05,"2":0.03,"3":0.15,"4":0.40,"5":0.37}',
  created_at    DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (movie_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 2.8 douban_ids — 豆瓣电影 ID 资产

```sql
CREATE TABLE douban_ids (
  douban_id     VARCHAR(32)   NOT NULL PRIMARY KEY,
  title         VARCHAR(128)  NOT NULL,
  source        VARCHAR(32)   NOT NULL DEFAULT 'dashboard_api',
  type_num      INT           DEFAULT NULL,
  interval_id   VARCHAR(16)   DEFAULT NULL,
  admin_id      INT           DEFAULT NULL,
  is_acquired   TINYINT(1)    NOT NULL DEFAULT 0,
  is_scraped    TINYINT(1)    NOT NULL DEFAULT 0,
  acquired_at   DATETIME      DEFAULT NULL,
  task_id       BIGINT        DEFAULT NULL,
  created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_acquired (is_acquired),
  INDEX idx_scraped (is_scraped),
  INDEX idx_task (task_id),
  INDEX idx_source (type_num, interval_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**状态机**：

```
is_scraped=0, is_acquired=0 → 未认领（movie_crawl 写入）
is_scraped=0, is_acquired=1 → 已认领，排队爬取中
is_scraped=1, is_acquired=1 → 终态：已爬取完成（不可释放/重认领）
```

### 2.9 crawl_progress — 爬取进度 + 类型字典

```sql
CREATE TABLE crawl_progress (
  id           INT          NOT NULL AUTO_INCREMENT,
  type_num     INT          NOT NULL DEFAULT 0,
  interval_id  VARCHAR(32)  NOT NULL DEFAULT '',
  type_name    VARCHAR(64)  NOT NULL DEFAULT '',
  is_published TINYINT(1)   NOT NULL DEFAULT 0,
  douban_total INT          NOT NULL DEFAULT 0,
  ids_fetched  INT          NOT NULL DEFAULT 0  COMMENT '已从榜单获取的 douban_id 数量',
  PRIMARY KEY (id),
  UNIQUE KEY uk_type_interval (type_num, interval_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

> `crawl_progress` 承担双重角色：既是豆瓣类型字典（`type_num → type_name`），也是爬取进度跟踪表。`ids_fetched` 列由 `migrate_add_ids_fetched.sql` 加入。

---

## 三、用户与权限（3 张）

### 3.1 users — 用户

```sql
CREATE TABLE users (
  id            INT            NOT NULL AUTO_INCREMENT,
  uuid          BIGINT         NOT NULL UNIQUE,
  username      VARCHAR(64)    NOT NULL,
  password_hash VARCHAR(256)   NOT NULL,
  display_name  VARCHAR(64)    NOT NULL DEFAULT '',
  avatar_url    VARCHAR(2048)  DEFAULT 'https://movie-poster.tos-cn-guangzhou.volces.com/user-avatar/default-avatar.png',
  is_active     TINYINT(1)     NOT NULL DEFAULT 1,
  created_at    DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

> **安全设计**：`password_hash` 通过 bcrypt 加盐存储，不存明文；`uuid` 为 snowflake ID，用于对外暴露时替代自增 `id`。

> **迁移记录**：`avatar_url` 列由 `add_avatar_column.py` 加入，默认值为火山引擎 TOS 上的默认头像。`VARCHAR(2048)` 长度兼容 TOS 长签名 URL。

### 3.2 permissions — 权限字典

```sql
CREATE TABLE permissions (
  code        VARCHAR(32)   NOT NULL PRIMARY KEY,
  name        VARCHAR(64)   NOT NULL,
  description VARCHAR(256)  NOT NULL DEFAULT ''
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**14 条种子权限**：

| code | 名称 | 说明 |
|------|------|------|
| `user:manage` | 用户管理 | 创建/禁用/恢复/删除用户，分配权限 |
| `crawler:task:read` | 任务只读 | 查看爬取进度、任务历史 |
| `crawler:task:write` | 任务提交 | 提交 8 种爬虫任务 |
| `crawler:failure:manage` | 失败管理 | 认领/释放/解决/重试失败任务 |
| `movie:manage` | 电影管理 | 编辑/上下架电影及关联数据 |
| `movie:read` | 查看电影数据 | 只读访问电影详情 |
| `comment:read` | 评论查看 | 查看长评/短评列表 |
| `comment:manage` | 评论管理 | 长评/短评上下架管理 |
| `system:monitor` | 系统监控 | 查看实时状态/队列/日志/限流事件 |
| `infra:proxy:read` | 代理查看 | 查看代理列表和下拉选项 |
| `infra:proxy:manage` | 代理管理 | 增删改代理+连通性测试 |
| `infra:cookie:read` | Cookie 查看 | 查看 Cookie 列表和下拉选项 |
| `infra:cookie:manage` | Cookie 管理 | 增删改 Cookie+有效性测试 |
| `infra:sensitive:read` | 敏感信息查看 | 查看代理密码、完整 Cookie 值 |

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

> 没有任何权限的登录用户为普通用户（role = `user`），有权限的用户为管理员（role = `admin`）。

---

## 四、任务与日志（5 张）

### 4.1 task_history — 任务历史

```sql
CREATE TABLE task_history (
  id          BIGINT        PRIMARY KEY  COMMENT 'snowflake ID',
  admin_id    INT           NOT NULL,
  task_type   VARCHAR(32)   NOT NULL     COMMENT 'movie_crawl / review_crawl / comment_crawl / director_crawl / ai_review_summary / ai_wordcloud / ...',
  task_params JSON          COMMENT      '任务提交时的完整参数',
  parent_task_id BIGINT     NOT NULL DEFAULT 0,
  status      VARCHAR(16)   NOT NULL DEFAULT 'submitted' COMMENT 'submitted / running / done / failed',
  message     VARCHAR(512)  DEFAULT NULL,
  elapsed_ms  INT           DEFAULT NULL,
  created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_admin_id (admin_id),
  INDEX idx_status (status),
  INDEX idx_task_type (task_type),
  INDEX idx_created_at (created_at),
  CONSTRAINT fk_th_admin FOREIGN KEY (admin_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

> **迁移记录**：`fk_th_admin` 外键已通过 `drop_task_history_fk.sql` 移除（用户删除时保留任务历史）。

**8 种任务类型**：

| task_type | 说明 |
|-----------|------|
| `movie_crawl` | 按类型+评分区间批量爬取豆瓣 ID |
| `movie_scrape_task` | 单个电影详情页爬取 |
| `movie_detail_crawl` | movie_crawl 派生的子任务（详情+演职人员） |
| `review_crawl` | 爬取长评摘要列表 |
| `review_body_crawl` | 爬取长评正文 |
| `comment_crawl` | 爬取短评列表 |
| `director_crawl` | 存量演职人员补录 |
| `ai_review_summary` | AI 长评总结（子任务） |

### 4.2 task_failures — 失败任务

```sql
CREATE TABLE task_failures (
  id                INT            NOT NULL AUTO_INCREMENT PRIMARY KEY,
  task_id           BIGINT         NOT NULL DEFAULT 0,
  worker_id         INT            NOT NULL DEFAULT 0,
  task_json         JSON           NOT NULL,
  event_type        VARCHAR(16)    NOT NULL DEFAULT 'failure' COMMENT 'failure / cancelled',
  kind              VARCHAR(32)    NOT NULL DEFAULT 'unknown' COMMENT 'network / timeout / parse / storage / abuse / validation / browser / unknown',
  failure_layer     VARCHAR(16)    NOT NULL DEFAULT 'crawler' COMMENT 'crawler / storage / system',
  reason            VARCHAR(1024)  DEFAULT NULL,
  admin_id          INT            NOT NULL DEFAULT 0,
  status            VARCHAR(16)    NOT NULL DEFAULT 'pending' COMMENT 'pending / claimed / resolved',
  claimed_by        INT            NOT NULL DEFAULT 0,
  claimed_at        DATETIME       DEFAULT NULL,
  resolved_at       DATETIME       DEFAULT NULL,
  parent_failure_id INT            NOT NULL DEFAULT 0,
  retry_count       INT            NOT NULL DEFAULT 0,
  scope             VARCHAR(16)    NOT NULL DEFAULT 'batch' COMMENT 'batch / item',
  item_douban_id    VARCHAR(32)    NOT NULL DEFAULT '',
  item_title        VARCHAR(256)   NOT NULL DEFAULT '',
  snapshot          JSON           DEFAULT NULL COMMENT 'AI 调用失败时的执行现场快照',
  created_at        DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at        DATETIME       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_status (status),
  INDEX idx_claimed_by (claimed_by),
  INDEX idx_task (task_id),
  INDEX idx_kind (kind)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**状态机**：`pending（待处理） → claimed（已认领） → resolved（已解决，可重爬）`

### 4.3 movie_review — 长评待爬表

```sql
CREATE TABLE movie_review (
  review_id     VARCHAR(32)   NOT NULL PRIMARY KEY  COMMENT '豆瓣长评ID',
  movie_id      BIGINT        NOT NULL,
  subject_id    VARCHAR(32)   NOT NULL               COMMENT '豆瓣电影subject_id',
  title         VARCHAR(256)  NOT NULL DEFAULT '',
  author        VARCHAR(64)   NOT NULL DEFAULT '',
  useful_count  INT           NOT NULL DEFAULT 0,
  `date`        VARCHAR(16)   NOT NULL DEFAULT '',
  status        VARCHAR(16)   NOT NULL DEFAULT 'pending' COMMENT 'pending / done / failed',
  created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_movie (movie_id),
  INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 4.4 movie_style_tag — AI 风格标签字典

```sql
CREATE TABLE movie_style_tag (
  id        INT UNSIGNED  AUTO_INCREMENT PRIMARY KEY,
  name      VARCHAR(32)   NOT NULL               COMMENT '风格名称（如 黑暗压抑、非线性叙事）',
  dimension VARCHAR(16)   NOT NULL DEFAULT ''    COMMENT 'overall | plot | visual | narrative | pacing',
  UNIQUE KEY uk_name_dim (name, dimension)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

> **迁移记录**：`dimension` 列由 `upgrade_20260519_movie_style_tag.sql` 加入，唯一键从 `uk_name` 升级为 `uk_name_dim(name, dimension)`——同名标签在不同维度下不冲突。

**5 维度**：overall（整体）、plot（剧情）、visual（画面）、narrative（叙事）、pacing（节奏）

### 4.5 movie_style — 电影↔风格标签关联

```sql
CREATE TABLE movie_style (
  movie_id   BIGINT          NOT NULL,
  tag_id     INT UNSIGNED    NOT NULL,
  confidence DECIMAL(2,1)    NOT NULL DEFAULT 1.0  COMMENT 'AI 可信度 0.0~1.0',
  PRIMARY KEY (movie_id, tag_id),
  INDEX idx_tag (tag_id),
  CONSTRAINT fk_ms_movie FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE,
  CONSTRAINT fk_ms_tag   FOREIGN KEY (tag_id)  REFERENCES movie_style_tag(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 五、AI 与内容（1 张）

### 5.1 review_summary — AI 长评总结

```sql
CREATE TABLE review_summary (
  id            INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  movie_id      INT           NOT NULL                COMMENT '关联电影ID',
  full_summary  TEXT          COMMENT '长评综合总结文本',
  review_tags   JSON          COMMENT '评论标签数组 ["悬疑反转","人性探讨",...]',
  status        VARCHAR(20)   NOT NULL DEFAULT 'pending' COMMENT 'pending / done / failed',
  created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_movie_id (movie_id),
  KEY idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

> 由 `create_review_summary_table.sql` 迁移加入。每部电影最多一条总结，通过 DeepSeek 大模型对已上架长评进行语义聚合生成。

---

## 六、片单（1 张）

### 6.1 playlists — 管理员推荐片单

```sql
CREATE TABLE playlists (
  id           BIGINT        NOT NULL AUTO_INCREMENT,
  title        VARCHAR(128)  NOT NULL,
  description  TEXT,
  cover_url    VARCHAR(512)  DEFAULT '',
  movie_ids    JSON          NOT NULL               COMMENT '电影ID有序列表 [38,39,44,47,53]',
  sort_order   INT           DEFAULT 0,
  is_published TINYINT(1)    DEFAULT 0,
  publish_at   DATETIME      DEFAULT NULL            COMMENT '计划上架时间（NULL=立即）',
  unpublish_at DATETIME      DEFAULT NULL            COMMENT '计划下架时间（NULL=永久）',
  created_by   INT           NOT NULL,
  created_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  INDEX idx_sort        (sort_order, is_published),
  INDEX idx_created_by  (created_by),
  INDEX idx_created_at  (created_at),
  INDEX idx_publish_at  (publish_at),
  CONSTRAINT fk_playlist_creator FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

> 由 `upgrade_202507_playlists.sql` 迁移加入。支持定时上下架（`publish_at` / `unpublish_at` 时间窗口），前端按 `sort_order` 轮播展示。

---

## 七、演职人员管理（1 张）

### 7.1 duplicate_name — 演职人员重名管理

```sql
CREATE TABLE duplicate_name (
  id               INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
  name             VARCHAR(128) NOT NULL,
  person_id1       INT          NOT NULL,
  person_id2       INT          NOT NULL                COMMENT '保证 person_id1 < person_id2',
  is_checked       TINYINT      NOT NULL DEFAULT 0      COMMENT '0=待处理 1=已处理',
  created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  checked_at       DATETIME     NULL,
  operate_admin_id INT          NULL,
  UNIQUE KEY uk_pair (person_id1, person_id2)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

> 由 `upgrade_20250515_people_duplicate.sql` 迁移加入。`person_id1 < person_id2` 约束保证同一对人只记录一条。

---

## 八、用户行为评分（4 张）

> 全部由 `upgrade_20260520_user_behavior.sql` 迁移加入。

### 8.1 user_movie_status — 用户-电影标记快照

```sql
CREATE TABLE user_movie_status (
  user_id       INT       NOT NULL,
  movie_id      BIGINT    NOT NULL,
  want_watch    TINYINT   NOT NULL DEFAULT 0,
  watching      TINYINT   NOT NULL DEFAULT 0,
  watched       TINYINT   NOT NULL DEFAULT 0,
  favorite      TINYINT   NOT NULL DEFAULT 0,
  reviewed      TINYINT   NOT NULL DEFAULT 0,
  updated_at    DATETIME  NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, movie_id),
  INDEX idx_user_want   (user_id, want_watch),
  INDEX idx_user_watched (user_id, watched),
  INDEX idx_user_fav    (user_id, favorite),
  CONSTRAINT fk_ums_user  FOREIGN KEY (user_id)  REFERENCES users(id)  ON DELETE CASCADE,
  CONSTRAINT fk_ums_movie FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

> 每用户每电影一行，5 种标记（想看/在看/看过/收藏/已评论）各自 TINYINT。用户点「看过」后解锁评论入口。

### 8.2 user_action_log — 用户行为操作流水

```sql
CREATE TABLE user_action_log (
  id              BIGINT        NOT NULL               COMMENT 'snowflake ID',
  user_id         INT           NOT NULL,
  movie_id        BIGINT        NOT NULL,
  action          VARCHAR(16)   NOT NULL               COMMENT 'want_watch / watching / watched / favorite / comment',
  score_delta     DECIMAL(8,4)  NOT NULL DEFAULT 0     COMMENT '本次操作总计分值（正=加分，负=回滚）',
  tag_deltas_json JSON          DEFAULT NULL           COMMENT '[{"dim":"director","label":"吕克·贝松","delta":2.0},...]',
  reverted_at     DATETIME      DEFAULT NULL           COMMENT '非空=已回滚，值为回滚时间',
  created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  INDEX idx_ual_user_movie (user_id, movie_id),
  INDEX idx_ual_user_time  (user_id, created_at DESC),
  INDEX idx_ual_reverted   (reverted_at),
  CONSTRAINT fk_ual_user  FOREIGN KEY (user_id)  REFERENCES users(id)  ON DELETE CASCADE,
  CONSTRAINT fk_ual_movie FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 8.3 user_tag_score — 用户-标签偏好分数聚合

```sql
CREATE TABLE user_tag_score (
  user_id       INT           NOT NULL,
  dimension     VARCHAR(16)   NOT NULL  COMMENT 'era / region / director / actor / genre / overall / plot / visual / narrative / pacing',
  label         VARCHAR(128)  NOT NULL  COMMENT '标签文本（冗余存储，避免 JOIN）',
  score         DECIMAL(8,4)  NOT NULL DEFAULT 0,
  last_action   VARCHAR(16)   DEFAULT NULL,
  updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, dimension, label),
  INDEX idx_uts_user_score (user_id, score DESC),
  CONSTRAINT fk_uts_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

> `label` 冗余标签文本，避免查询时 JOIN `people` / `movie_style_tag` 表，实现单表画像查询。

**10 维度**：

| 维度 | 来源 | 示例 label |
|------|------|-----------|
| `era` | 年代 | "1990s" |
| `region` | 地区 | "美国" |
| `director` | 导演 | "克里斯托弗·诺兰" |
| `actor` | 演员 | "梁朝伟"（带排名衰减） |
| `genre` | 豆瓣分类 | "悬疑" |
| `overall` | AI 整体风格 | "黑暗压抑" |
| `plot` | AI 剧情风格 | "非线性叙事" |
| `visual` | AI 画面风格 | "冷色调" |
| `narrative` | AI 叙事风格 | "碎片化" |
| `pacing` | AI 节奏风格 | "紧张" |

### 8.4 config_score_weight — 评分权重配置（热加载）

```sql
CREATE TABLE config_score_weight (
  config_key    VARCHAR(32)   NOT NULL PRIMARY KEY,
  config_value  DECIMAL(4,2)  NOT NULL,
  description   VARCHAR(128)  NOT NULL DEFAULT '',
  updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**种子数据（25 条）**：

| 类别 | config_key 示例 | 默认值 |
|------|----------------|--------|
| 操作行为权重 | `action.want_watch` / `action.watched` / `action.favorite` / `action.comment` | 1.0 / 2.0 / 1.5 / 3.0 |
| 维度基础权重 | `dim.director` / `dim.actor` / `dim.era` / ... | 1.0 / 0.8 / 0.3 / ... |
| 演员排名衰减 | `actor.decay.1` ~ `actor.decay.5` | 1.0 → 0.40 逐名递减 |
| 时间衰减 | `decay.window_30d` / `decay.window_180d` / ... | 1.0 → 0.2 逐窗口递减 |
| 推荐引擎 | `recommend.cv_threshold` | 0.5（变异系数阈值） |

> 权重配置表支持 **运行时热加载**：UPDATE 后无需重启服务，推荐引擎下次查询即可读取最新权重。

---

## 九、版本历史表（5 张）

> 每张历史表结构 = 对应主表的全量列 + `change_type`（update/delete）+ `changed_by`（操作人）。由 `crawler/storage.py` 在每次写操作时同步写入，变更可追溯到人。

| 表名 | 对应主表 | 主键 | 索引 |
|------|---------|------|------|
| `movies_history` | `movies` | INT AUTO_INCREMENT | `idx_movie(movie_id)` |
| `people_history` | `people` | INT AUTO_INCREMENT | `idx_person(person_id)` |
| `movie_credits_history` | `movie_credits` | INT AUTO_INCREMENT | `idx_mc(movie_id, person_id)` |
| `movie_genres_history` | `movie_genres` | INT AUTO_INCREMENT | `idx_mg(movie_id)` |
| `movie_regions_history` | `movie_regions` | INT AUTO_INCREMENT | `idx_mr(movie_id)` |

---

## 十、迁移脚本执行顺序

新环境从零部署时，按以下顺序执行：

| 序号 | 脚本 | 新增表 | ALTER 现有表 |
|:----:|------|:------:|:------------:|
| 1 | `db_init/mysql/init.sql` | 22 张基础表 | — |
| 2 | `add_avatar_column.py` | — | `users.avatar_url` |
| 3 | `add_regions_name_unique.sql` | — | `regions.uk_regions_name` |
| 4 | `migrate_add_ids_fetched.sql` | — | `crawl_progress.ids_fetched` |
| 5 | `drop_task_history_fk.sql` | — | 移除 `fk_th_admin` 外键 |
| 6 | `create_review_summary_table.sql` | `review_summary` | — |
| 7 | `upgrade_20250515_people_duplicate.sql` | `duplicate_name` | `people.admin_id`, `people.is_duplicate` |
| 8 | `upgrade_202507_playlists.sql` | `playlists` | — |
| 9 | `upgrade_20260519_movie_style_tag.sql` | — | `movie_style_tag.dimension`, `movie_style.confidence`, uk 重定义为 `(name, dimension)` |
| 10 | `upgrade_20260520_user_behavior.sql` | `user_movie_status` `user_action_log` `user_tag_score` `config_score_weight` | `movies.id` → BIGINT（级联 10 表） |

---

## 十一、安全设计要点

| 安全机制 | 实现方式 |
|----------|---------|
| SQL 注入防护 | 所有 SQL 走 `%s` 占位符 + aiomysql 参数化，`query_builder.py` 禁止 `;` / `UNION` / `DROP` 等关键字 |
| 密码存储 | `users.password_hash` 通过 bcrypt 加盐哈希，不存明文 |
| 外键一致 | CASCADE 删除（用户删除时级联清理关联权限、行为数据）；RESTRICT 删除（片单创建者不可随意删除） |
| 变更追溯 | 5 张 `_history` 表全量快照 + `change_type` + `changed_by`，每次写操作同步归档 |
| 权限细粒度 | 14 条权限码，N:N 分配，前端路由 + 后端装饰器双重校验 |

---

*最后更新：2026-05-24*
