-- 评论评分调节因子 — 数据库升级脚本
-- 用途：将用户星级评分作为评论操作权重的调节因子，使差评能降低同类推荐
-- 日期：2026-05-29
-- 依赖：config_score_weight 表已存在（upgrade_20260520_user_behavior.sql）
-- ===================================================

-- 评论评分调节配置（热加载，UPDATE 后无需重启）
INSERT IGNORE INTO config_score_weight (config_key, config_value, description) VALUES
('comment.rating_neutral',    3.0,  '评分基准线（中性点, factor=0），默认 3 星'),
('comment.rating_factor_max', 1.0,  '5星对应的调节因子上限，5星 = action_weight × 1.0'),
('comment.rating_factor_min', -0.5, '1星对应的调节因子下限（负值=差评惩罚），1星 = action_weight × -0.5');

-- 公式说明：
--   rating_factor = factor_max × (rating - neutral) / (5.0 - neutral)    当 rating ≥ neutral
--   rating_factor = factor_min × (neutral - rating) / (neutral - 1.0)    当 rating < neutral
--   effective_weight = action_weight × rating_factor
--   delta = effective_weight × tag.weight
--
-- 示例（默认配置: action_weight=3.0, neutral=3.0, max=1.0, min=-0.5）：
--   5星 → factor=1.00  → effective=+3.00
--   4星 → factor=0.50  → effective=+1.50
--   3星 → factor=0.00  → effective= 0.00
--   2星 → factor=-0.25 → effective=-0.75
--   1星 → factor=-0.50  → effective=-1.50
--
-- 调参建议：
--   - 加大惩罚 → UPDATE config_score_weight SET config_value = -1.0 WHERE config_key = 'comment.rating_factor_min';
--   - 改为对称 → 同上改为 -1.0（与正向对称）
--   - 关闭惩罚 → 同上改为 0.0
