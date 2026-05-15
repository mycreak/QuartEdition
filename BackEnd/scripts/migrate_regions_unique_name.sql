-- 迁移: regions 表 name 字段添加唯一索引
-- 用途: 防止重复地区名称，与 POST /admin/regions 唯一性校验配合使用
-- 执行方式: mysql -u root -p movie_db < scripts/migrate_regions_unique_name.sql

-- 1. 清理已存在的重复数据（保留 id 最小的记录）
DELETE r1 FROM regions r1
INNER JOIN regions r2
WHERE r1.id > r2.id AND r1.name = r2.name;

-- 2. 添加唯一索引（ALTER IGNORE 保证已有数据兼容）
CREATE UNIQUE INDEX uk_regions_name ON regions (name);
