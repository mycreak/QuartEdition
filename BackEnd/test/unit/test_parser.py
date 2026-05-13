
"""
电影解析器 单元测试
覆盖内容:
    - parse_movie_list: 豆瓣榜单 JSON 列表解析
    - parse_movie_detail: 电影详情页 HTML 解析
"""

import pytest
from crawler.parser import parse_movie_list, parse_movie_detail


# ============================================================================
# 一、parse_movie_list 测试
# ============================================================================

class TestParseMovieList:
    """测试 parse_movie_list: 从豆瓣榜单 JSON API 提取 douban_id"""

    def test_normal_list(self):
        """正常电影列表"""
        data = [
            {"id": 1292052, "title": "肖申克的救赎", "score": 9.7},
            {"id": 1291549, "title": "霸王别姬", "score": 9.6},
            {"id": 1292722, "title": "泰坦尼克号", "score": 9.4},
        ]
        result = parse_movie_list(data)
        assert len(result) == 3
        assert result[0]["douban_id"] == "1292052"
        assert result[0]["title"] == "肖申克的救赎"

    def test_empty_list(self):
        """空列表应该抛出 ValueError"""
        with pytest.raises(ValueError, match="电影列表为空"):
            parse_movie_list([])

    def test_list_is_none(self):
        """None 列表应该抛出 ValueError"""
        with pytest.raises(ValueError, match="电影列表为空"):
            parse_movie_list(None)

    def test_single_movie(self):
        """只有一部电影"""
        data = [{"id": 1292052, "title": "肖申克的救赎"}]
        result = parse_movie_list(data)
        assert len(result) == 1
        assert result[0]["douban_id"] == "1292052"

    def test_item_without_id(self):
        """缺少 id 字段的项应该被跳过"""
        data = [
            {"id": 1292052, "title": "肖申克的救赎"},
            {"title": "无ID电影"},
            {"id": 1291549, "title": "霸王别姬"},
        ]
        result = parse_movie_list(data)
        assert len(result) == 2

    def test_item_without_title(self):
        """缺少 title 字段应该使用空字符串"""
        data = [
            {"id": 1292052},
            {"id": 1291549, "title": "霸王别姬"},
        ]
        result = parse_movie_list(data)
        assert len(result) == 2
        assert result[0]["title"] == ""
        assert result[1]["title"] == "霸王别姬"

    def test_id_is_int(self):
        """id 字段为 int 类型时转成 str"""
        data = [{"id": 1292052, "title": "肖申克的救赎"}]
        result = parse_movie_list(data)
        assert isinstance(result[0]["douban_id"], str)
        assert result[0]["douban_id"] == "1292052"

    def test_id_is_string(self):
        """id 字段已经是 str 类型"""
        data = [{"id": "1292052", "title": "肖申克的救赎"}]
        result = parse_movie_list(data)
        assert result[0]["douban_id"] == "1292052"

    def test_multiple_items_from_real_api(self):
        """模拟真实的榜单 API 返回数据"""
        data = [
            {"id": 1292052, "title": "肖申克的救赎", "score": 9.7, "vote_count": 12345},
            {"id": 1291549, "title": "霸王别姬", "score": 9.6, "vote_count": 23456},
            {"id": 1292722, "title": "泰坦尼克号", "score": 9.4, "vote_count": 34567},
            {"id": 1292064, "title": "楚门的世界", "score": 9.3, "vote_count": 45678},
        ]
        result = parse_movie_list(data)
        assert len(result) == 4
        # 只提取 id 和 title
        for item in result:
            assert "score" not in item
            assert "vote_count" not in item

    def test_fifty_movies(self):
        """50 部电影批量解析"""
        data = [{"id": 1000000 + i, "title": f"电影{i}"} for i in range(50)]
        result = parse_movie_list(data)
        assert len(result) == 50


# ============================================================================
# 二、parse_movie_detail 测试
# ============================================================================

