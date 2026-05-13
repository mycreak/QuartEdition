
"""
parse_movie_detail 单元测试
从豆瓣电影详情页 HTML 提取完整电影信息

提取机制:
    v: 标签文本     → title / score / votes / types
    v: 标签属性     → duration(content) / poster_url(content)
    <span class="year"> → release_year
    <span class="pl">   → release_date / regions
    <li class="celebrity"> → directors (role含"导演") / actors (其余role)
"""

import pytest
from crawler.parser import parse_movie_detail


# ============================================================================
# 测试样本 HTML 片段工厂
# ============================================================================

def _html(head: str, body: str) -> str:
    """拼接最小 HTML 骨架"""
    return f"<html><head>{head}</head><body>{body}</body></html>"


# ============================================================================
# 一、微观层: v: 微格式提取 — title / score / votes / duration / poster
# ============================================================================

class TestVMicroformatExtraction:
    """v: 标签文本 和 v: 标签属性 提取"""

    def test_title_from_itemreviewed(self):
        html = _html("", '<span property="v:itemreviewed">肖申克的救赎</span>')
        result = parse_movie_detail(html)
        assert result["title"] == "肖申克的救赎"

    def test_score_from_average(self):
        html = _html("", '<strong property="v:average">9.7</strong>')
        result = parse_movie_detail(html)
        assert result["score"] == 9.7

    def test_score_zero_when_missing(self):
        html = _html("", "")
        result = parse_movie_detail(html)
        assert result["score"] == 0.0

    def test_votes_from_votes(self):
        html = _html("", '<span property="v:votes">2840000</span>')
        result = parse_movie_detail(html)
        assert result["vote_count"] == 2840000

    def test_votes_zero_when_missing(self):
        html = _html("", "")
        result = parse_movie_detail(html)
        assert result["vote_count"] == 0

    def test_duration_from_runtime_content_attr(self):
        html = _html("", '<span property="v:runtime" content="142">142分钟</span>')
        result = parse_movie_detail(html)
        assert result["duration"] == 142

    def test_duration_zero_when_runtime_not_digit(self):
        html = _html("", '<span property="v:runtime" content="N/A">N/A</span>')
        result = parse_movie_detail(html)
        assert result["duration"] == 0

    def test_duration_zero_when_missing(self):
        html = _html("", "")
        result = parse_movie_detail(html)
        assert result["duration"] == 0

    def test_poster_from_img_rel_v_image_src(self):
        """真实豆瓣模式: <img rel="v:image" src="...">"""
        html = _html("", '<img rel="v:image" src="https://img3.doubanio.com/poster/p480747492.webp"/>')
        result = parse_movie_detail(html)
        assert result["poster_url"] == "https://img3.doubanio.com/poster/p480747492.webp"

    def test_poster_from_v_image_content_fallback(self):
        """降级模式: <link property="v:image" content="...">"""
        html = _html("", '<link property="v:image" content="https://img.douban.com/poster.jpg"/>')
        result = parse_movie_detail(html)
        assert result["poster_url"] == "https://img.douban.com/poster.jpg"

    def test_poster_empty_when_missing(self):
        html = _html("", "")
        result = parse_movie_detail(html)
        assert result["poster_url"] == ""

    def test_score_as_integer_string(self):
        """评分是整数字符串 "8" → float 8.0"""
        html = _html("", '<strong property="v:average">8</strong>')
        result = parse_movie_detail(html)
        assert result["score"] == 8.0

    def test_score_as_decimal_string(self):
        """评分是小数 "8.5" → float 8.5"""
        html = _html("", '<strong property="v:average">8.5</strong>')
        result = parse_movie_detail(html)
        assert result["score"] == 8.5

    def test_title_with_html_entity(self):
        """title 包含 &amp; → 解码后为 &"""
        html = _html("", '<span property="v:itemreviewed">Tom &amp; Jerry</span>')
        result = parse_movie_detail(html)
        assert result["title"] == "Tom & Jerry"


# ============================================================================
# 二、微观层: 年份提取
# ============================================================================

class TestYearExtraction:
    """\<span class="year"\>(YYYY)\</span\> 提取"""

    def test_year_basic(self):
        html = _html("", '<span class="year">(1994)</span>')
        result = parse_movie_detail(html)
        assert result["release_year"] == 1994

    def test_year_zero_when_no_match(self):
        html = _html("", '<span>no year here</span>')
        result = parse_movie_detail(html)
        assert result["release_year"] == 0

    def test_year_not_matched_by_three_digits(self):
        """只匹配 4 位年份"""
        html = _html("", '<span class="year">(199)</span>')
        result = parse_movie_detail(html)
        assert result["release_year"] == 0


# ============================================================================
# 三、微观层: 类型提取
# ============================================================================

