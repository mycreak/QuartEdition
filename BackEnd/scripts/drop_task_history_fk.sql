-- 修复 task_history FK 约束失败（2026-05-19）
-- 问题: admin_id=0 时触发 fk_th_auth_admin → users(id) 约束失败
-- 原因: 系统自动任务 admin_id=0，不关联任何真实用户
-- 解决: 去除 task_history.admin_id 的 FOREIGN KEY 约束
-- 执行前确认 FK 名: SHOW CREATE TABLE task_history;

-- 方式1: 如果 FK 名为 fk_th_auth_admin
ALTER TABLE task_history DROP FOREIGN KEY fk_th_auth_admin;

-- 方式2: 如果 FK 名为 fk_th_admin（旧版 seed_auth.py 中的名字）
-- ALTER TABLE task_history DROP FOREIGN KEY fk_th_admin;

-- 方式3: 如果不确定 FK 名，或上面两个都报错，用这个查
-- SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE
-- WHERE TABLE_NAME='task_history' AND REFERENCED_TABLE_NAME='users';