class TestParseMovieDetail:
    """测试 parse_movie_detail: 从豆瓣详情页 HTML 提取电影信息"""

    SAMPLE_HTML = r"""
<!DOCTYPE html>
<html>
<head><title>肖申克的救赎 (1994)</title></head>
<body>
<div id="wrapper">
    <div id="content">
        <h1>
            <span property="v:itemreviewed">肖申克的救赎</span>
            <span class="year">(1994)</span>
        </h1>
        <div id="info">
            <span class="pl">制片国家/地区:</span> 美国<br>
            <span class="pl">上映日期:</span>
            <span property="v:initialReleaseDate" content="1994-09-10">1994-09-10(加拿大)</span><br>
            <span class="pl">片长:</span>
            <span property="v:runtime" content="142">142分钟</span><br>
        </div>
        <div class="rating_wrap">
            <strong property="v:average">9.7</strong>
            <span property="v:votes">2800000</span>
        </div>
        <span property="v:genre">剧情</span>
        <span property="v:genre">犯罪</span>
        <div id="celebrities">
            <ul>
                <li class="celebrity">
                    <span class="role">导演</span>
                    <span class="name"><a href="https://movie.douban.com/personage/1054394/">弗兰克·德拉邦特</a></span>
                </li>
                <li class="celebrity">
                    <span class="role">演员</span>
                    <span class="name"><a href="https://movie.douban.com/personage/1054539/">蒂姆·罗宾斯</a></span>
                </li>
                <li class="celebrity">
                    <span class="role">演员</span>
                    <span class="name"><a href="https://movie.douban.com/personage/1054450/">摩根·弗里曼</a></span>
                </li>
            </ul>
        </div>
        <link property="v:image" content="https://img9.doubanio.com/view/photo/m_ratio_poster/public/p480747492.jpg"/>
    </div>
</div>
</body>
</html>
"""

    def test_basic_detail(self):
        """正常解析电影详情"""
        result = parse_movie_detail(self.SAMPLE_HTML)
        assert result["title"] == "肖申克的救赎"
        assert result["release_year"] == 1994
        assert result["duration"] == 142

    def test_score_and_votes(self):
        """评分和评分人数"""
        result = parse_movie_detail(self.SAMPLE_HTML)
        assert result["score"] == 9.7
        assert result["vote_count"] == 2800000

    def test_types(self):
        """电影类型"""
        result = parse_movie_detail(self.SAMPLE_HTML)
        assert "剧情" in result["types"]
        assert "犯罪" in result["types"]

    def test_regions(self):
        """电影地区（国家/地区）"""
        result = parse_movie_detail(self.SAMPLE_HTML)
        assert "美国" in result["regions"]

    def test_release_date(self):
        """上映日期"""
        result = parse_movie_detail(self.SAMPLE_HTML)
        assert result["release_date"] == "1994-09-10"

    def test_directors(self):
        """导演信息"""
        result = parse_movie_detail(self.SAMPLE_HTML)
        assert len(result["directors"]) == 1
        assert result["directors"][0]["name"] == "弗兰克·德拉邦特"
        assert result["directors"][0]["douban_id"] == "1054394"

    def test_actors(self):
        """演员列表"""
        result = parse_movie_detail(self.SAMPLE_HTML)
        assert len(result["actors"]) == 2
        assert "蒂姆·罗宾斯" in result["actors"]
        assert "摩根·弗里曼" in result["actors"]

    def test_poster_url(self):
        """封面图片 URL"""
        result = parse_movie_detail(self.SAMPLE_HTML)
        assert "p480747492.jpg" in result["poster_url"]

    def test_empty_html(self):
        """空 HTML 应该抛出 ValueError"""
        with pytest.raises(ValueError, match="详情页 HTML 为空"):
            parse_movie_detail("")
        with pytest.raises(ValueError, match="详情页 HTML 为空"):
            parse_movie_detail(None)


