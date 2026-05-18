"""
crawler/parser.py

数据提取层 — 将原始 HTML/JSON 转换为结构化 dict。

⚠️ 豆瓣页面改版风险：HTML 解析依赖正则/选择器匹配，豆瓣变更页面结构时
关键字段可能静默返回空值。建议在提取 title/score 等核心字段为空时
加 WARNING 日志供 Monitor 感知。

职责：
    1. parse_movie_list(JSON list)    → list[dict]  电影列表
    2. parse_review_list(HTML)        → list[dict]  长评列表 (review_id, 标题, 作者, 赞同数)
    3. parse_review_full(JSON)        → dict        长评正文 (html → 纯文本)
    4. parse_comments(HTML)           → list[dict]  短评列表
    5. parse_directors(HTML)          → list[dict]  电影详情页导演提取

设计原则：
    - 纯函数，无副作用，不依赖外部 I/O
    - 输入：原始数据（list/dict/str），输出：结构化 dict 列表
    - 异常：解析失败时抛出 ValueError，标记错误原因
    - 正则优先：HTML 结构相对固定，用 re.DOTALL 提取比引入依赖更轻量
"""

import html
import logging
import re
from datetime import date, datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 1a: 电影列表解析 (JSON → list[dict])
# ═══════════════════════════════════════════


def parse_movie_list(data: list) -> List[Dict[str, Any]]:
    """
    从豆瓣榜单 /j/chart/top_list API 响应中提取 douban_id 列表。

    仅提取 id 和 title（用于日志），其余数据在 parse_movie_detail 中从详情页提取。

    输入：
        data: /j/chart/top_list 返回的 JSON list

    输出：
        list[dict]，每个 dict 包含：
          - douban_id: str  豆瓣电影 ID
          - title:     str  中文片名（仅用于日志）

    异常：
        ValueError — data 为空
    """
    if not data:
        raise ValueError("电影列表为空")

    result = []
    for item in data:
        if not item.get("id"):
            continue
        result.append({
            "douban_id": str(item["id"]),
            "title": item.get("title", ""),
        })

    logger.info(f"parse_movie_list: 提取 {len(result)} 部电影 ID")
    return result


# ═══════════════════════════════════════════
# 1a2: 电影详情解析 (HTML → dict)
# ═══════════════════════════════════════════


