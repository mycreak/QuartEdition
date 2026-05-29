-- 迁移: task_failures 表去除冗余列
-- 日期: 2026-05-29
-- 原因: task_json / admin_id / event_type 与 task_history 表冗余
--       查询时通过 LEFT JOIN task_history 获取
-- 删除列: task_json, admin_id, event_type (共 3 列)
-- 执行方式: mysql -u root -p movie_db < scripts/upgrade_20260529_task_failures_dedup.sql

ALTER TABLE task_failures
  DROP COLUMN task_json,
  DROP COLUMN admin_id,
  DROP COLUMN event_type;
