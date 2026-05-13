-- 迁移: crawl_progress 表增加 ids_fetched 字段
-- 用途: 跟踪榜单 API 实际已获取的 douban_id 数量, 替代 COUNT douban_ids 计算分页偏移
-- 执行方式: mysql -u root -p movie_db < scripts/migrate_add_ids_fetched.sql

-- 新增字段 (已存在的行默认 0, 与 DDL DEFAULT 0 一致)
ALTER TABLE crawl_progress
  ADD COLUMN ids_fetched INT NOT NULL DEFAULT 0 COMMENT '已从榜单获取的 douban_id 数量, 用于分页偏移计算'
  AFTER douban_total;

-- 回填: 对已有数据的行, 用 douban_ids 实际行数填充 ids_fetched
-- 注意: 如果 douban_ids 混入了手动添加的条目, 回填值会偏大, 后续爬取可能跳过部分榜单页
-- 但这只是一次性损失, 之后再爬取时 ids_fetched 由事务原子写入保证准确性
UPDATE crawl_progress cp
SET cp.ids_fetched = (
    SELECT COUNT(*)
    FROM douban_ids d
    WHERE d.type_num = cp.type_num AND d.interval_id = cp.interval_id
);
