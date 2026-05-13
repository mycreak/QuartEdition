
"""
parse_review_list 单元测试
"""
import pytest
from crawler.parser import parse_review_list, _mask_author_name


class TestMaskAuthorName:
    """单独测试 author 去敏函数"""

    def test_author_name_empty(self):
        assert _mask_author_name("") == ""
        assert _mask_author_name(None) == ""

    def test_author_name_1_char(self):
        assert _mask_author_name("A") == "A*"
        assert _mask_author_name("  一  ") == "一*"

    def test_author_name_2_char(self):
        assert _mask_author_name("张三") == "张*"
        assert _mask_author_name("AB") == "A*"

    def test_author_name_3_char(self):
        assert _mask_author_name("王小明") == "王*明"
        assert _mask_author_name("ABC") == "A*C"

    def test_author_name_long(self):
        assert _mask_author_name("abcdefgh") == "a******h"


class TestParseReviewListNormalPath:
    """一、正常路径：标准页面"""

    def test_single_review_all_fields(self):
        html = """
        <div class="main review-item" id="12345">
            <h2><a href="/review/12345/">评论标题1</a></h2>
            <span content="2024-01-01" class="main-meta">...</span>
            <a class="name" href="/people/abc/">作者昵称</a>
            <a class="action-btn up" title="有用">999</a>
        </div></div></div>
        """
        result = parse_review_list(html)
        assert len(result) == 1
        assert result[0] == {
            "review_id": "12345",
            "title": "评论标题1",
            "author": "作**称",  # 4字 → 中间两个*
            "useful_count": 999,
            "date": "2024-01-01",
        }

    def test_three_reviews_all_fields(self):
        html = """
        <div class="main review-item" id="1"><h2><a href="/">A</a></h2><a class="name">张三</a><span content="2023-01-01" class="main-meta"></span><a class="action-btn up" title="有用">10</a></div></div></div>
        <div class="main review-item" id="2"><h2><a href="/">B</a></h2><a class="name">李四</a><span content="2023-02-01" class="main-meta"></span><a class="action-btn up" title="有用">20</a></div></div></div>
        <div class="main review-item" id="3"><h2><a href="/">C</a></h2><a class="name">王五</a><span content="2023-03-01" class="main-meta"></span><a class="action-btn up" title="有用">30</a></div></div></div>
        """
        result = parse_review_list(html)
        assert len(result) == 3
        assert result[0]["review_id"] == "1"
        assert result[1]["title"] == "B"
        assert result[2]["useful_count"] == 30

    def test_twenty_reviews_batch(self):
        html_parts = []
        for i in range(1, 21):
            part = f'<div class="main review-item" id="{i}"><h2><a href="/">Title{i}</a></h2><a class="name">Author{i}</a></div></div></div>'
            html_parts.append(part)
        html = "".join(html_parts)
        result = parse_review_list(html)
        assert len(result) == 20


class TestParseReviewListFields:
    """二、逐字段：存在/缺失/边界"""

    def test_title_with_html_entities(self):
        html = """
        <div class="main review-item" id="1">
            <h2><a href="/">Tom &amp; Jerry 影评</a></h2>
        </div></div></div>
        """
        result = parse_review_list(html)
        assert result[0]["title"] == "Tom & Jerry 影评"

    def test_title_missing_a_tag(self):
        html = """
        <div class="main review-item" id="1">
            <h2>无链接标题</h2>
        </div></div></div>
        """
        result = parse_review_list(html)
        assert result[0]["title"] == ""

    def test_author_missing_name_class(self):
        html = """
        <div class="main review-item" id="1">
            <h2><a href="/">标题</a></h2>
            <a href="/people/abc/">非name标签</a>
        </div></div></div>
        """
        result = parse_review_list(html)
        assert result[0]["author"] == ""

    def test_useful_count_zero(self):
        html = """
        <div class="main review-item" id="1">
            <h2><a href="/">标题</a></h2>
            <a class="name">张三</a>
        </div></div></div>
        """
        result = parse_review_list(html)
        assert result[0]["useful_count"] == 0

    def test_useful_count_large_number(self):
        html = """
        <div class="main review-item" id="1">
            <h2><a href="/">标题</a></h2>
            <a class="name">李四</a>
            <a class="action-btn up" title="有用">99999</a>
        </div></div></div>
        """
        result = parse_review_list(html)
        assert result[0]["useful_count"] == 99999

    def test_date_missing(self):
        html = """
        <div class="main review-item" id="1">
            <h2><a href="/">标题</a></h2>
            <span class="main-meta">无content属性</span>
        </div></div></div>
        """
        result = parse_review_list(html)
        assert result[0]["date"] == ""

    def test_date_bad_format(self):
        html = """
        <div class="main review-item" id="1">
            <h2><a href="/">标题</a></h2>
            <span content="2024/01/01" class="main-meta">...</span>
        </div></div></div>
        """
        result = parse_review_list(html)
        assert result[0]["date"] == ""


