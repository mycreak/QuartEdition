"""
查询构建器单元测试
测试 db/query_builder.py 中的 ConditionBuilder 和 QueryBuilder
"""

import pytest
from db.query_builder import ConditionBuilder, QueryBuilder, Operator


class TestConditionBuilder:
    """ConditionBuilder 基础条件构建器测试"""

    def test_single_operators_eq(self):
        """测试等值查询 EQ"""
        builder = ConditionBuilder()
        builder.eq("name", "test")
        sql, params = builder.build_mysql()
        assert sql == " WHERE name = %s"
        assert params == ("test",)

    def test_single_operators_ne(self):
        """测试不等查询 NE"""
        builder = ConditionBuilder()
        builder.ne("age", 18)
        sql, params = builder.build_mysql()
        assert sql == " WHERE age != %s"
        assert params == (18,)

    def test_single_operators_gt(self):
        """测试大于查询 GT"""
        builder = ConditionBuilder()
        builder.gt("rating", 8.0)
        sql, params = builder.build_mysql()
        assert sql == " WHERE rating > %s"
        assert params == (8.0,)

    def test_single_operators_gte(self):
        """测试大于等于 GTE"""
        builder = ConditionBuilder()
        builder.gte("year", 2020)
        sql, params = builder.build_mysql()
        assert sql == " WHERE year >= %s"
        assert params == (2020,)

    def test_single_operators_lt(self):
        """测试小于查询 LT"""
        builder = ConditionBuilder()
        builder.lt("price", 100)
        sql, params = builder.build_mysql()
        assert sql == " WHERE price < %s"
        assert params == (100,)

    def test_single_operators_lte(self):
        """测试小于等于 LTE"""
        builder = ConditionBuilder()
        builder.lte("count", 50)
        sql, params = builder.build_mysql()
        assert sql == " WHERE count <= %s"
        assert params == (50,)

    def test_single_operators_is_null(self):
        """测试空值查询 IS_NULL"""
        builder = ConditionBuilder()
        builder.is_null("deleted_at")
        sql, params = builder.build_mysql()
        assert sql == " WHERE deleted_at IS NULL"
        assert params == ()

    def test_single_operators_is_not_null(self):
        """测试非空查询 IS_NOT_NULL"""
        builder = ConditionBuilder()
        builder.is_not_null("updated_at")
        sql, params = builder.build_mysql()
        assert sql == " WHERE updated_at IS NOT NULL"
        assert params == ()

    def test_like_patterns_both(self):
        """测试两端模糊匹配"""
        builder = ConditionBuilder()
        builder.like("title", "action", position="both")
        sql, params = builder.build_mysql()
        assert sql == " WHERE title LIKE %s"
        assert params == ("%action%",)

    def test_like_patterns_left(self):
        """测试前缀匹配"""
        builder = ConditionBuilder()
        builder.like("title", "test", position="left")
        sql, params = builder.build_mysql()
        assert sql == " WHERE title LIKE %s"
        assert params == ("%test",)

    def test_like_patterns_right(self):
        """测试后缀匹配"""
        builder = ConditionBuilder()
        builder.like("title", "movie", position="right")
        sql, params = builder.build_mysql()
        assert sql == " WHERE title LIKE %s"
        assert params == ("movie%",)

    def test_like_patterns_none(self):
        """测试精确匹配"""
        builder = ConditionBuilder()
        builder.like("title", "exact", position="none")
        sql, params = builder.build_mysql()
        assert sql == " WHERE title LIKE %s"
        assert params == ("exact",)

    def test_like_invalid_position(self):
        """测试非法位置参数"""
        builder = ConditionBuilder()
        with pytest.raises(ValueError, match="position 必须为"):
            builder.like("title", "test", position="invalid")

    def test_in_queries_normal(self):
        """测试 IN 查询正常情况"""
        builder = ConditionBuilder()
        builder.in_("id", [1, 2, 3])
        sql, params = builder.build_mysql()
        assert sql == " WHERE id IN (%s, %s, %s)"
        assert params == (1, 2, 3)

    def test_not_in_queries_normal(self):
        """测试 NOT IN 查询正常情况"""
        builder = ConditionBuilder()
        builder.not_in("status", ["active", "pending"])
        sql, params = builder.build_mysql()
        assert sql == " WHERE status NOT IN (%s, %s)"
        assert params == ("active", "pending")

    def test_in_empty_list(self):
        """测试 IN 空列表错误"""
        builder = ConditionBuilder()
        with pytest.raises(ValueError, match="IN 查询的值列表不能为空"):
            builder.in_("id", [])

    def test_not_in_empty_list(self):
        """测试 NOT IN 空列表错误"""
        builder = ConditionBuilder()
        with pytest.raises(ValueError, match="NOT IN 查询的值列表不能为空"):
            builder.not_in("id", [])

    def test_between_numeric(self):
        """测试数值区间"""
        builder = ConditionBuilder()
        builder.between("age", 18, 65)
        sql, params = builder.build_mysql()
        assert sql == " WHERE age BETWEEN %s AND %s"
        assert params == (18, 65)

    def test_between_date(self):
        """测试日期区间"""
        builder = ConditionBuilder()
        builder.between("created_at", "2020-01-01", "2020-12-31")
        sql, params = builder.build_mysql()
        assert sql == " WHERE created_at BETWEEN %s AND %s"
        assert params == ("2020-01-01", "2020-12-31")

    def test_and_combinations_two(self):
        """测试两个条件 AND"""
        builder = ConditionBuilder()
        builder.eq("status", "active").and_().eq("role", "user")
        sql, params = builder.build_mysql()
        assert sql == " WHERE status = %s AND role = %s"
        assert params == ("active", "user")

    def test_or_combinations_two(self):
        """测试两个条件 OR"""
        builder = ConditionBuilder()
        builder.eq("status", "active").or_().eq("role", "admin")
        sql, params = builder.build_mysql()
        assert sql == " WHERE status = %s OR role = %s"
        assert params == ("active", "admin")

    def test_and_or_mixed_multiple(self):
        """测试多个条件混合 AND"""
        builder = ConditionBuilder()
        (builder
            .eq("status", "active")
            .and_()
            .gt("rating", 8.0)
            .and_()
            .lt("year", 2023))
        sql, params = builder.build_mysql()
        assert "WHERE" in sql
        assert "AND" in sql
        assert len(params) == 3

    def test_parentheses_simple_group(self):
        """测试简单括号分组"""
        builder = ConditionBuilder()
        (builder
            .group_start()
            .eq("a", 1)
            .and_()
            .eq("b", 2)
            .group_end())
        sql, params = builder.build_mysql()
        assert sql == " WHERE ( a = %s AND b = %s )"
        assert params == (1, 2)

    def test_parentheses_complex_group(self):
        """测试复杂分组 (A OR B) AND C"""
        builder = ConditionBuilder()
        (builder
            .group_start()
            .eq("a", 1)
            .or_()
            .eq("b", 2)
            .group_end()
            .and_()
            .eq("c", 3))
        sql, params = builder.build_mysql()
        assert sql == " WHERE ( a = %s OR b = %s ) AND c = %s"
        assert params == (1, 2, 3)

    def test_parentheses_nested(self):
        """测试嵌套分组"""
        builder = ConditionBuilder()
        (builder
            .eq("a", 1)
            .or_()
            .group_start()
            .eq("b", 2)
            .and_()
            .eq("c", 3)
            .group_end())
        sql, params = builder.build_mysql()
        assert sql == " WHERE a = %s OR ( b = %s AND c = %s )"
        assert params == (1, 2, 3)

    def test_mongodb_eq(self):
        """测试 MongoDB 等值查询"""
        builder = ConditionBuilder()
        builder.eq("field", "value")
        query = builder.build_mongodb()
        assert query == {"field": "value"}

    def test_mongodb_comparison(self):
        """测试 MongoDB 比较查询"""
        builder = ConditionBuilder()
        builder.gt("age", 18)
        query = builder.build_mongodb()
        assert query == {"age": {"$gt": 18}}

    def test_mongodb_like(self):
        """测试 MongoDB LIKE 转正则"""
        builder = ConditionBuilder()
        builder.like("title", "test", position="both")
        query = builder.build_mongodb()
        assert "title" in query
        assert "$regex" in query["title"]
        assert "$options" in query["title"]

    def test_mongodb_in(self):
        """测试 MongoDB IN 查询"""
        builder = ConditionBuilder()
        builder.in_("id", [1, 2, 3])
        query = builder.build_mongodb()
        assert query == {"id": {"$in": [1, 2, 3]}}

    def test_mongodb_between(self):
        """测试 MongoDB 区间查询"""
        builder = ConditionBuilder()
        builder.between("age", 18, 65)
        query = builder.build_mongodb()
        assert query == {"age": {"$gte": 18, "$lte": 65}}

    def test_mongodb_and(self):
        """测试 MongoDB AND 组合"""
        builder = ConditionBuilder()
        builder.eq("a", 1).and_().eq("b", 2)
        query = builder.build_mongodb()
        assert query == {"a": 1, "b": 2}

    def test_mongodb_or(self):
        """测试 MongoDB OR 组合"""
        builder = ConditionBuilder()
        builder.eq("a", 1).or_().eq("b", 2)
        query = builder.build_mongodb()
        assert query == {"$or": [{"a": 1}, {"b": 2}]}

    def test_clear_conditions(self):
        """测试清空条件列表"""
        builder = ConditionBuilder()
        builder.eq("a", 1).gt("b", 2)
        assert len(builder.conditions) > 0
        assert len(builder.params) > 0
        
        builder.clear()
        assert len(builder.conditions) == 0
        assert len(builder.params) == 0

    def test_clear_and_reuse(self):
        """测试清空后继续使用"""
        builder = ConditionBuilder()
        builder.eq("a", 1)
        builder.clear()
        builder.eq("b", 2)
        sql, params = builder.build_mysql()
        assert sql == " WHERE b = %s"
        assert params == (2,)

    def test_no_conditions(self):
        """测试无任何条件"""
        builder = ConditionBuilder()
        sql, params = builder.build_mysql()
        assert sql == ""
        assert params == ()

    def test_properties_readonly(self):
        """测试 conditions 和 params 只读属性"""
        builder = ConditionBuilder()
        builder.eq("a", 1)
        
        conditions = builder.conditions
        params = builder.params
        
        # 修改返回的副本不应影响内部状态
        conditions.append({"test": "data"})
        assert len(builder.conditions) == 1