class TestParseMovieDetailEdgeCases:
    """测试 parse_movie_detail 边界情况"""

    def test_no_score(self):
        """无评分信息"""
        html = r"""
        <html><body>
            <h1><span property="v:itemreviewed">无评分电影</span><span class="year">(2020)</span></h1>
        </body></html>
        """
        result = parse_movie_detail(html)
        assert result["score"] == 0.0
        assert result["vote_count"] == 0

    def test_no_title(self):
        """无标题"""
        html = r"""
        <html><body>
            <h1><span class="year">(2020)</span></h1>
        </body></html>
        """
        result = parse_movie_detail(html)
        assert result["title"] == ""

    def test_no_year(self):
        """无年份"""
        html = r"""
        <html><body>
            <h1><span property="v:itemreviewed">无年份电影</span></h1>
        </body></html>
        """
        result = parse_movie_detail(html)
        assert result["release_year"] == 0

    def test_no_directors(self):
        """无导演信息"""
        html = r"""
        <html><body>
            <h1><span property="v:itemreviewed">无导演电影</span><span class="year">(2020)</span></h1>
            <div id="celebrities"><ul></ul></div>
        </body></html>
        """
        result = parse_movie_detail(html)
        assert result["directors"] == []

    def test_no_actors(self):
        """无演员信息"""
        html = r"""
        <html><body>
            <h1><span property="v:itemreviewed">无演员电影</span><span class="year">(2020)</span></h1>
            <div id="info">
                <span class="pl">片长:</span> <span property="v:runtime" content="100">100分钟</span>
            </div>
        </body></html>
        """
        result = parse_movie_detail(html)
        assert result["actors"] == []

    def test_multiple_directors(self):
        """联合执导（多导演）"""
        html = r"""
        <html><body>
            <h1><span property="v:itemreviewed">多导演电影</span><span class="year">(2020)</span></h1>
            <ul>
                <li class="celebrity">
                    <span class="role">导演</span>
                    <span class="name"><a href="https://movie.douban.com/personage/1001/">导演A</a></span>
                </li>
                <li class="celebrity">
                    <span class="role">导演</span>
                    <span class="name"><a href="https://movie.douban.com/personage/1002/">导演B</a></span>
                </li>
                <li class="celebrity">
                    <span class="role">演员</span>
                    <span class="name"><a href="https://movie.douban.com/personage/2001/">演员C</a></span>
                </li>
            </ul>
        </body></html>
        """
        result = parse_movie_detail(html)
        assert len(result["directors"]) == 2
        assert result["directors"][0]["name"] == "导演A"
        assert result["directors"][1]["name"] == "导演B"

    def test_multiple_regions(self):
        """多个制片国家/地区"""
        html = r"""
        <html><body>
            <h1><span property="v:itemreviewed">合拍片</span><span class="year">(2020)</span></h1>
            <div id="info">
                <span class="pl">制片国家/地区:</span> 中国大陆 / 美国 / 英国<br>
            </div>
        </body></html>
        """
        result = parse_movie_detail(html)
        assert "中国大陆" in result["regions"]
        assert "美国" in result["regions"]
        assert "英国" in result["regions"]

    def test_no_poster(self):
        """无封面图片"""
        html = r"""
        <html><body>
            <h1><span property="v:itemreviewed">无海报电影</span><span class="year">(2020)</span></h1>
        </body></html>
        """
        result = parse_movie_detail(html)
        assert result["poster_url"] == ""

    def test_no_duration(self):
        """无片长信息"""
        html = r"""
        <html><body>
            <h1><span property="v:itemreviewed">无片长电影</span><span class="year">(2020)</span></h1>
            <div id="info"><span class="pl">上映日期:</span> 2020-01-01<br></div>
        </body></html>
        """
        result = parse_movie_detail(html)
        assert result["duration"] == 0

    def test_no_release_date(self):
        """无上映日期"""
        html = r"""
        <html><body>
            <h1><span property="v:itemreviewed">无日期电影</span><span class="year">(2020)</span></h1>
            <div id="info"><span class="pl">制片国家/地区:</span> 美国<br></div>
        </body></html>
        """
        result = parse_movie_detail(html)
        assert result["release_date"] == ""

    def test_poster_url_extraction(self):
        """封面 URL 从 different 标签提取"""
        html = r"""
        <html><body>
            <h1><span property="v:itemreviewed">有海报</span><span class="year">(2020)</span></h1>
            <link property="v:image" content="https://example.com/poster.jpg"/>
        </body></html>
        """
        result = parse_movie_detail(html)
        assert result["poster_url"] == "https://example.com/poster.jpg"


class TestParseMovieDetailRealScenarios:
    """模拟真实豆瓣页面可能会出现的各种情况"""

    def test_score_with_decimal(self):
        """评分带小数"""
        html = r"""
        <html><body>
            <h1><span property="v:itemreviewed">电影</span><span class="year">(2020)</span></h1>
            <strong property="v:average">8.5</strong>
            <span property="v:votes">50000</span>
        </body></html>
        """
        result = parse_movie_detail(html)
        assert result["score"] == 8.5
        assert result["vote_count"] == 50000

    def test_score_is_int_str(self):
        """评分是整数字符串"""
        html = r"""
        <html><body>
            <h1><span property="v:itemreviewed">电影</span><span class="year">(2020)</span></h1>
            <strong property="v:average">8</strong>
            <span property="v:votes">30000</span>
        </body></html>
        """
        result = parse_movie_detail(html)
        assert result["score"] == 8.0

    def test_html_with_special_chars(self):
        """HTML 包含特殊字符"""
        html = r"""
        <html><body>
            <h1><span property="v:itemreviewed">电影 &amp; 电视</span><span class="year">(2020)</span></h1>
            <strong property="v:average">8.0</strong>
            <span property="v:votes">1000</span>
        </body></html>
        """
        result = parse_movie_detail(html)
        assert result["title"] == "电影 & 电视"

    def test_no_votes(self):
        """无评分人数"""
        html = r"""
        <html><body>
            <h1><span property="v:itemreviewed">新电影</span><span class="year">(2024)</span></h1>
            <strong property="v:average">0.0</strong>
        </body></html>
        """
        result = parse_movie_detail(html)
        assert result["vote_count"] == 0