class TestParseReviewListDomDegradation:
    """三、DOM结构变化：严格降级到宽松"""

    def test_strict_match_success(self):
        html = """
        <div class="main review-item" id="1">
            <h2><a href="/">标题</a></h2>
            <a class="name">张三</a>
        </div></div></div>
        """
        result = parse_review_list(html)
        assert len(result) == 1

    def test_fallback_to_relaxed_match(self):
        # 缺 2 个 </div>，走宽松 (?=<div...) 路径
        html = """
        <div class="main review-item" id="1"><h2><a href="/">A</a></h2><a class="name">甲</a></div>
        <div class="main review-item" id="2"><h2><a href="/">B</a></h2><a class="name">乙</a></div>
        """
        result = parse_review_list(html)
        assert len(result) == 2

    def test_extra_nested_tags_in_block(self):
        html = """
        <div class="main review-item" id="1">
            <div class="some-wrapper">
                <h2><a href="/">嵌套标题</a></h2>
            </div>
            <a class="name">嵌套作者</a>
        </div></div></div>
        """
        result = parse_review_list(html)
        assert result[0]["title"] == "嵌套标题"


class TestParseReviewListMixedMissing:
    """四、混合字段缺失"""

    def test_only_review_id_all_fields_missing(self, caplog):
        html = """
        <div class="main review-item" id="12345">
            <p>什么可提取字段都没有</p>
        </div></div></div>
        """
        result = parse_review_list(html)
        assert len(result) == 1
        assert result[0]["review_id"] == "12345"
        assert result[0]["title"] == ""
        assert result[0]["author"] == ""
        assert result[0]["date"] == ""
        assert result[0]["useful_count"] == 0

        # 告警场景⑤：全缺
        assert "所有可提取字段均为空" in caplog.text

    def test_missing_title_only(self):
        html = """
        <div class="main review-item" id="1">
            <h2>缺a标签标题</h2>
            <a class="name">李四</a>
            <span content="2024-02-01" class="main-meta"></span>
            <a class="action-btn up" title="有用">50</a>
        </div></div></div>
        """
        result = parse_review_list(html)
        assert result[0]["title"] == ""
        assert result[0]["author"] == "李*"
        assert result[0]["useful_count"] == 50

    def test_missing_author_only(self):
        html = """
        <div class="main review-item" id="1">
            <h2><a href="/">标题</a></h2>
            <span content="2024-03-01" class="main-meta"></span>
            <a class="action-btn up" title="有用">60</a>
        </div></div></div>
        """
        result = parse_review_list(html)
        assert result[0]["author"] == ""


class TestParseReviewListException:
    """五、异常路径"""

    def test_empty_html_raises(self):
        with pytest.raises(ValueError, match="评论列表 HTML 为空"):
            parse_review_list("")

    def test_none_html_raises(self):
        with pytest.raises(ValueError, match="评论列表 HTML 为空"):
            parse_review_list(None)

    def test_no_review_items_returns_empty(self, caplog):
        html = """
        <html><body>
            <div class="some-other-content">普通页面，没有任何 review-item</div>
        </body></html>
        """
        result = parse_review_list(html)
        assert result == []

        # 告警场景④：无块
        assert "未找到任何 review-item 块" in caplog.text


class TestParseReviewListReturnKeys:
    """六、返回 key 集合恒定"""

    def test_return_keys_constant(self):
        html = """
        <div class="main review-item" id="1">
            <h2><a href="/">标题</a></h2>
            <a class="name">作者</a>
        </div></div></div>
        """
        result = parse_review_list(html)
        expected = {"review_id", "title", "author", "useful_count", "date"}
        assert set(result[0].keys()) == expected