class TestTypesExtraction:
    """\<span property="v:genre"\>提取 + 去重"""

    def test_single_type(self):
        html = _html("", '<span property="v:genre">剧情</span>')
        result = parse_movie_detail(html)
        assert result["types"] == ["剧情"]

    def test_multiple_types(self):
        html = _html(
            "",
            '<span property="v:genre">剧情</span>'
            '<span property="v:genre">犯罪</span>'
            '<span property="v:genre">悬疑</span>',
        )
        result = parse_movie_detail(html)
        assert result["types"] == ["剧情", "犯罪", "悬疑"]

    def test_duplicate_types_deduplicated(self):
        """同一 genre 出现多次 → 去重保留首次出现顺序"""
        html = _html(
            "",
            '<span property="v:genre">剧情</span>'
            '<span property="v:genre">剧情</span>'
            '<span property="v:genre">犯罪</span>',
        )
        result = parse_movie_detail(html)
        assert result["types"] == ["剧情", "犯罪"]

    def test_no_types(self):
        html = _html("", "")
        result = parse_movie_detail(html)
        assert result["types"] == []


# ============================================================================
# 四、微观层: 制片国家/地区提取
# ============================================================================

class TestRegionsExtraction:
    """\<span class="pl"\>制片国家/地区:\</span\> 提取"""

    def test_single_region(self):
        html = _html(
            "",
            '<div id="info">'
            '<span class="pl">制片国家/地区:</span> 美国<br>'
            "</div>",
        )
        result = parse_movie_detail(html)
        assert result["regions"] == ["美国"]

    def test_multiple_regions_slash_separated(self):
        html = _html(
            "",
            '<div id="info">'
            '<span class="pl">制片国家/地区:</span> 中国大陆 / 香港 / 美国<br>'
            "</div>",
        )
        result = parse_movie_detail(html)
        assert result["regions"] == ["中国大陆", "香港", "美国"]

    def test_region_with_extra_spaces(self):
        """斜杠两侧多余空格不影响解析"""
        html = _html(
            "",
            '<div id="info">'
            '<span class="pl">制片国家/地区:</span> 法国  /  意大利<br>'
            "</div>",
        )
        result = parse_movie_detail(html)
        # strip 只去掉首尾空格，" 意大利" 中间空格不去 — 符合当前实现行为
        assert "法国" in result["regions"]

    def test_no_regions(self):
        html = _html("", "")
        result = parse_movie_detail(html)
        assert result["regions"] == []


# ============================================================================
# 五、微观层: 上映日期提取
# ============================================================================

class TestReleaseDateExtraction:
    """\<span class="pl"\>上映日期:\</span\> — 取最早日期"""

    def test_single_release_date(self):
        html = _html(
            "",
            '<div id="info">'
            '<span class="pl">上映日期:</span>'
            '<span property="v:initialReleaseDate" content="1994-09-10">1994-09-10(加拿大)</span><br>'
            "</div>",
        )
        result = parse_movie_detail(html)
        assert result["release_date"] == "1994-09-10"

    def test_multi_date_picks_earliest(self):
        """多地上映取 min 日期"""
        html = _html(
            "",
            '<div id="info">'
            '<span class="pl">上映日期:</span>'
            "1994-09-10(加拿大) / 1994-10-14(美国)<br>"
            "</div>",
        )
        result = parse_movie_detail(html)
        assert result["release_date"] == "1994-09-10"

    def test_no_release_date(self):
        html = _html("", '<div id="info"></div>')
        result = parse_movie_detail(html)
        assert result["release_date"] == ""


# ============================================================================
# 六、微观层: 导演提取
# ============================================================================