def parse_movie_detail(html_str: str) -> Dict[str, Any]:
    """
    从豆瓣电影详情页 HTML 提取完整电影信息（替代榜单 API 摘要）。

    输入：
        html_str: /subject/{douban_id}/ 页面的完整 HTML

    输出：
        dict:
          - douban_id:  str       豆瓣电影 ID
          - title:      str       中文片名
          - score:      float     豆瓣评分
          - vote_count: int       评分人数
          - types:      list[str] 类型（中文）
          - actors:     list[str] 演员姓名（中文）
          - directors:  list[dict] 导演 [{name, douban_id}, ...]
          - release_date: str     最早上映日期 (YYYY-MM-DD)
          - release_year: int     上映年份
          - duration:   int       片长（分钟）
          - poster_url: str       封面图片 URL

    异常：
        ValueError — HTML 为空

    设计要点：
        - 标题/评分/片长/类型来自 v: 微格式属性
        - 导演/演员来自 <li class="celebrity"> 列表（按 role 分类）
        - 不依赖 JSON-LD（含控制字符，json.loads 可能失败）
    """
    if not html_str:
        raise ValueError("详情页 HTML 为空")

    def _get_v(name: str) -> str:
        m = re.search(rf'property="v:{name}"[^>]*>([^<]+)<', html_str)
        return html.unescape(m.group(1)).strip() if m else ""

    def _get_v_attr(name: str, attr: str = "content") -> str:
        tag_match = re.search(rf'<[^>]*property="v:{name}"[^>]*>', html_str, re.DOTALL)
        if tag_match:
            attr_match = re.search(rf'{attr}=["\']([^"\']+)["\']', tag_match.group())
            if attr_match:
                return attr_match.group(1)
        return ""

    # 标题 + 年份
    title = _get_v("itemreviewed")
    if not title:
        logger.warning("parse_movie_detail: title 为空，豆瓣页面结构可能已变更")
    year_match = re.search(r'<span class="year">\((\d{4})\)</span>', html_str)
    release_year = int(year_match.group(1)) if year_match else 0

    # 评分
    score = float(_get_v("average")) if _get_v("average") else 0.0
    if score == 0.0:
        logger.debug("parse_movie_detail: score 为 0（无评分或提取失败）")
    votes = int(_get_v("votes")) if _get_v("votes") else 0

    # 片长
    runtime_str = _get_v_attr("runtime") or "0"
    duration = int(runtime_str) if runtime_str.isdigit() else 0

    # 上映日期 + 地区 + 封面（来自 <span class="pl"> 标签区）
    release_date = ""
    regions: list[str] = []
    for m in re.finditer(
        r'<span\s+class="pl">(.*?)</span>\s*(.+?)(?:<br|</div)',
        html_str,
        re.DOTALL,
    ):
        label = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        value = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        if label == "制片国家/地区:":
            regions = [r.strip() for r in value.split("/")]
        elif label == "上映日期:" and not release_date:
            # 取年份最早的日期
            date_candidates = re.findall(r'(\d{4}-\d{2}-\d{2})', value)
            if date_candidates:
                release_date = min(date_candidates)

    # 封面图 — 多道兜底，从最精确到最通用
    poster_url = ""

    # ① img[rel="v:image"] — 先整体匹配 img 标签，再从标签内提取 src
    #    豆瓣详情页主海报固定使用 rel="v:image" 语义标记
    img_tag_match = re.search(
        r'<img[^>]*\brel="v:image"[^>]*>',
        html_str,
        re.IGNORECASE,
    )
    if img_tag_match:
        src_match = re.search(r'src="([^"]+)"', img_tag_match.group(), re.IGNORECASE)
        if src_match:
            poster_url = src_match.group(1)

    # ② <a class="nbgnbg" — 封面图的父级链接，豆瓣新页面结构
    #    点击海报跳转图片页的 <a> 标签，内部 <img> 不含 rel="v:image" 时靠此兜底
    if not poster_url:
        poster_link_match = re.search(
            r'<a[^>]*href="[^"]*/subject/\d+/photos?[^"]*"[^>]*>\s*<img[^>]*src="([^"]+)"',
            html_str,
            re.IGNORECASE,
        )
        if poster_link_match:
            poster_url = poster_link_match.group(1)

    # ③ <div id="mainpic"> — 豆瓣传统海报容器，提取其中第一张 img 的 src
    if not poster_url:
        mainpic_match = re.search(
            r'<div\s+id="mainpic"[^>]*>(.*?)</div>',
            html_str,
            re.DOTALL,
        )
        if mainpic_match:
            src_in_mainpic = re.search(r'<img[^>]*src="([^"]+)"', mainpic_match.group(1))
            if src_in_mainpic:
                poster_url = src_in_mainpic.group(1)

    # ④ <meta property="v:image" content="..."> — 兜底，豆瓣可能不再提供
    if not poster_url:
        poster_url = _get_v_attr("image") or ""

    # ⑤ JSON-LD — 限制在 <script type="application/ld+json"> 块内提取
    #    先取完整 script 块（非贪婪到 </script>），再从中搜 "image"
    #    避免全局匹配误伤演职人员/影人的 image 字段
    if not poster_url:
        ld_block = re.search(
            r'<script\s+type="application/ld\+json"[^>]*>(.*?)</script>',
            html_str,
            re.DOTALL,
        )
        if ld_block:
            ld_match = re.search(r'"image"\s*:\s*"([^"]+)"', ld_block.group(1))
            if ld_match:
                poster_url = ld_match.group(1)

    # ⑥ <meta property="og:image" content="..."> — Open Graph 标准
    if not poster_url:
        og_match = re.search(
            r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"',
            html_str,
            re.IGNORECASE,
        )
        if og_match:
            poster_url = og_match.group(1)

    # ── 协议归一化 ──
    # 豆瓣 CDN 图片常用 //img9.doubanio.com/... 协议相对格式
    if poster_url and poster_url.startswith("//"):
        poster_url = "https:" + poster_url

    # ── 过滤非图片 URL（兜底匹配可能抓到无关链接） ──
    if poster_url and not any(
        poster_url.endswith(ext) for ext in (".webp", ".jpg", ".jpeg", ".png", ".gif", ".bmp")
    ):
        logger.warning(
            "parse_movie_detail: poster_url 可能不是图片URL，已丢弃: %s",
            poster_url[:150],
        )
        poster_url = ""

    if not poster_url:
        # 诊断日志：列出 HTML 中所有可能的图片 URL，便于排查豆瓣新页面结构
        all_potential = re.findall(
            r'(?:src|content|data-src)=["\']([^"\']*(?:poster|photo|image)[^"\']*\.(?:webp|jpg|png))["\']',
            html_str,
            re.IGNORECASE,
        )
        logger.warning(
            "parse_movie_detail: poster_url 提取失败，HTML 前 500 字: %s | 候选海报URL: %s",
            html_str[:500],
            all_potential[:5] if all_potential else "无",
        )

    # 类型（去重 — 详情页可能同一 genre 出现多次）
    types = list(dict.fromkeys(re.findall(r'<span property="v:genre">(.*?)</span>', html_str)))

    # ── 导演 + 演员（来自 <li class="celebrity"> 列表） ──
    celebs = re.findall(
        r'<li\s+class="celebrity"[^>]*>(.*?)</li>', html_str, re.DOTALL,
    )

    actors_list: list[str] = []
    directors_list: list[dict] = []

    for block in celebs:
        role_match = re.search(
            r'<span\s+class="role"[^>]*>(.*?)</span>', block, re.DOTALL,
        )
        if not role_match:
            continue
        role_text = html.unescape(role_match.group(1)).strip()

        name_match = re.search(
            r'<span\s+class="name"[^>]*>.*?<a[^>]*href="[^"]*/personage/(\d+)/"[^>]*>(.*?)</a>',
            block, re.DOTALL,
        )
        if not name_match:
            continue
        person_douban_id = name_match.group(1)
        person_name = html.unescape(name_match.group(2)).strip()

        if "导演" in role_text:
            directors_list.append({"name": person_name, "douban_id": person_douban_id})
        else:
            actors_list.append(person_name)

    logger.info(
        f"parse_movie_detail: title='{title}' "
        f"actors={len(actors_list)} directors={len(directors_list)}"
    )
    return {
        "douban_id": "",  # 由调用方填入（详情页 URL 中不含 douban_id）
        "title": title,
        "score": score,
        "vote_count": votes,
        "types": types,
        "regions": regions,
        "actors": actors_list,
        "directors": directors_list,
        "release_date": release_date,
        "release_year": release_year,
        "duration": duration,
        "poster_url": poster_url,
    }