class TestQueryBuilder:
    """QueryBuilder 完整查询构建器测试"""

    def test_sort_single_asc(self):
        """测试单字段升序"""
        qb = QueryBuilder()
        qb.sort("name", "asc")
        sql, params, _, _ = qb.build_mysql()
        assert "ORDER BY name ASC" in sql

    def test_sort_single_desc(self):
        """测试单字段降序"""
        qb = QueryBuilder()
        qb.sort("name", "desc")
        sql, params, _, _ = qb.build_mysql()
        assert "ORDER BY name DESC" in sql

    def test_sort_multiple(self):
        """测试多字段排序"""
        qb = QueryBuilder()
        qb.sort("rating", "desc").sort("created_at", "asc")
        sql, params, _, _ = qb.build_mysql()
        assert "ORDER BY rating DESC, created_at ASC" in sql

    def test_sort_invalid_order(self):
        """测试非法排序方向"""
        qb = QueryBuilder()
        with pytest.raises(ValueError, match="order 必须是"):
            qb.sort("name", "invalid")

    def test_fields_include(self):
        """测试包含字段投影"""
        qb = QueryBuilder()
        qb.fields(name=1, age=1)
        query = qb.build_mongodb()
        assert query["projection"] == {"name": 1, "age": 1}

    def test_fields_exclude(self):
        """测试排除字段投影"""
        qb = QueryBuilder()
        qb.fields(password=0)
        query = qb.build_mongodb()
        assert query["projection"] == {"password": 0}

    def test_pagination_normal(self):
        """测试正常分页"""
        qb = QueryBuilder()
        qb.paginate(2, 20)
        sql, params, page, page_size = qb.build_mysql()
        assert "LIMIT %s OFFSET %s" in sql
        assert page == 2
        assert page_size == 20
        assert params == (20, 20)

    def test_pagination_page_less_than_one(self):
        """测试 page 小于 1"""
        qb = QueryBuilder()
        with pytest.raises(ValueError, match="page 必须 >="):
            qb.paginate(0, 20)

    def test_pagination_page_size_less_than_one(self):
        """测试 page_size 小于 1"""
        qb = QueryBuilder()
        with pytest.raises(ValueError, match="page_size 必须在"):
            qb.paginate(1, 0)

    def test_pagination_page_size_exceeds_limit(self):
        """测试 page_size 超过 1000"""
        qb = QueryBuilder()
        with pytest.raises(ValueError, match="page_size 必须在"):
            qb.paginate(1, 1001)

    def test_chained_complete(self):
        """测试完整链式调用"""
        qb = QueryBuilder()
        (qb
            .eq("status", "active")
            .gt("rating", 8.0)
            .sort("rating", "desc")
            .sort("created_at", "asc")
            .paginate(2, 20))
        sql, params, page, page_size = qb.build_mysql()
        assert "WHERE" in sql
        assert "ORDER BY" in sql
        assert "LIMIT" in sql
        assert page == 2
        assert page_size == 20

    def test_where_method(self):
        """测试 where 方法"""
        qb = QueryBuilder()
        qb.where("status", "active")
        sql, params, _, _ = qb.build_mysql()
        assert "WHERE status = %s" in sql
        assert params == ("active",)

    def test_and_where_method(self):
        """测试 and_where 方法"""
        qb = QueryBuilder()
        qb.where("status", "active").and_where("role", "user")
        sql, params, _, _ = qb.build_mysql()
        assert "WHERE status = %s AND role = %s" in sql

    def test_or_where_method(self):
        """测试 or_where 方法"""
        qb = QueryBuilder()
        qb.where("status", "active").or_where("role", "admin")
        sql, params, _, _ = qb.build_mysql()
        assert "WHERE status = %s OR role = %s" in sql

    def test_where_builder(self):
        """测试 where_builder 方法"""
        inner = ConditionBuilder()
        inner.eq("a", 1).and_().eq("b", 2)
        
        qb = QueryBuilder()
        qb.where_builder(inner)
        sql, params, _, _ = qb.build_mysql()
        assert "WHERE a = %s AND b = %s" in sql

    def test_clear_all(self):
        """测试清空所有条件"""
        qb = QueryBuilder()
        qb.eq("a", 1).sort("b", "asc").paginate(1, 10)
        qb.clear()
        
        sql, params, page, page_size = qb.build_mysql()
        assert sql == ""
        assert page == 1
        assert page_size == 20
        
        mongo_query = qb.build_mongodb()
        assert mongo_query["filter"] == {}
        assert "sort" not in mongo_query
        assert "projection" not in mongo_query
        assert "skip" not in mongo_query
        assert "limit" not in mongo_query

    def test_mongodb_build_complete(self):
        """测试 MongoDB 完整查询构建"""
        qb = QueryBuilder()
        (qb
            .eq("status", "active")
            .sort("rating", "desc")
            .fields(name=1, rating=1)
            .paginate(2, 20))
        query = qb.build_mongodb()
        
        assert "filter" in query
        assert "sort" in query
        assert "projection" in query
        assert "skip" in query
        assert "limit" in query
        assert query["skip"] == 20
        assert query["limit"] == 20
