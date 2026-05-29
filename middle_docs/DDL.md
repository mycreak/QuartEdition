-- movie_db.config_score_weight definition

CREATE TABLE `config_score_weight` (
  `config_key` varchar(32) NOT NULL COMMENT '配置键',
  `config_value` decimal(4,2) NOT NULL COMMENT '配置值',
  `description` varchar(128) NOT NULL DEFAULT '' COMMENT '说明',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`config_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户行为评分配置';


-- movie_db.crawl_progress definition

CREATE TABLE `crawl_progress` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  `type_num` int NOT NULL COMMENT '豆瓣类型编号, 如 11=剧情',
  `type_name` varchar(64) NOT NULL DEFAULT '' COMMENT '类型名称, 如 剧情',
  `interval_id` varchar(16) NOT NULL COMMENT '评分区间, 如 100:90',
  `is_published` tinyint(1) NOT NULL DEFAULT '1' COMMENT '0=下架 1=上架',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `douban_total` int NOT NULL DEFAULT '0' COMMENT '豆瓣该类型+区间的总电影数',
  `ids_fetched` int NOT NULL DEFAULT '0' COMMENT '已从榜单获取的 douban_id 数量, 用于分页偏移计算',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_type_interval` (`type_num`,`interval_id`)
) ENGINE=InnoDB AUTO_INCREMENT=857 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='电影爬取进度追踪';


-- movie_db.douban_ids definition