# ═══════════════════════════════════════════
# 1b: 长评列表解析 (HTML → list[dict])
# ═══════════════════════════════════════════


def _mask_author_name(name: str) -> str:
    """作者昵称中间打码（方案A）：
    1字：A → A*
    2字：张三 → 张*
    3+字：王小明 → 王*明 / abcde → a***e
    """
    if not name:
        return ""
    name = name.strip()
    if len(name) == 1:
        return name + "*"
    if len(name) == 2:
        return name[0] + "*"
    return name[0] + "*" * (len(name) - 2) + name[-1]


def parse_review_list(html_str: str) -> List[Dict[str, Any]]:
    """
    从豆瓣长评列表页 HTML 提取评论元数据。

    输入：
        html_str: /subject/{id}/reviews 页面的完整 HTML

    输出：
        list[dict]，每个 dict 包含：
          - review_id:    str  (review_item 的 id 属性)
          - title:        str  (评论标题)
          - author:       str  (作者昵称，已去敏)
          - useful_count: int  (赞同数)
          - date:         str  (发布日期，如 "2005-05-12")

    提取策略：
        1. 按 <div class="main review-item" id="..."> 分块
        2. 在每个块中用子正则提取各项
        3. 容忍部分字段缺失

    异常：
        ValueError — HTML 为空或无 review-item
    """
    if not html_str:
        raise ValueError("评论列表 HTML 为空")

    # 按 review-item 分块
    blocks = re.findall(
        r'<div class="main review-item"\s+id="(\d+)"[^>]*>(.*?)</div>\s*</div>\s*</div>',
        html_str,
        re.DOTALL,
    )
    if not blocks:
        # 宽松匹配（Dom 结构可能略有调整）
        blocks = re.findall(
            r'<div class="main review-item"\s+id="(\d+)"[^>]*>(.*?)(?=<div class="main review-item"|$)',
            html_str,
            re.DOTALL,
        )

    if not blocks:
        logger.warning("parse_review_list: 未找到任何 review-item 块，页面结构可能已变更")

    result = []
    for review_id, block in blocks:
        # 标题: <h2><a href="...">标题文本</a></h2>
        title = ""
        title_match = re.search(r"<h2>\s*<a[^>]*>(.*?)</a>\s*</h2>", block, re.DOTALL)
        if title_match:
            title = html.unescape(title_match.group(1)).strip()

        # 作者: <a ... class="name">作者名</a>
        author = ""
        author_match = re.search(r'<a[^>]*class="name"[^>]*>(.*?)</a>', block, re.DOTALL)
        if author_match:
            author = html.unescape(author_match.group(1)).strip()
            author = _mask_author_name(author)

        # 赞同数: <a class="action-btn up" title="有用">数字</a>
        useful_count = 0
        useful_match = re.search(
            r'<a[^>]*class="action-btn up"[^>]*title="有用"[^>]*>\s*(\d+)\s*</a>',
            block,
            re.DOTALL,
        )
        if useful_match:
            useful_count = int(useful_match.group(1))

        # 日期: <span content="2005-05-12" class="main-meta">...</span>
        date_str = ""
        date_match = re.search(
            r'<span\s+content="(\d{4}-\d{2}-\d{2})"\s+class="main-meta"',
            block,
        )
        if date_match:
            date_str = date_match.group(1)

        if not title and not author and not date_str and useful_count == 0:
            logger.warning(f"parse_review_list: review_id={review_id} 所有可提取字段均为空")

        result.append({
            "review_id": review_id,
            "title": title,
            "author": author,
            "useful_count": useful_count,
            "date": date_str,
        })

    logger.info(f"parse_review_list: 解析 {len(result)} 条长评")
    return result


