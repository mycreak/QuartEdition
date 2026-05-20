-- 用户行为评分子系统 — 数据库升级脚本
-- 用途：记录用户操作、聚合标签分数、存储权重配置、驱动推荐引擎
-- ===================================================

-- 0. movies.id 升为 BIGINT（所有新表 movie_id 的 FK 需匹配）
ALTER TABLE movies MODIFY id BIGINT NOT NULL AUTO_INCREMENT;

-- 级联修改所有引用 movies.id 的子表
ALTER TABLE movie_ratings       MODIFY movie_id BIGINT NOT NULL;
ALTER TABLE movie_review        MODIFY movie_id BIGINT NOT NULL;
ALTER TABLE movie_credits       MODIFY movie_id BIGINT NOT NULL;
ALTER TABLE movie_genres        MODIFY movie_id BIGINT NOT NULL;
ALTER TABLE movie_regions       MODIFY movie_id BIGINT NOT NULL;
ALTER TABLE movie_style         MODIFY movie_id BIGINT NOT NULL;
ALTER TABLE movies_history      MODIFY movie_id BIGINT NOT NULL;
ALTER TABLE movie_credits_history  MODIFY movie_id BIGINT NOT NULL;
ALTER TABLE movie_genres_history   MODIFY movie_id BIGINT NOT NULL;
ALTER TABLE movie_regions_history  MODIFY movie_id BIGINT NOT NULL;

-- 1. 用户-电影标记状态表（快照：每用户每电影一行）
CREATE TABLE IF NOT EXISTS user_movie_status (
    user_id       INT      NOT NULL COMMENT 'FK users.id',
    movie_id      BIGINT   NOT NULL COMMENT 'FK movies.id',
    want_watch    TINYINT  NOT NULL DEFAULT 0 COMMENT '1=想看',
    watching      TINYINT  NOT NULL DEFAULT 0 COMMENT '1=在看',
    watched       TINYINT  NOT NULL DEFAULT 0 COMMENT '1=看过',
    favorite      TINYINT  NOT NULL DEFAULT 0 COMMENT '1=收藏',
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, movie_id),
    INDEX idx_user_want   (user_id, want_watch),
    INDEX idx_user_watched(user_id, watched),
    INDEX idx_user_fav    (user_id, favorite),
    CONSTRAINT fk_ums_user  FOREIGN KEY (user_id)  REFERENCES users(id)  ON DELETE CASCADE,
    CONSTRAINT fk_ums_movie FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户-电影标记状态（当前快照：想看/在看/看过/收藏）';

