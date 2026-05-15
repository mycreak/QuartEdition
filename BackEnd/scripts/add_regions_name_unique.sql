-- 为 regions 表的 name 字段添加唯一索引
-- 防止重复地区名称（应用层已做校验，此索引为数据库最后防线）
--
-- 执行前建议先检查是否有重复数据：
-- SELECT name, COUNT(*) AS cnt FROM regions GROUP BY name HAVING cnt > 1;
-- 若有重复，手动清理后再执行:
-- DELETE r1 FROM regions r1 INNER JOIN regions r2 ON r1.name = r2.name AND r1.id > r2.id;

ALTER TABLE `regions`
  ADD UNIQUE INDEX `uk_regions_name` (`name`);