# ═══════════════════════════════════════════
# 1c: 长评正文解析 (JSON → dict)
# ═══════════════════════════════════════════


def parse_review_full(data: dict) -> Dict[str, Any]:
    """
    解析豆瓣长评正文 API 响应。

    输入：
        data: /j/review/{id}/full 返回的 JSON 对象
              {"body": "...", "votes": "...", "html": "<p>完整正文HTML</p>"}

    输出：
        dict:
          - html:  str  原始 HTML 正文
          - text:  str  去标签后的纯文本
          - votes: str  赞同数

    异常：
        ValueError — data 缺少必要字段
    """
    if not data:
        raise ValueError("长评正文数据为空")

    body_html = data.get("html", "")
    if not body_html:
        raise ValueError("长评正文缺少 html 字段")

    # HTML → 纯文本：去除标签、解码实体、压缩空白
    text = re.sub(r"<br\s*/?>", "\n", body_html)
    text = re.sub(r"</p>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n\s*\n", "\n\n", text)
    text = text.strip()

    return {
        "html": body_html,
        "text": text,
        "votes": data.get("votes", ""),
    }


# ═══════════════════════════════════════════
# 1d: 短评列表解析 (HTML → list[dict])
# ═══════════════════════════════════════════

# 评分映射: allstar50 → 5.0 / allstar40 → 4.0 / allstar30 → 3.0 ...
_STAR_MAP = {
    "allstar50": 5.0,
    "allstar45": 4.5,
    "allstar40": 4.0,
    "allstar35": 3.5,
    "allstar30": 3.0,
    "allstar25": 2.5,
    "allstar20": 2.0,
    "allstar15": 1.5,
    "allstar10": 1.0,
    "allstar05": 0.5,
}