CREATE TABLE `douban_ids` (
  `douban_id` varchar(32) NOT NULL COMMENT '豆瓣电影ID',
  `title` varchar(128) NOT NULL COMMENT '电影名',
  `source` varchar(32) NOT NULL DEFAULT 'dashboard_api' COMMENT '来源: dashboard_api / manual',
  `type_num` int DEFAULT NULL COMMENT '电影类型编号',
  `interval_id` varchar(16) DEFAULT NULL COMMENT '评分区间',
  `admin_id` int DEFAULT NULL COMMENT '手动添加时的操作人',
  `is_acquired` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否已被认领为爬取任务',
  `acquired_at` datetime DEFAULT NULL,
  `task_id` bigint DEFAULT NULL COMMENT '关联 task_history.id',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `is_scraped` tinyint(1) NOT NULL DEFAULT '0' COMMENT '0=未爬 1=已成功爬取',
  PRIMARY KEY (`douban_id`),
  KEY `idx_acquired` (`is_acquired`),
  KEY `idx_task` (`task_id`),
  KEY `idx_source` (`type_num`,`interval_id`),
  KEY `idx_scraped` (`is_scraped`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- movie_db.movie_style_tag definition

CREATE TABLE `movie_style_tag` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(32) NOT NULL COMMENT '风格名称（如 黑暗、温馨、暴力、哲学）',
  `dimension` varchar(16) NOT NULL DEFAULT '' COMMENT 'overall|plot|visual|narrative|pacing',
  `review_status` tinyint NOT NULL DEFAULT '0' COMMENT '0=刚生成未检测 1=相似度<82%无需合并 2=相似度≥82%待确认 3=管理员确认已合并',
  `merged_to_tag_id` int unsigned NOT NULL DEFAULT '0' COMMENT '合并到的已有标签id，0=未合并',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_name_dim` (`name`,`dimension`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- movie_db.movies definition

CREATE TABLE `movies` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `douban_id` varchar(32) DEFAULT NULL COMMENT '豆瓣电影ID',
  `title` varchar(512) NOT NULL,
  `original_title` varchar(512) DEFAULT NULL,
  `release_year` smallint NOT NULL,
  `release_date` date DEFAULT NULL,
  `duration` smallint DEFAULT NULL,
  `poster_url` varchar(2048) DEFAULT NULL,
  `imdb_id` varchar(20) DEFAULT NULL,
  `is_published` tinyint(1) NOT NULL DEFAULT '1' COMMENT '0=下架 1=上架',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_imdb_id` (`imdb_id`),
  UNIQUE KEY `uk_douban_id` (`douban_id`),
  KEY `idx_douban` (`douban_id`)
) ENGINE=InnoDB AUTO_INCREMENT=68 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- movie_db.people definition

CREATE TABLE `people` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `douban_id` varchar(32) DEFAULT NULL COMMENT '豆瓣人员ID',
  `admin_id` int NOT NULL DEFAULT '0' COMMENT '录入的管理员ID，0代表爬虫自动录入',
  `is_duplicate` tinyint NOT NULL DEFAULT '0' COMMENT '重名标记，0=无重名/已确认，1=待确认重名，-1=无效重复记录',
  `name` varchar(256) NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_people_douban` (`douban_id`),
  KEY `idx_people_name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=1478 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- movie_db.permissions definition

CREATE TABLE `permissions` (
  `code` varchar(32) NOT NULL,
  `name` varchar(64) NOT NULL,
  `description` varchar(256) NOT NULL DEFAULT '',
  PRIMARY KEY (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- movie_db.task_failures definition
-- 2026-05-29: 删除 task_json / admin_id / event_type 冗余列，查询时 LEFT JOIN task_history

CREATE TABLE `task_failures` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_id` bigint NOT NULL DEFAULT '0' COMMENT 'snowflake 任务ID',
  `worker_id` int NOT NULL,
  `reason` text NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `kind` varchar(16) NOT NULL DEFAULT 'unknown',
  `failure_layer` varchar(16) NOT NULL DEFAULT 'crawler' COMMENT 'crawler | storage | ai | system',
  `status` varchar(16) NOT NULL DEFAULT 'pending' COMMENT 'pending/claimed/resolved',
  `claimed_by` int NOT NULL DEFAULT '0' COMMENT '认领的管理员 admin_id',
  `claimed_at` datetime DEFAULT NULL,
  `resolved_at` datetime DEFAULT NULL,
  `parent_failure_id` bigint NOT NULL DEFAULT '0' COMMENT '关联的上一次失败记录 ID，首败=0',
  `retry_count` int NOT NULL DEFAULT '0',
  `scope` varchar(10) NOT NULL DEFAULT 'batch' COMMENT 'batch / item',
  `item_douban_id` varchar(32) NOT NULL DEFAULT '' COMMENT '失败的电影 douban_id',
  `item_title` varchar(256) NOT NULL DEFAULT '' COMMENT '失败的电影名',
  `snapshot` json DEFAULT NULL COMMENT '执行现场快照',
  PRIMARY KEY (`id`),
  KEY `idx_created_at` (`created_at`),
  KEY `idx_status` (`status`),
  KEY `idx_scope_status` (`scope`,`status`)
) ENGINE=InnoDB AUTO_INCREMENT=915 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- movie_db.task_history definition

CREATE TABLE `task_history` (
  `id` bigint NOT NULL,
  `admin_id` int NOT NULL,
  `task_type` varchar(32) NOT NULL,
  `task_category` varchar(16) NOT NULL DEFAULT 'browser' COMMENT 'api | browser',
  `parent_task_id` bigint DEFAULT NULL COMMENT '父任务 ID',
  `task_params` json DEFAULT NULL,
  `status` varchar(16) NOT NULL DEFAULT 'submitted',
  `message` varchar(512) DEFAULT NULL,
  `elapsed_ms` int DEFAULT NULL COMMENT '执行耗时（毫秒）',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_admin_id` (`admin_id`),
  KEY `idx_status` (`status`),
  KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- movie_db.users definition

CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `uuid` bigint NOT NULL,
  `username` varchar(64) NOT NULL,
  `password_hash` varchar(256) NOT NULL,
  `display_name` varchar(64) NOT NULL DEFAULT '',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `avatar_url` varchar(255) DEFAULT 'https://movie-poster.tos-cn-guangzhou.volces.com/user-avatar/default-avatar.png',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_username` (`username`),
  UNIQUE KEY `uuid` (`uuid`)
) ENGINE=InnoDB AUTO_INCREMENT=2913 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- movie_db.movie_style definition

CREATE TABLE `movie_style` (
  `movie_id` bigint NOT NULL COMMENT '关联 movies.id',
  `tag_id` int unsigned NOT NULL COMMENT '关联 movie_style_tag.id',
  `confidence` decimal(2,1) NOT NULL DEFAULT '1.0' COMMENT 'AI 可信度 0.0~1.0',
  PRIMARY KEY (`movie_id`,`tag_id`),
  KEY `idx_tag` (`tag_id`),
  CONSTRAINT `fk_ms_movie` FOREIGN KEY (`movie_id`) REFERENCES `movies` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_ms_tag` FOREIGN KEY (`tag_id`) REFERENCES `movie_style_tag` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- movie_db.user_movie_status definition

CREATE TABLE `user_movie_status` (
  `user_id` int NOT NULL COMMENT 'FK users.id',
  `movie_id` bigint NOT NULL COMMENT 'FK movies.id',
  `want_watch` tinyint NOT NULL DEFAULT '0' COMMENT '1=想看',
  `watching` tinyint NOT NULL DEFAULT '0' COMMENT '1=在看',
  `watched` tinyint NOT NULL DEFAULT '0' COMMENT '1=看过',
  `favorite` tinyint NOT NULL DEFAULT '0' COMMENT '1=收藏',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`,`movie_id`),
  KEY `idx_user_want` (`user_id`,`want_watch`),
  KEY `idx_user_watched` (`user_id`,`watched`),
  KEY `idx_user_fav` (`user_id`,`favorite`),
  KEY `fk_ums_movie` (`movie_id`),
  CONSTRAINT `fk_ums_movie` FOREIGN KEY (`movie_id`) REFERENCES `movies` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_ums_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户-电影标记状态（当前快照：想看/在看/看过/收藏）';


-- movie_db.user_permissions definition

CREATE TABLE `user_permissions` (
  `user_id` int NOT NULL,
  `permission_code` varchar(32) NOT NULL,
  `granted_by` int NOT NULL DEFAULT '0',
  `granted_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`,`permission_code`),
  KEY `fk_up_perm` (`permission_code`),
  CONSTRAINT `fk_up_perm` FOREIGN KEY (`permission_code`) REFERENCES `permissions` (`code`) ON DELETE CASCADE,
  CONSTRAINT `fk_up_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- movie_db.user_tag_score definition

CREATE TABLE `user_tag_score` (
  `user_id` int NOT NULL COMMENT 'FK users.id',
  `dimension` varchar(16) NOT NULL COMMENT 'era|region|director|actor|genre|overall|plot|visual|narrative|pacing',
  `label` varchar(128) NOT NULL COMMENT '标签文本（冗余存储，避免 JOIN people/movie_style_tag）',
  `score` decimal(8,4) NOT NULL DEFAULT '0.0000' COMMENT '当前累积分值',
  `last_action` varchar(16) DEFAULT NULL COMMENT '最后一次触发此标签的操作类型',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`,`dimension`,`label`),
  KEY `idx_uts_user_score` (`user_id`,`score` DESC),
  CONSTRAINT `fk_uts_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户-标签分数聚合快照';