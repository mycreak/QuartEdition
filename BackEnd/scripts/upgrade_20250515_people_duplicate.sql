-- 演职人员重名功能数据库升级脚本
-- 执行顺序：依次执行以下SQL即可，无破坏性修改
-- ===================================================
-- 1. 给people表新增admin_id字段
ALTER TABLE people ADD COLUMN IF NOT EXISTS admin_id INT NOT NULL DEFAULT 0 COMMENT '录入的管理员ID，0代表爬虫自动录入' AFTER douban_id;
-- 2. 给people表新增is_duplicate字段
ALTER TABLE people ADD COLUMN IF NOT EXISTS is_duplicate TINYINT NOT NULL DEFAULT 0 COMMENT '重名标记：0=无重名/已确认，1=待确认重名，-1=无效重复记录' AFTER admin_id;
-- 3. 给people.name加索引，加速重名查询
CREATE INDEX IF NOT EXISTS idx_people_name ON people(name);
-- 4. 新建重名记录表duplicate_name
CREATE TABLE IF NOT EXISTS duplicate_name (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  name            VARCHAR(128) NOT NULL COMMENT '重名姓名',
  person_id1      INT NOT NULL COMMENT '重名人员ID1（保证person_id1 < person_id2）',
  person_id2      INT NOT NULL COMMENT '重名人员ID2',
  is_checked      TINYINT NOT NULL DEFAULT 0 COMMENT '0待处理 1已处理',
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  checked_at      DATETIME NULL COMMENT '处理时间',
  operate_admin_id INT NULL COMMENT '处理的管理员ID',
  UNIQUE KEY uk_pair(person_id1, person_id2) COMMENT '唯一约束，避免同一对重名重复写入'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- ===================================================
-- 执行完成校验：
-- 1. DESC people; 能看到admin_id和is_duplicate字段
-- 2. SHOW INDEX FROM people; 能看到idx_people_name索引
-- 3. SHOW TABLES; 能看到duplicate_name表