def parse_comments(html_str: str) -> List[Dict[str, Any]]:
    """
    从豆瓣短评页 HTML 提取短评列表。

    输入：
        html_str: /subject/{id}/comments?start=N&limit=20&... 页面的完整 HTML

    输出：
        list[dict]，每个 dict 包含：
          - comment_id:   str   豆瓣短评 ID
          - author:       str   用户名（已脱敏）
          - rating:       float 评分 (1.0~5.0)
          - text:         str   短评正文
          - date:         str   发布日期时间 ("YYYY-MM-DD HH:MM:SS")
          - useful_count: int   有用数

    提取策略：
        1. 按 <div class="comment-item" data-cid="..."> 分块
        2. 在每个块中提取各项字段
        3. 评分通过 allstarXX class 映射

    异常：
        ValueError — HTML 为空或无 comment-item
    """
    if not html_str:
        raise ValueError("短评 HTML 为空")

    blocks = re.findall(
        r'<div class="comment-item"\s+data-cid="(\d+)"[^>]*>(.*?)</div>\s*<script>',
        html_str,
        re.DOTALL,
    )
    if not blocks:
        logger.warning("parse_comments: 未找到任何 comment-item 块")
        raise ValueError("短评 HTML 中未找到 comment-item")

    result = []
    for cid, block in blocks:
        # 有用数: <span class="votes vote-count">N</span>
        useful_count = 0
        votes_match = re.search(
            r'<span class="votes vote-count">(\d+)</span>', block
        )
        if votes_match:
            useful_count = int(votes_match.group(1))

        # 作者: <span class="comment-info">...<a href="...">NAME</a>...
        author = ""
        author_match = re.search(
            r'<span class="comment-info">.*?<a[^>]*>(.*?)</a>', block, re.DOTALL
        )
        if author_match:
            author = html.unescape(author_match.group(1)).strip()
            author = _mask_author_name(author)

        # 评分: <span class="allstarXX rating" title="..."></span>
        rating = 0.0
        rating_match = re.search(
            r'<span class="(allstar\d\d)\s+rating"', block
        )
        if rating_match:
            rating = _STAR_MAP.get(rating_match.group(1), 0.0)

        # 日期: <span class="comment-time" title="YYYY-MM-DD HH:MM:SS">
        date_str = ""
        date_match = re.search(
            r'<span class="comment-time"[^>]*title="([^"]*)"', block
        )
        if date_match:
            date_str = date_match.group(1)

        # 正文: <span class="short">TEXT</span>
        text = ""
        text_match = re.search(
            r'<span class="short">(.*?)</span>', block, re.DOTALL
        )
        if text_match:
            text = html.unescape(text_match.group(1)).strip()

        if not author and not date_str and not text and useful_count == 0 and rating == 0.0:
            logger.warning(f"parse_comments: comment_id={cid} 所有可提取字段均为空")

        result.append({
            "comment_id": cid,
            "author": author,
            "rating": rating,
            "text": text,
            "date": date_str,
            "useful_count": useful_count,
        })

    logger.info(f"parse_comments: 解析 {len(result)} 条短评")
    return result


# ═══════════════════════════════════════════
# 1e: 电影详情页导演提取 (HTML → list[dict])
# ═══════════════════════════════════════════


def parse_directors(html_str: str) -> List[Dict[str, Any]]:
    """
    从豆瓣电影详情页 HTML 提取导演信息。

    输入：
        html_str: /subject/{douban_id}/ 页面的完整 HTML

    输出：
        list[dict]，每个 dict 包含：
          - name:      str  导演名
          - douban_id: str  豆瓣人员 ID（来自 /personage/{id}/ URL），提取失败则为 ""

    提取策略：
        1. 定位所有 <li class="celebrity"> 块
        2. 在每个块中：
           - 找 <span class="role"> 内容，包含中文"导演"二字 → 判定为导演
           - 找 <span class="name"> 内的 <a href=".../personage/{id}/"> → douban_id
           - <a> 标签文本 → name（html.unescape）
        3. 仅返回判定为导演的条目

    异常：
        ValueError — HTML 为空
        未找到导演 → 返回空列表（不抛异常，部分页面可能无导演信息）

    设计要点：
        - 不依赖微格式属性（rel="v:directedBy"），只依赖可见文本"导演"二字
        - 支持多导演（联合执导），全量提取后按 role 过滤
        - 可复用于提取演员/编剧等其他角色（本函数只取导演）
    """
    if not html_str:
        raise ValueError("详情页 HTML 为空")

    # 定位所有 <li class="celebrity"> 块
    blocks = re.findall(
        r'<li\s+class="celebrity"[^>]*>(.*?)</li>',
        html_str,
        re.DOTALL,
    )
    if not blocks:
        logger.debug("parse_directors: 未找到 celebrity 列表")
        return []

    result = []
    for block in blocks:
        # 判定角色：<span class="role" ...>导演</span>
        role_match = re.search(
            r'<span\s+class="role"[^>]*>(.*?)</span>',
            block,
            re.DOTALL,
        )
        if not role_match:
            continue
        role_text = html.unescape(role_match.group(1)).strip()
        if "导演" not in role_text:
            continue

        # 提取人名 + douban_id（仅在 <span class="name"> 内搜索）
        name_match = re.search(
            r'<span\s+class="name"[^>]*>.*?<a[^>]*href="[^"]*/personage/(\d+)/"[^>]*>(.*?)</a>',
            block,
            re.DOTALL,
        )
        if name_match:
            douban_id = name_match.group(1)
            raw_name = name_match.group(2)
            name = html.unescape(raw_name).strip()
            result.append({"name": name, "douban_id": douban_id})

    logger.info(f"parse_directors: 解析 {len(result)} 位导演")
    return result


