-- 片单系统 — 数据库升级脚本 v2
-- 用途：管理员创建推荐片单 + 轮播展示，片单详情页含电影摘要
-- v2: 增加定时上下架时间 + 管理端筛选索引
-- 日期：2025-07
-- ===================================================

-- 片单主表
CREATE TABLE IF NOT EXISTS playlists (
    id           BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
    title        VARCHAR(128) NOT NULL COMMENT '片单标题',
    description  TEXT         COMMENT '推荐语/介绍文字',
    cover_url    VARCHAR(512) DEFAULT '' COMMENT '封面图 URL（TOS 上传）',
    movie_ids    JSON         NOT NULL COMMENT '电影ID有序列表，如 [38,39,44,47,53]',
    sort_order   INT          DEFAULT 0 COMMENT '轮播展示顺序（数字越小越靠前）',
    is_published TINYINT(1)   DEFAULT 0 COMMENT '0=草稿/下架 1=已发布（需配合 publish_at/unpublish_at 时间窗口）',
    publish_at   DATETIME     DEFAULT NULL COMMENT '计划上架时间（NULL=立即上架，配合 is_published=1）',
    unpublish_at DATETIME     DEFAULT NULL COMMENT '计划下架时间（NULL=永不下架，到期后查询自动过滤）',
    created_by   INT          NOT NULL COMMENT 'FK users.id，创建者',
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_sort        (sort_order, is_published),
    INDEX idx_created_by  (created_by),
    INDEX idx_created_at  (created_at),
    INDEX idx_publish_at  (publish_at),
    CONSTRAINT fk_playlist_creator FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='管理员推荐片单（轮播 + 详情页，支持定时上下架）';
