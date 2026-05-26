
/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;
DROP TABLE IF EXISTS `config_score_weight`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `config_score_weight` (
  `config_key` varchar(32) NOT NULL COMMENT '配置键',
  `config_value` decimal(4,2) NOT NULL COMMENT '配置值',
  `description` varchar(128) NOT NULL DEFAULT '' COMMENT '说明',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`config_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户行为评分配置';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `crawl_progress`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `douban_ids`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `duplicate_name`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `duplicate_name` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(128) NOT NULL COMMENT '重名姓名',
  `person_id1` int NOT NULL COMMENT '重名人员ID1（保证person_id1 < person_id2）',
  `person_id2` int NOT NULL COMMENT '重名人员ID2',
  `is_checked` tinyint NOT NULL DEFAULT '0' COMMENT '0待处理 1已处理',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `checked_at` datetime DEFAULT NULL COMMENT '处理时间',
  `operate_admin_id` int DEFAULT NULL COMMENT '处理的管理员ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_pair` (`person_id1`,`person_id2`) COMMENT '唯一约束，避免同一对重名重复写入'
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `movie_credits`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `movie_credits` (
  `movie_id` bigint NOT NULL,
  `person_id` bigint NOT NULL,
  `role_type` varchar(20) NOT NULL,
  PRIMARY KEY (`movie_id`,`person_id`,`role_type`),
  KEY `person_id` (`person_id`),
  CONSTRAINT `movie_credits_ibfk_1` FOREIGN KEY (`movie_id`) REFERENCES `movies` (`id`) ON DELETE CASCADE,
  CONSTRAINT `movie_credits_ibfk_2` FOREIGN KEY (`person_id`) REFERENCES `people` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `movie_credits_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `movie_credits_history` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `movie_id` bigint NOT NULL,
  `person_id` bigint NOT NULL,
  `role_type` varchar(20) NOT NULL,
  `change_type` varchar(16) NOT NULL,
  `changed_by` varchar(64) NOT NULL DEFAULT '',
  `changed_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_mc_ver` (`movie_id`,`person_id`,`changed_at`)
) ENGINE=InnoDB AUTO_INCREMENT=144 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='角色关联版本历史';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `movie_genres`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `movie_genres` (
  `movie_id` bigint NOT NULL,
  `type_num` int NOT NULL,
  PRIMARY KEY (`movie_id`,`type_num`),
  CONSTRAINT `movie_genres_ibfk_1` FOREIGN KEY (`movie_id`) REFERENCES `movies` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `movie_genres_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `movie_genres_history` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `movie_id` bigint NOT NULL,
  `type_num` int NOT NULL,
  `change_type` varchar(16) NOT NULL,
  `changed_by` varchar(64) NOT NULL DEFAULT '',
  `changed_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_mg_ver` (`movie_id`,`type_num`,`changed_at`)
) ENGINE=InnoDB AUTO_INCREMENT=123 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='类型关联版本历史';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `movie_ratings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `movie_ratings` (
  `movie_id` bigint NOT NULL,
  `average` decimal(3,1) NOT NULL,
  `count` int NOT NULL,
  `distribution` json DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`movie_id`),
  CONSTRAINT `movie_ratings_ibfk_1` FOREIGN KEY (`movie_id`) REFERENCES `movies` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `movie_regions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `movie_regions` (
  `movie_id` bigint NOT NULL,
  `region_id` int NOT NULL,
  PRIMARY KEY (`movie_id`,`region_id`),
  KEY `region_id` (`region_id`),
  CONSTRAINT `movie_regions_ibfk_1` FOREIGN KEY (`movie_id`) REFERENCES `movies` (`id`) ON DELETE CASCADE,
  CONSTRAINT `movie_regions_ibfk_2` FOREIGN KEY (`region_id`) REFERENCES `regions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `movie_regions_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `movie_regions_history` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `movie_id` bigint NOT NULL,
  `region_id` int NOT NULL,
  `change_type` varchar(16) NOT NULL,
  `changed_by` varchar(64) NOT NULL DEFAULT '',
  `changed_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_mr_ver` (`movie_id`,`region_id`,`changed_at`)
) ENGINE=InnoDB AUTO_INCREMENT=47 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='地区关联版本历史';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `movie_review`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `movie_review` (
  `review_id` varchar(32) NOT NULL COMMENT '豆瓣长评ID',
  `movie_id` int NOT NULL COMMENT '本地MySQL movies.id',
  `subject_id` varchar(32) NOT NULL COMMENT '豆瓣电影subject_id',
  `title` varchar(256) NOT NULL DEFAULT '' COMMENT '长评标题',
  `author` varchar(64) NOT NULL DEFAULT '' COMMENT '作者昵称',
  `useful_count` int NOT NULL DEFAULT '0' COMMENT '赞同数',
  `date` varchar(16) NOT NULL DEFAULT '' COMMENT '发布日期',
  `status` varchar(16) NOT NULL DEFAULT 'pending' COMMENT 'pending/done/failed',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`review_id`),
  KEY `idx_movie` (`movie_id`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `movie_style`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `movie_style` (
  `movie_id` bigint NOT NULL COMMENT '关联 movies.id',
  `tag_id` int unsigned NOT NULL COMMENT '关联 movie_style_tag.id',
  `confidence` decimal(2,1) NOT NULL DEFAULT '1.0' COMMENT 'AI 可信度 0.0~1.0',
  PRIMARY KEY (`movie_id`,`tag_id`),
  KEY `idx_tag` (`tag_id`),
  CONSTRAINT `fk_ms_movie` FOREIGN KEY (`movie_id`) REFERENCES `movies` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_ms_tag` FOREIGN KEY (`tag_id`) REFERENCES `movie_style_tag` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `movie_style_tag`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `movie_style_tag` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(32) NOT NULL COMMENT '风格名称（如 黑暗、温馨、暴力、哲学）',
  `dimension` varchar(16) NOT NULL DEFAULT '' COMMENT 'overall|plot|visual|narrative|pacing',
  `review_status` tinyint NOT NULL DEFAULT '0' COMMENT '0=刚生成未检测 1=相似度<82%无需合并 2=相似度≥82%待确认 3=管理员确认已合并',
  `merged_to_tag_id` int unsigned NOT NULL DEFAULT '0' COMMENT '合并到的已有标签id，0=未合并',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_name_dim` (`name`,`dimension`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `movies`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `movies_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `movies_history` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `movie_id` bigint NOT NULL,
  `douban_id` varchar(32) DEFAULT NULL,
  `title` varchar(512) NOT NULL,
  `original_title` varchar(512) DEFAULT NULL,
  `release_year` smallint DEFAULT NULL,
  `release_date` date DEFAULT NULL,
  `duration` smallint DEFAULT NULL,
  `poster_url` varchar(2048) DEFAULT NULL,
  `imdb_id` varchar(20) DEFAULT NULL,
  `is_published` tinyint(1) DEFAULT '1',
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `change_type` varchar(16) NOT NULL COMMENT 'create/update/delete',
  `changed_by` varchar(64) NOT NULL DEFAULT '',
  `changed_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_mv_ver` (`movie_id`,`changed_at`)
) ENGINE=InnoDB AUTO_INCREMENT=79 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='电影版本历史';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `people`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `people_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `people_history` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `person_id` bigint NOT NULL,
  `douban_id` varchar(32) DEFAULT NULL,
  `name` varchar(256) NOT NULL,
  `change_type` varchar(16) NOT NULL,
  `changed_by` varchar(64) NOT NULL DEFAULT '',
  `changed_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_pp_ver` (`person_id`,`changed_at`)
) ENGINE=InnoDB AUTO_INCREMENT=133 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='人员版本历史';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `permissions` (
  `code` varchar(32) NOT NULL,
  `name` varchar(64) NOT NULL,
  `description` varchar(256) NOT NULL DEFAULT '',
  PRIMARY KEY (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `playlists`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `playlists` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `title` varchar(128) NOT NULL COMMENT '片单标题',
  `description` text COMMENT '推荐语/介绍文字',
  `cover_url` varchar(512) DEFAULT '' COMMENT '封面图 URL（TOS 上传）',
  `movie_ids` json NOT NULL COMMENT '电影ID有序列表，如 [38,39,44,47,53]',
  `sort_order` int DEFAULT '0' COMMENT '轮播展示顺序（数字越小越靠前）',
  `is_published` tinyint(1) DEFAULT '0' COMMENT '0=草稿/下架 1=已发布（需配合 publish_at/unpublish_at 时间窗口）',
  `publish_at` datetime DEFAULT NULL COMMENT '计划上架时间（NULL=立即上架，配合 is_published=1）',
  `unpublish_at` datetime DEFAULT NULL COMMENT '计划下架时间（NULL=永不下架，到期后查询自动过滤）',
  `created_by` int NOT NULL COMMENT 'FK users.id，创建者',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_sort` (`sort_order`,`is_published`),
  KEY `idx_created_by` (`created_by`),
  KEY `idx_created_at` (`created_at`),
  KEY `idx_publish_at` (`publish_at`),
  CONSTRAINT `fk_playlist_creator` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='管理员推荐片单（轮播 + 详情页，支持定时上下架）';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `regions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `regions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(128) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`),
  UNIQUE KEY `uk_regions_name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=25 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `review_summary`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `review_summary` (
  `id` int unsigned NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `movie_id` int NOT NULL COMMENT '关联电影ID',
  `full_summary` text COMMENT '长评综合总结',
  `review_tags` json DEFAULT NULL COMMENT '评论标签数组',
  `status` varchar(20) NOT NULL DEFAULT 'pending' COMMENT '状态：pending=待生成, done=生成成功, failed=生成失败',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_movie_id` (`movie_id`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='电影评论AI总结表';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `task_failures`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_failures` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_id` bigint NOT NULL DEFAULT '0' COMMENT 'snowflake 任务ID',
  `worker_id` int NOT NULL,
  `task_json` text NOT NULL,
  `event_type` varchar(20) NOT NULL COMMENT 'failure 或 cancelled',
  `reason` text NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `admin_id` int NOT NULL DEFAULT '0' COMMENT '提交任务的管理员ID',
  `kind` varchar(16) NOT NULL DEFAULT 'unknown',
  `failure_layer` varchar(16) NOT NULL DEFAULT 'crawler' COMMENT 'crawler | storage | ai | system',
  `status` varchar(16) NOT NULL DEFAULT 'pending' COMMENT 'pending/claimed/resolved',
  `claimed_by` int NOT NULL DEFAULT '0' COMMENT '认领的管理员 admin_id',
  `claimed_at` datetime DEFAULT NULL,
  `resolved_at` datetime DEFAULT NULL,
  `parent_failure_id` bigint NOT NULL DEFAULT '0' COMMENT '关联的上一次失败记录 ID，首败=0',
  `scope` varchar(10) NOT NULL DEFAULT 'batch' COMMENT 'batch / item',
  `item_douban_id` varchar(32) NOT NULL DEFAULT '' COMMENT '失败的电影 douban_id',
  `item_title` varchar(256) NOT NULL DEFAULT '' COMMENT '失败的电影名',
  `snapshot` json DEFAULT NULL COMMENT '执行现场快照',
  `retry_count` int NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `idx_created_at` (`created_at`),
  KEY `idx_status` (`status`),
  KEY `idx_scope_status` (`scope`,`status`)
) ENGINE=InnoDB AUTO_INCREMENT=915 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `task_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `user_action_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_action_log` (
  `id` bigint NOT NULL COMMENT 'snowflake ID',
  `user_id` int NOT NULL COMMENT 'FK users.id',
  `movie_id` bigint NOT NULL COMMENT 'FK movies.id',
  `action` varchar(16) NOT NULL COMMENT 'want_watch|watching|watched|favorite|review',
  `score_delta` decimal(8,4) NOT NULL DEFAULT '0.0000' COMMENT '本次操作总计分值（正=加分，负=扣分/回滚）',
  `tag_deltas_json` json DEFAULT NULL COMMENT '[{"dim":"director","label":"吕克·贝松","delta":2.0},...]',
  `reverted_at` datetime DEFAULT NULL COMMENT '非空=已回滚，值为回滚时间',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_ual_user_movie` (`user_id`,`movie_id`),
  KEY `idx_ual_user_time` (`user_id`,`created_at` DESC),
  KEY `idx_ual_reverted` (`reverted_at`),
  KEY `fk_ual_movie` (`movie_id`),
  CONSTRAINT `fk_ual_movie` FOREIGN KEY (`movie_id`) REFERENCES `movies` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_ual_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户行为操作流水（审计+回滚）';
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `user_movie_status`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `user_permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `user_tag_score`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=2912 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

