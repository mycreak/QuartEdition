-- 电影风格标签 — 数据库升级脚本
-- 用途：从 AI 评论分析中提取内容风格关键词（整体/剧情/画面/叙事/节奏 5 维度）
-- 注意：题材/导演/演员/编剧/地区/年代 已由 movies / movie_genres / movie_credits / movie_regions 覆盖，不需要在此建表
-- ===================================================

-- 1. 风格标签字典表
CREATE TABLE IF NOT EXISTS movie_style_tag (
    id        INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name      VARCHAR(32) NOT NULL COMMENT '风格名称（如 黑暗压抑、非线性叙事、冷色调）',
    dimension VARCHAR(16) NOT NULL DEFAULT '' COMMENT 'overall|plot|visual|narrative|pacing',
    UNIQUE KEY uk_name_dim (name, dimension)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. 电影 ↔ 风格标签 关联表
CREATE TABLE IF NOT EXISTS movie_style (
    movie_id   BIGINT NOT NULL COMMENT '关联 movies.id',
    tag_id     INT UNSIGNED NOT NULL COMMENT '关联 movie_style_tag.id',
    confidence DECIMAL(2,1) NOT NULL DEFAULT 1.0 COMMENT 'AI 可信度 0.0~1.0',
    PRIMARY KEY (movie_id, tag_id),
    INDEX idx_tag (tag_id),
    CONSTRAINT fk_ms_movie FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE,
    CONSTRAINT fk_ms_tag   FOREIGN KEY (tag_id)  REFERENCES movie_style_tag(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. 旧表升级（已建表无 dimension / confidence 列时执行）
--    使用存储过程兼容 MySQL 8.0 各版本的 IF NOT EXISTS
DELIMITER //
CREATE PROCEDURE IF NOT EXISTS _migrate_style_tag()
BEGIN
    -- 3a. 补 dimension 列
    IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS 
                   WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='movie_style_tag' AND COLUMN_NAME='dimension') THEN
        ALTER TABLE movie_style_tag ADD COLUMN dimension VARCHAR(16) NOT NULL DEFAULT '' COMMENT 'overall|plot|visual|narrative|pacing' AFTER name;
    END IF;

    -- 3b. 修复唯一键：旧版只约束 name → 改为 (name, dimension) 联合唯一
    --     否则同名标签在不同维度下会被 INSERT IGNORE 静默丢弃
    IF EXISTS (SELECT 1 FROM information_schema.STATISTICS
               WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='movie_style_tag' AND INDEX_NAME='uk_name') THEN
        ALTER TABLE movie_style_tag DROP INDEX uk_name;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.STATISTICS
                   WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='movie_style_tag' AND INDEX_NAME='uk_name_dim') THEN
        ALTER TABLE movie_style_tag ADD UNIQUE KEY uk_name_dim (name, dimension);
    END IF;

    -- 3c. movie_style 表补 confidence 列
    IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS 
                   WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='movie_style' AND COLUMN_NAME='confidence') THEN
        ALTER TABLE movie_style   ADD COLUMN confidence DECIMAL(2,1) NOT NULL DEFAULT 1.0 COMMENT 'AI 可信度 0.0~1.0' AFTER tag_id;
    END IF;
END //
DELIMITER ;

CALL _migrate_style_tag();
DROP PROCEDURE IF EXISTS _migrate_style_tag;

-- ===================================================
-- 验证：
--   DESC movie_style_tag;   — 应有 id, name, dimension 三列
--   DESC movie_style;       — 应有 movie_id, tag_id, confidence 三列