# ═══════════════════════════════════════════
# 1f: 全部演职人员解析 (HTML → list[dict])
# ═══════════════════════════════════════════

_ROLE_MAP = [
    # (keyword, slug) — 按优先级从高到低排列
    ("导演", "director"),
    ("Director", "director"),
    ("演员", "actor"),
    ("Actress", "actor"),
    ("Actor", "actor"),
    ("配音", "actor"),
    ("Voice", "actor"),
    ("编剧", "writer"),
    ("Screenplay", "writer"),
    ("Writer", "writer"),
    ("制片", "producer"),
    ("Producer", "producer"),
    ("美术", "art_director"),
    ("Art Direction", "art_director"),
    ("Production Design", "art_director"),
    ("音乐", "music"),
    ("Music", "music"),
]


def _classify_role(role_text: str) -> str:
    """
    输入：豆瓣 role 文本（如 "导演 Director" / "Story and Screenplay by" / "配音 Voice"}
    输出：内部 role_type slug（如 "director" / "writer" / "actor"）
    """
    for keyword, slug in _ROLE_MAP:
        if keyword in role_text:
            return slug
    return "other"


def parse_personnel(html_str: str) -> List[Dict[str, Any]]:
    """
    从 /subject/{douban_id}/celebrities 页面提取全部演职人员。

    输入：
        html_str: /celebrities 页面的完整 HTML

    输出：
        list[dict]，每个 dict 包含：
          - name:       str   人员姓名
          - douban_id:  str   豆瓣人员 ID
          - role_type:  str   内部角色分类 (director/actor/writer/producer/art_director/music/other)

    角色分类规则：
        - "导演" in role → director
        - "演员" or "配音" in role → actor
        - "编剧" in role → writer
        - "制片" in role → producer
        - "美术" in role → art_director
        - "音乐" in role → music
        - 其他 → other

    异常：
        ValueError — HTML 为空
    """
    if not html_str:
        raise ValueError("演职人员 HTML 为空")

    blocks = re.findall(
        r'<li\s+class="celebrity"[^>]*>(.*?)</li>',
        html_str,
        re.DOTALL,
    )
    if not blocks:
        logger.debug("parse_personnel: 未找到 celebrity 列表")
        return []

    result = []
    for block in blocks:
        role_match = re.search(
            r'<span\s+class="role"[^>]*>(.*?)</span>',
            block,
            re.DOTALL,
        )
        if not role_match:
            continue
        role_text = html.unescape(role_match.group(1)).strip()

        name_match = re.search(
            r'<span\s+class="name"[^>]*>.*?<a[^>]*href="[^"]*/personage/(\d+)/"[^>]*>(.*?)</a>',
            block,
            re.DOTALL,
        )
        if not name_match:
            continue

        douban_id = name_match.group(1)
        raw_name = name_match.group(2)
        name = html.unescape(raw_name).strip()
        role_type = _classify_role(role_text)

        result.append({
            "name": name,
            "douban_id": douban_id,
            "role_type": role_type,
        })

    # 分类统计
    stats = {}
    for r in result:
        stats[r["role_type"]] = stats.get(r["role_type"], 0) + 1
    logger.info(f"parse_personnel: 解析 {len(result)} 人 ({stats})")
    return result