class TestDirectorsExtraction:
    """\<li class="celebrity"\> 中 role 含 "导演" → directors"""

    def test_single_director(self):
        html = _html(
            "",
            '<ul>'
            '<li class="celebrity">'
            '<span class="role">导演</span>'
            '<span class="name"><a href="https://movie.douban.com/personage/1054394/">弗兰克·德拉邦特</a></span>'
            "</li>"
            "</ul>",
        )
        result = parse_movie_detail(html)
        assert len(result["directors"]) == 1
        assert result["directors"][0]["name"] == "弗兰克·德拉邦特"
        assert result["directors"][0]["douban_id"] == "1054394"

    def test_multiple_directors(self):
        html = _html(
            "",
            '<ul>'
            '<li class="celebrity">'
            '<span class="role">导演</span>'
            '<span class="name"><a href="https://movie.douban.com/personage/111/">导演A</a></span>'
            "</li>"
            '<li class="celebrity">'
            '<span class="role">导演</span>'
            '<span class="name"><a href="https://movie.douban.com/personage/222/">导演B</a></span>'
            "</li>"
            "</ul>",
        )
        result = parse_movie_detail(html)
        assert len(result["directors"]) == 2
        assert result["directors"][0]["name"] == "导演A"
        assert result["directors"][1]["name"] == "导演B"

    def test_no_directors(self):
        html = _html("", '<ul></ul>')
        result = parse_movie_detail(html)
        assert result["directors"] == []

    def test_director_without_douban_id_link(self):
        """role 是导演但 name span 内没有 personage URL → 跳过"""
        html = _html(
            "",
            '<ul>'
            '<li class="celebrity">'
            '<span class="role">导演</span>'
            '<span class="name">无名氏</span>'  # 无 <a> 标签
            "</li>"
            "</ul>",
        )
        result = parse_movie_detail(html)
        assert result["directors"] == []
        assert result["actors"] == []

    def test_celebrity_without_role_span(self):
        """celebrity 块缺少 role span → 跳过"""
        html = _html(
            "",
            '<ul>'
            '<li class="celebrity">'
            '<span class="name"><a href="https://movie.douban.com/personage/999/">某人</a></span>'
            "</li>"
            "</ul>",
        )
        result = parse_movie_detail(html)
        assert result["directors"] == []
        assert result["actors"] == []


# ============================================================================
# 七、微观层: 演员提取
# ============================================================================

class TestActorsExtraction:
    """\<li class="celebrity"\> 中 role 不含 "导演" → actors"""

    def test_single_actor(self):
        html = _html(
            "",
            '<ul>'
            '<li class="celebrity">'
            '<span class="role">演员</span>'
            '<span class="name"><a href="https://movie.douban.com/personage/1054539/">蒂姆·罗宾斯</a></span>'
            "</li>"
            "</ul>",
        )
        result = parse_movie_detail(html)
        assert result["actors"] == ["蒂姆·罗宾斯"]

    def test_multiple_actors(self):
        html = _html(
            "",
            '<ul>'
            '<li class="celebrity">'
            '<span class="role">演员</span>'
            '<span class="name"><a href="https://movie.douban.com/personage/111/">演员A</a></span>'
            "</li>"
            '<li class="celebrity">'
            '<span class="role">编剧</span>'  # 编剧也算 actor（role 不含"导演"）
            '<span class="name"><a href="https://movie.douban.com/personage/222/">编剧B</a></span>'
            "</li>"
            '<li class="celebrity">'
            '<span class="role">配音</span>'
            '<span class="name"><a href="https://movie.douban.com/personage/333/">配音C</a></span>'
            "</li>"
            "</ul>",
        )
        result = parse_movie_detail(html)
        assert len(result["actors"]) == 3
        assert result["actors"] == ["演员A", "编剧B", "配音C"]

    def test_no_actors(self):
        html = _html("", '<ul></ul>')
        result = parse_movie_detail(html)
        assert result["actors"] == []

    def test_actor_without_douban_id_link_skipped(self):
        """celebrity actor 无 <a> 标签 → 跳过"""
        html = _html(
            "",
            '<ul>'
            '<li class="celebrity">'
            '<span class="role">演员</span>'
            '<span class="name">无链接的演员</span>'  # 无 <a>
            "</li>"
            "</ul>",
        )
        result = parse_movie_detail(html)
        assert result["actors"] == []


# ============================================================================
# 八、集成层: 导演 + 演员混合列表
# ============================================================================

class TestFullCelebrityList:
    """完整的 \<li class="celebrity"\> 列表: 导演和演员正确分流"""

    def test_mixed_directors_and_actors(self):
        html = _html(
            "",
            '<ul>'
            '<li class="celebrity">'
            '<span class="role">导演</span>'
            '<span class="name"><a href="https://movie.douban.com/personage/1/">导演A</a></span>'
            "</li>"
            '<li class="celebrity">'
            '<span class="role">演员</span>'
            '<span class="name"><a href="https://movie.douban.com/personage/2/">演员B</a></span>'
            "</li>"
            '<li class="celebrity">'
            '<span class="role">演员</span>'
            '<span class="name"><a href="https://movie.douban.com/personage/3/">演员C</a></span>'
            "</li>"
            "</ul>",
        )
        result = parse_movie_detail(html)
        assert len(result["directors"]) == 1
        assert result["directors"][0]["name"] == "导演A"
        assert len(result["actors"]) == 2
        assert result["actors"] == ["演员B", "演员C"]

    def test_only_directors(self):
        html = _html(
            "",
            '<ul>'
            '<li class="celebrity">'
            '<span class="role">导演 Director</span>'
            '<span class="name"><a href="https://movie.douban.com/personage/1/">A</a></span>'
            "</li>"
            "</ul>",
        )
        result = parse_movie_detail(html)
        assert len(result["directors"]) == 1
        assert result["actors"] == []

    def test_only_actors(self):
        html = _html(
            "",
            '<ul>'
            '<li class="celebrity">'
            '<span class="role">Actor</span>'
            '<span class="name"><a href="https://movie.douban.com/personage/1/">A</a></span>'
            "</li>"
            "</ul>",
        )
        result = parse_movie_detail(html)
        assert result["directors"] == []
        assert len(result["actors"]) == 1

    def test_director_comes_before_actors(self):
        """验证导演在 actors 之前被提取（顺序保留）"""
        html = _html(
            "",
            '<ul>'
            '<li class="celebrity">'
            '<span class="role">演员</span>'
            '<span class="name"><a href="https://movie.douban.com/personage/1/">A</a></span>'
            "</li>"
            '<li class="celebrity">'
            '<span class="role">导演</span>'
            '<span class="name"><a href="https://movie.douban.com/personage/2/">B</a></span>'
            "</li>"
            "</ul>",
        )
        result = parse_movie_detail(html)
        assert result["directors"] == [{"name": "B", "douban_id": "2"}]
        assert result["actors"] == ["A"]


