
-- 创建电影评论AI总结表
CREATE TABLE IF NOT EXISTS `review_summary` (
  `id` int UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `movie_id` int NOT NULL COMMENT '关联电影ID',
  `full_summary` text COMMENT '长评综合总结',
  `review_tags` json COMMENT '评论标签数组',
  `status` varchar(20) NOT NULL DEFAULT 'pending' COMMENT '状态：pending=待生成, done=生成成功, failed=生成失败',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_movie_id` (`movie_id`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='电影评论AI总结表';