-- 2. 用户操作流水表（审计 + 回滚依据，每次操作一条）
CREATE TABLE IF NOT EXISTS user_action_log (
    id              BIGINT       NOT NULL COMMENT 'snowflake ID',
    user_id         INT          NOT NULL COMMENT 'FK users.id',
    movie_id        BIGINT       NOT NULL COMMENT 'FK movies.id',
    action          VARCHAR(16)  NOT NULL COMMENT 'want_watch|watching|watched|favorite|comment',
    score_delta     DECIMAL(8,4) NOT NULL DEFAULT 0 COMMENT '本次操作总计分值（正=加分，负=扣分/回滚）',
    tag_deltas_json JSON         DEFAULT NULL COMMENT '[{"dim":"director","label":"吕克·贝松","delta":2.0},...]',
    reverted_at     DATETIME     DEFAULT NULL COMMENT '非空=已回滚，值为回滚时间',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_ual_user_movie  (user_id, movie_id),
    INDEX idx_ual_user_time   (user_id, created_at DESC),
    INDEX idx_ual_reverted    (reverted_at),
    CONSTRAINT fk_ual_user  FOREIGN KEY (user_id)  REFERENCES users(id)  ON DELETE CASCADE,
    CONSTRAINT fk_ual_movie FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户行为操作流水（审计+回滚）';

-- 3. 用户-标签分数聚合表（画像查询专用，冗余 label 加速单表查询）
CREATE TABLE IF NOT EXISTS user_tag_score (
    user_id       INT          NOT NULL COMMENT 'FK users.id',
    dimension     VARCHAR(16)  NOT NULL COMMENT 'era|region|director|actor|genre|overall|plot|visual|narrative|pacing',
    label         VARCHAR(128) NOT NULL COMMENT '标签文本（冗余存储，避免 JOIN people/movie_style_tag）',
    score         DECIMAL(8,4) NOT NULL DEFAULT 0 COMMENT '当前累积分值',
    last_action   VARCHAR(16)  DEFAULT NULL COMMENT '最后一次触发此标签的操作类型',
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, dimension, label),
    INDEX idx_uts_user_score (user_id, score DESC),
    CONSTRAINT fk_uts_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户-标签分数聚合快照';

-- 4. 权重配置表（支持热加载，UPDATE 后无需重启）
CREATE TABLE IF NOT EXISTS config_score_weight (
    config_key    VARCHAR(32)  NOT NULL PRIMARY KEY COMMENT '配置键',
    config_value  DECIMAL(4,2) NOT NULL COMMENT '配置值',
    description   VARCHAR(128) NOT NULL DEFAULT '' COMMENT '说明',
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户行为评分配置';

-- ===================================================
-- 种子数据 — 权重与参数默认值
-- ===================================================

-- 操作行为权重
INSERT IGNORE INTO config_score_weight (config_key, config_value, description) VALUES
('action.want_watch',   1.0, '想看: 基础操作权重'),
('action.watching',     1.2, '在看: 基础操作权重'),
('action.watched',      2.0, '看过: 基础操作权重'),
('action.favorite',     1.5, '收藏: 基础操作权重'),
('action.comment',       3.0, '评论: 基础操作权重（最高）');

-- 维度基础权重
INSERT IGNORE INTO config_score_weight (config_key, config_value, description) VALUES
('dim.era',             0.3, '年代维度: 基础权重'),
('dim.region',          0.4, '地区维度: 基础权重'),
('dim.director',        1.0, '导演维度: 基础权重（最高）'),
('dim.actor',           0.8, '演员维度: 基础权重（再乘以位置衰减）'),
('dim.genre',           0.6, '豆瓣分类维度: 基础权重'),
('dim.overall',         0.7, '整体风格维度: 基础权重（AI）'),
('dim.plot',            0.7, '剧情风格维度: 基础权重（AI）'),
('dim.visual',          0.7, '画面风格维度: 基础权重（AI）'),
('dim.narrative',       0.7, '叙事风格维度: 基础权重（AI）'),
('dim.pacing',          0.7, '节奏风格维度: 基础权重（AI）');

-- 演员排名衰减系数
INSERT IGNORE INTO config_score_weight (config_key, config_value, description) VALUES
('actor.decay.1',       1.0,  '演员第1名: 位置衰减系数'),
('actor.decay.2',       0.85, '演员第2名: 位置衰减系数'),
('actor.decay.3',       0.70, '演员第3名: 位置衰减系数'),
('actor.decay.4',       0.55, '演员第4名: 位置衰减系数'),
('actor.decay.5',       0.40, '演员第5名: 位置衰减系数');

-- 时间衰减参数（查询时使用，不写入 user_tag_score）
INSERT IGNORE INTO config_score_weight (config_key, config_value, description) VALUES
('decay.window_30d',    1.0,  '30天内: 时间衰减系数'),
('decay.window_90d',    0.8,  '30-90天: 时间衰减系数'),
('decay.window_180d',   0.5,  '90-180天: 时间衰减系数'),
('decay.window_beyond', 0.2,  '180天以上: 时间衰减系数');

-- 推荐引擎阈值
INSERT IGNORE INTO config_score_weight (config_key, config_value, description) VALUES
('recommend.cv_threshold', 0.5, '变异系数阈值: 高于此值走精准推荐，低于走探索');

-- ===================================================
-- 验证
-- ===================================================
-- SHOW TABLES LIKE 'user_%';
-- SHOW TABLES LIKE 'config_score_weight';
-- SELECT COUNT(*) AS seed_count FROM config_score_weight;  -- 应为 25
-- DESC user_movie_status;    -- movie_id 应为 BIGINT
-- DESC user_action_log;
-- DESC user_tag_score;
-- DESC config_score_weight;