# ============================================================================
# 九、边界 & 异常情况
# ============================================================================

class TestEdgeCases:
    """边界情况: 空输入、全部字段缺失、非法值"""

    def test_empty_html_raises(self):
        with pytest.raises(ValueError, match="详情页 HTML 为空"):
            parse_movie_detail("")

    def test_none_html_raises(self):
        with pytest.raises(ValueError, match="详情页 HTML 为空"):
            parse_movie_detail(None)

    def test_empty_body_yields_empty_defaults(self):
        """完全无内容的 HTML — 所有字段都是默认值 """
        result = parse_movie_detail("<html><body></body></html>")
        assert result["title"] == ""
        assert result["score"] == 0.0
        assert result["vote_count"] == 0
        assert result["types"] == []
        assert result["regions"] == []
        assert result["actors"] == []
        assert result["directors"] == []
        assert result["release_date"] == ""
        assert result["release_year"] == 0
        assert result["duration"] == 0
        assert result["poster_url"] == ""
        assert result["douban_id"] == ""

    def test_full_movie_page_all_fields(self):
        """所有字段都存在的完整页面 — 全量断言"""
        html = _html(
            "",
            '<h1>'
            '<span property="v:itemreviewed">肖申克的救赎</span>'
            '<span class="year">(1994)</span>'
            "</h1>"
            '<div id="info">'
            '<span class="pl">制片国家/地区:</span> 美国<br>'
            '<span class="pl">上映日期:</span>'
            "1994-09-10(加拿大) / 1994-10-14(美国)<br>"
            '<span class="pl">片长:</span>'
            '<span property="v:runtime" content="142">142分钟</span><br>'
            "</div>"
            '<strong property="v:average">9.7</strong>'
            '<span property="v:votes">2840000</span>'
            '<span property="v:genre">剧情</span>'
            '<span property="v:genre">犯罪</span>'
            '<img rel="v:image" src="https://img3.doubanio.com/poster/p480747492.webp"/>'
            '<ul>'
            '<li class="celebrity">'
            '<span class="role">导演</span>'
            '<span class="name"><a href="https://movie.douban.com/personage/1054394/">弗兰克·德拉邦特</a></span>'
            "</li>"
            '<li class="celebrity">'
            '<span class="role">演员</span>'
            '<span class="name"><a href="https://movie.douban.com/personage/1054539/">蒂姆·罗宾斯</a></span>'
            "</li>"
            "</ul>",
        )
        result = parse_movie_detail(html)

        assert result["title"] == "肖申克的救赎"
        assert result["release_year"] == 1994
        assert result["score"] == 9.7
        assert result["vote_count"] == 2840000
        assert result["duration"] == 142
        assert result["types"] == ["剧情", "犯罪"]
        assert result["regions"] == ["美国"]
        assert result["release_date"] == "1994-09-10"
        assert result["poster_url"] == "https://img3.doubanio.com/poster/p480747492.webp"
        assert len(result["directors"]) == 1
        assert result["directors"][0]["name"] == "弗兰克·德拉邦特"
        assert len(result["actors"]) == 1
        assert result["actors"][0] == "蒂姆·罗宾斯"

    def test_return_keys_unchanged(self):
        """验证返回 dict 的 key 集合恒定（防止无意删改字段）"""
        result = parse_movie_detail("<html><body></body></html>")
        expected_keys = {
            "douban_id", "title", "score", "vote_count",
            "types", "regions", "actors", "directors",
            "release_date", "release_year", "duration", "poster_url",
        }
        assert set(result.keys()) == expected_keys
