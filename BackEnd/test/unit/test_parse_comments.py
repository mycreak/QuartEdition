
"""
parse_comments 单元测试
"""
import pytest
from crawler.parser import parse_comments


class TestParseCommentsBasic:
    """基础功能测试"""

    def test_single_comment_rating(self):
        html = """<div class="comment-item" data-cid="1"><span class="comment-info"><a href="/people/abc">作者</a></span><span class="allstar40 rating"></span><span class="short">正文</span></div><script>"""
        result = parse_comments(html)
        assert len(result) == 1
        assert result[0]["rating"] == 4.0

    def test_single_comment_all_stars(self):
        test_cases = [
            ("allstar50", 5.0),
            ("allstar45", 4.5),
            ("allstar40", 4.0),
            ("allstar35", 3.5),
            ("allstar30", 3.0),
            ("allstar25", 2.5),
            ("allstar20", 2.0),
            ("allstar15", 1.5),
            ("allstar10", 1.0),
            ("allstar05", 0.5),
        ]
        for idx, (star_class, expected) in enumerate(test_cases):
            html = f"""<div class="comment-item" data-cid="{100+idx}"><span class="comment-info"><a href="/people/a">作者</a></span><span class="{star_class} rating"></span><span class="short">正文</span></div><script>"""
            result = parse_comments(html)
            assert result[0]["rating"] == expected

    def test_author_masking(self):
        test_cases = [
            ("张三", "张*"),
            ("王小明", "王*明"),
        ]
        for idx, (raw, expected) in enumerate(test_cases):
            html = f"""<div class="comment-item" data-cid="{200+idx}"><span class="comment-info"><a href="/people/a">{raw}</a></span><span class="short">正文</span></div><script>"""
            result = parse_comments(html)
            assert result[0]["author"] == expected

    def test_empty_html_raises(self):
        with pytest.raises(ValueError):
            parse_comments("")

    def test_no_comment_items(self):
        html = """<html><body>...</body></html>"""
        with pytest.raises(ValueError):
            parse_comments(html)

