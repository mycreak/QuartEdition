import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import init_mysql, close_mysql
from db.mysql import get_mysql_pool
import bcrypt
from utils.snowflake import init_snowflake, generate_id

init_snowflake(machine_id=1)

SQLS = [
    """CREATE TABLE IF NOT EXISTS users (
      id            INT           NOT NULL AUTO_INCREMENT,
      uuid          BIGINT        NOT NULL UNIQUE,
      username      VARCHAR(64)   NOT NULL,
      password_hash VARCHAR(256)  NOT NULL,
      display_name  VARCHAR(64)   NOT NULL DEFAULT '',
      is_active     TINYINT(1)    NOT NULL DEFAULT 1,
      created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at    DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      UNIQUE KEY uk_username (username)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    """CREATE TABLE IF NOT EXISTS permissions (
      code        VARCHAR(32)  NOT NULL,
      name        VARCHAR(64)  NOT NULL,
      description VARCHAR(256) NOT NULL DEFAULT '',
      PRIMARY KEY (code)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    """CREATE TABLE IF NOT EXISTS user_permissions (
      user_id         INT         NOT NULL,
      permission_code VARCHAR(32) NOT NULL,
      granted_by      INT         NOT NULL DEFAULT 0,
      granted_at      DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (user_id, permission_code),
      CONSTRAINT fk_up_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
      CONSTRAINT fk_up_perm FOREIGN KEY (permission_code) REFERENCES permissions(code) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    """CREATE TABLE IF NOT EXISTS task_history (
      id              BIGINT          PRIMARY KEY COMMENT 'snowflake ID',
      admin_id        INT             NOT NULL COMMENT '提交人 user_id',
      task_type       VARCHAR(32)     NOT NULL COMMENT 'movie_crawl / review_crawl / comment_crawl / director_crawl / ai_wordcloud',
      task_category   VARCHAR(16)     NOT NULL DEFAULT 'browser' COMMENT 'api | browser — 两大爬虫路径',
      parent_task_id  BIGINT          DEFAULT NULL COMMENT '父任务 ID，子任务归属',
      task_params     JSON            COMMENT '任务提交时的完整参数',
      status          VARCHAR(16)     NOT NULL DEFAULT 'submitted'
                        COMMENT 'submitted / running / done / failed',
      message         VARCHAR(512)    DEFAULT NULL COMMENT '完成/失败时的描述',
      elapsed_ms      INT             DEFAULT NULL COMMENT '执行耗时（毫秒），done/failed 时填充',
      created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      INDEX idx_admin_id (admin_id),
      INDEX idx_status (status),
      INDEX idx_category (task_category),
      INDEX idx_task_type (task_type),
      INDEX idx_created_at (created_at),
      INDEX idx_parent (parent_task_id),
      CONSTRAINT fk_th_admin FOREIGN KEY (admin_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    """INSERT INTO permissions (code, name, description) VALUES
      ('user:manage',          '用户管理',      '创建/禁用/恢复/删除用户，分配权限'),
      ('crawler:task:read',    '任务只读',      '查看爬取进度、任务历史'),
      ('crawler:task:write',   '任务提交',      '提交爬虫任务'),
      ('crawler:failure:manage','失败管理',      '认领/释放/解决失败任务'),
      ('movie:manage',        '电影管理',      '编辑/上下架 movies/people/credits/genres/regions'),
      ('movie:read',           '查看电影数据',  '只读访问电影详情'),
      ('comment:read',         '评论查看',      '查看长评/短评列表'),
      ('comment:manage',       '评论管理',      '长评/短评上下架管理'),
      ('system:monitor',       '系统监控',      '查看实时状态/队列/日志/限流事件'),
      ('infra:proxy:read',     '代理查看',      '查看代理列表和下拉选项'),
      ('infra:proxy:manage',   '代理管理',      '增删改代理+连通性测试'),
      ('infra:cookie:read',    'Cookie查看',    '查看Cookie列表和下拉选项'),
      ('infra:cookie:manage',  'Cookie管理',    '增删改Cookie+有效性测试'),
      ('infra:sensitive:read', '敏感信息查看',  '查看代理密码、完整Cookie值')
    ON DUPLICATE KEY UPDATE name=VALUES(name), description=VALUES(description)""",

    # P1 — douban_id 资产表
    """CREATE TABLE IF NOT EXISTS douban_ids (
      douban_id     VARCHAR(32)   NOT NULL PRIMARY KEY COMMENT '豆瓣电影ID',
      title         VARCHAR(128)  NOT NULL COMMENT '电影名',
      source        VARCHAR(32)   NOT NULL DEFAULT 'dashboard_api'
                        COMMENT '来源: dashboard_api / manual',
      type_num      INT           DEFAULT NULL COMMENT '电影类型编号',
      interval_id   VARCHAR(16)   DEFAULT NULL COMMENT '评分区间',
      admin_id      INT           DEFAULT NULL COMMENT '认领人 user_id',
      is_acquired   TINYINT(1)    NOT NULL DEFAULT 0 COMMENT '是否已被认领为爬取任务',
      is_scraped    TINYINT(1)    NOT NULL DEFAULT 0 COMMENT '0=未爬 1=已成功爬取电影详情',
      acquired_at   DATETIME      DEFAULT NULL,
      task_id       BIGINT        DEFAULT NULL COMMENT '关联 task_history.id',
      created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
      INDEX idx_acquired (is_acquired),
      INDEX idx_scraped (is_scraped),
      INDEX idx_task (task_id),
      INDEX idx_source (type_num, interval_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    """CREATE TABLE IF NOT EXISTS crawl_progress (
      id           INT NOT NULL AUTO_INCREMENT,
      type_num     INT NOT NULL DEFAULT 0,
      interval_id  VARCHAR(32) NOT NULL DEFAULT '',
      type_name    VARCHAR(64) NOT NULL DEFAULT '',
      is_published TINYINT(1)  NOT NULL DEFAULT 0,
      douban_total INT         NOT NULL DEFAULT 0,
      ids_fetched  INT         NOT NULL DEFAULT 0 COMMENT '已从榜单获取的 douban_id 数量, 用于分页偏移计算',
      PRIMARY KEY (id),
      UNIQUE KEY uk_type_interval (type_num, interval_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    # P1 — movie_review 长评待爬表（review_crawl 摘要采集 → review_body_crawl 正文爬取）
    """CREATE TABLE IF NOT EXISTS movie_review (
      review_id     VARCHAR(32)   NOT NULL PRIMARY KEY COMMENT '豆瓣长评ID',
      movie_id      INT           NOT NULL COMMENT '本地MySQL movies.id',
      subject_id    VARCHAR(32)   NOT NULL COMMENT '豆瓣电影subject_id',
      title         VARCHAR(256)  NOT NULL DEFAULT '' COMMENT '长评标题',
      author        VARCHAR(64)   NOT NULL DEFAULT '' COMMENT '作者昵称',
      useful_count  INT           NOT NULL DEFAULT 0 COMMENT '赞同数',
      `date`        VARCHAR(16)   NOT NULL DEFAULT '' COMMENT '发布日期',
      status        VARCHAR(16)   NOT NULL DEFAULT 'pending' COMMENT 'pending/done/failed',
      created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at    DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      INDEX idx_movie (movie_id),
      INDEX idx_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    # task_failures 表 — 失败任务记录（服务层依赖）
    """CREATE TABLE IF NOT EXISTS task_failures (
      id                INT           NOT NULL AUTO_INCREMENT PRIMARY KEY,
      task_id           BIGINT        NOT NULL DEFAULT 0,
      worker_id         INT           NOT NULL DEFAULT 0,
      task_json         JSON          NOT NULL,
      event_type        VARCHAR(16)   NOT NULL DEFAULT 'failure' COMMENT 'failure / cancelled',
      kind              VARCHAR(32)   NOT NULL DEFAULT 'unknown' COMMENT 'network / timeout / parse / storage / abuse / validation',
      failure_layer     VARCHAR(16)   NOT NULL DEFAULT 'crawler' COMMENT 'crawler | storage | ai | system — 错误来源层',
      reason            VARCHAR(1024) DEFAULT NULL,
      admin_id          INT           NOT NULL DEFAULT 0,
      status            VARCHAR(16)   NOT NULL DEFAULT 'pending' COMMENT 'pending / claimed / resolved',
      claimed_by        INT           NOT NULL DEFAULT 0,
      claimed_at        DATETIME      DEFAULT NULL,
      resolved_at       DATETIME      DEFAULT NULL,
      parent_failure_id INT           NOT NULL DEFAULT 0,
      retry_count       INT           NOT NULL DEFAULT 0,
      scope             VARCHAR(16)   NOT NULL DEFAULT 'batch' COMMENT 'batch / item',
      item_douban_id    VARCHAR(32)   NOT NULL DEFAULT '',
      item_title        VARCHAR(256)  NOT NULL DEFAULT '',
      snapshot          JSON          DEFAULT NULL COMMENT '执行现场快照',
      created_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at        DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      INDEX idx_status (status),
      INDEX idx_claimed_by (claimed_by),
      INDEX idx_task (task_id),
      INDEX idx_kind (kind),
      INDEX idx_layer (failure_layer)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    # movies 表 — 电影主表（爬虫目标）
    """CREATE TABLE IF NOT EXISTS movies (
      id              INT           NOT NULL AUTO_INCREMENT,
      douban_id       VARCHAR(32)   NOT NULL DEFAULT '',
      title           VARCHAR(256)  NOT NULL DEFAULT '',
      original_title  VARCHAR(256)  NOT NULL DEFAULT '',
      release_year    INT           DEFAULT NULL,
      release_date    VARCHAR(16)   NOT NULL DEFAULT '',
      duration        INT           DEFAULT NULL COMMENT '片长（分钟）',
      poster_url      VARCHAR(2048) DEFAULT NULL,
      is_published    TINYINT(1)    NOT NULL DEFAULT 0,
      imdb_id         VARCHAR(20)   DEFAULT NULL,
      created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at      DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      INDEX idx_douban (douban_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    # movie_ratings 表 — 评分统计
    """CREATE TABLE IF NOT EXISTS movie_ratings (
      movie_id      INT           NOT NULL,
      average       DECIMAL(3,1)  DEFAULT NULL,
      `count`       INT           NOT NULL DEFAULT 0,
      distribution  JSON          DEFAULT NULL COMMENT '{"1": 比例, "2": 比例, ...}',
      created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at    DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (movie_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    # people 表 — 演职人员
    """CREATE TABLE IF NOT EXISTS people (
      id          INT           NOT NULL AUTO_INCREMENT,
      name        VARCHAR(128)  NOT NULL,
      douban_id   VARCHAR(64)   DEFAULT NULL,
      admin_id    INT           NOT NULL DEFAULT 0 COMMENT '录入的管理员ID，0代表爬虫自动录入',
      is_duplicate TINYINT      NOT NULL DEFAULT 0 COMMENT '重名标记：0=无重名/已确认，1=待确认重名，-1=无效重复记录',
      created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at  DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    # duplicate_name 表 — 演职人员重名记录表
    """CREATE TABLE IF NOT EXISTS duplicate_name (
      id              INT AUTO_INCREMENT PRIMARY KEY,
      name            VARCHAR(128) NOT NULL COMMENT '重名姓名',
      person_id1      INT NOT NULL COMMENT '重名人员ID1（保证person_id1 < person_id2）',
      person_id2      INT NOT NULL COMMENT '重名人员ID2',
      is_checked      TINYINT NOT NULL DEFAULT 0 COMMENT '0待处理 1已处理',
      created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      checked_at      DATETIME NULL COMMENT '处理时间',
      operate_admin_id INT NULL COMMENT '处理的管理员ID',
      UNIQUE KEY uk_pair(person_id1, person_id2) COMMENT '唯一约束，避免同一对重名重复写入'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    # movie_credits 表 — 演职人员关联
    """CREATE TABLE IF NOT EXISTS movie_credits (
      movie_id   INT          NOT NULL,
      person_id  INT          NOT NULL,
      role_type  VARCHAR(16)  NOT NULL COMMENT 'director / actor / writer / producer / ...',
      PRIMARY KEY (movie_id, person_id, role_type)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    # regions 表 — 地区字典
    """CREATE TABLE IF NOT EXISTS regions (
      id          INT           NOT NULL AUTO_INCREMENT,
      name        VARCHAR(64)   NOT NULL,
      created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      UNIQUE KEY uk_regions_name (name) COMMENT '地区名称唯一约束，避免重复国家/地区'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    # movie_regions 表 — 电影地区关联
    """CREATE TABLE IF NOT EXISTS movie_regions (
      movie_id   INT NOT NULL,
      region_id  INT NOT NULL,
      PRIMARY KEY (movie_id, region_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    # movie_genres 表 — 电影类型关联
    """CREATE TABLE IF NOT EXISTS movie_genres (
      movie_id  INT NOT NULL,
      type_num  INT NOT NULL,
      PRIMARY KEY (movie_id, type_num)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    # —— 版本历史表（MovieService._write_history 依赖，DDL 首次部署时建表）——
    """CREATE TABLE IF NOT EXISTS movies_history (
      id         INT AUTO_INCREMENT PRIMARY KEY,
      movie_id   INT NOT NULL,
      douban_id  VARCHAR(32) DEFAULT '',
      title      VARCHAR(256) DEFAULT '',
      original_title VARCHAR(256) DEFAULT '',
      release_year INT DEFAULT NULL,
      release_date VARCHAR(16) DEFAULT '',
      duration   INT DEFAULT NULL,
      poster_url VARCHAR(2048) DEFAULT NULL,
      imdb_id    VARCHAR(20) DEFAULT NULL,
      is_published TINYINT(1) DEFAULT 0,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      change_type VARCHAR(16) NOT NULL DEFAULT 'update',
      changed_by VARCHAR(64) NOT NULL DEFAULT 'system',
      INDEX idx_movie (movie_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    """CREATE TABLE IF NOT EXISTS people_history (
      id         INT AUTO_INCREMENT PRIMARY KEY,
      person_id  INT NOT NULL,
      name       VARCHAR(128) DEFAULT '',
      douban_id  VARCHAR(64) DEFAULT NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      change_type VARCHAR(16) NOT NULL DEFAULT 'update',
      changed_by VARCHAR(64) NOT NULL DEFAULT 'system',
      INDEX idx_person (person_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    """CREATE TABLE IF NOT EXISTS movie_credits_history (
      id         INT AUTO_INCREMENT PRIMARY KEY,
      movie_id   INT NOT NULL,
      person_id  INT NOT NULL,
      role_type  VARCHAR(16) DEFAULT '',
      change_type VARCHAR(16) NOT NULL DEFAULT 'update',
      changed_by VARCHAR(64) NOT NULL DEFAULT 'system',
      INDEX idx_mc (movie_id, person_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    """CREATE TABLE IF NOT EXISTS movie_genres_history (
      id         INT AUTO_INCREMENT PRIMARY KEY,
      movie_id   INT NOT NULL,
      type_num   INT DEFAULT NULL,
      change_type VARCHAR(16) NOT NULL DEFAULT 'update',
      changed_by VARCHAR(64) NOT NULL DEFAULT 'system',
      INDEX idx_mg (movie_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    """CREATE TABLE IF NOT EXISTS movie_regions_history (
      id         INT AUTO_INCREMENT PRIMARY KEY,
      movie_id   INT NOT NULL,
      region_id  INT DEFAULT NULL,
      change_type VARCHAR(16) NOT NULL DEFAULT 'update',
      changed_by VARCHAR(64) NOT NULL DEFAULT 'system',
      INDEX idx_mr (movie_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
]

# ── v2 归一化迁移：给已有 task_history / task_failures 补充新列 ──
MIGRATIONS = [
    # task_history 新增：task_category, parent_task_id, elapsed_ms
    "ALTER TABLE task_history ADD COLUMN task_category VARCHAR(16) NOT NULL DEFAULT 'browser' COMMENT 'api | browser' AFTER task_type",
    "ALTER TABLE task_history ADD COLUMN parent_task_id BIGINT DEFAULT NULL COMMENT '父任务 ID' AFTER task_category",
    "ALTER TABLE task_history ADD COLUMN elapsed_ms INT DEFAULT NULL COMMENT '执行耗时（毫秒）' AFTER message",
    # task_failures 新增：failure_layer
    "ALTER TABLE task_failures ADD COLUMN failure_layer VARCHAR(16) NOT NULL DEFAULT 'crawler' COMMENT 'crawler | storage | ai | system' AFTER kind",
]

PERMISSION_CODES = [
    "user:manage",
    "crawler:task:read",
    "crawler:task:write",
    "crawler:failure:manage",
    "movie:manage",
    "movie:read",
    "comment:read",
    "comment:manage",
    "system:monitor",
    "infra:proxy:read",
    "infra:proxy:manage",
    "infra:cookie:read",
    "infra:cookie:manage",
    "infra:sensitive:read",
]

DEFAULT_ADMIN = os.environ.get("ADMIN_USERNAME", "admin1")
DEFAULT_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


async def main():
    await init_mysql()
    pool = get_mysql_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            for sql in SQLS:
                await cur.execute(sql)
                print(f"  [OK] {sql[:70].replace(chr(10),' ')}...")

            # ── 归一化迁移 ──
            for sql in MIGRATIONS:
                try:
                    await cur.execute(sql)
                    short = sql[:60].replace(chr(10),' ')
                    print(f"  [MIG] {short}...")
                except Exception as e:
                    if "Duplicate column" in str(e) or "already exists" in str(e):
                        print(f"  [SKIP] 列已存在")
                    else:
                        print(f"  [WARN] 迁移失败: {e}")

            # 种子超级管理员
            pwd_hash = bcrypt.hashpw(
                DEFAULT_PASSWORD.encode("utf-8"),
                bcrypt.gensalt(rounds=12),
            ).decode("utf-8")
            admin_uuid = generate_id()

            await cur.execute("""
                INSERT INTO users (uuid, username, password_hash, display_name)
                VALUES (%s, %s, %s, '超级管理员')
                ON DUPLICATE KEY UPDATE display_name=VALUES(display_name)
            """, (admin_uuid, DEFAULT_ADMIN, pwd_hash))
            # 兜底：给旧库中 uuid=NULL 的用户补雪花 ID（兼容 uuid 列后加的迁移）
            await cur.execute(
                "UPDATE users SET uuid = %s WHERE uuid IS NULL",
                (generate_id(),),
            )
            await cur.execute("SELECT id FROM users WHERE username = %s", (DEFAULT_ADMIN,))
            admin_id = (await cur.fetchone())["id"]

            for code in PERMISSION_CODES:
                await cur.execute("""
                    INSERT IGNORE INTO user_permissions (user_id, permission_code, granted_by)
                    VALUES (%s, %s, 0)
                """, (admin_id, code))

            print(f"  [OK] 超级管理员已种子: username='{DEFAULT_ADMIN}' id={admin_id} 14 条权限")

    await close_mysql()
    print(f"\n[OK] 用户认证系统初始化完成")


asyncio.run(main())
