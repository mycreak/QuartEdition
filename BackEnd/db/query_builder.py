"""
db/query_builder.py

统一查询条件构建器（支持 MySQL/MongoDB/Redis）
"""

from typing import Dict, List, Any, Optional, Union, Tuple
from enum import Enum


class Operator(Enum):
    """查询操作符枚举"""
    EQ = "="           # 等于
    NE = "!="          # 不等于
    GT = ">"           # 大于
    GTE = ">="         # 大于等于
    LT = "<"           # 小于
    LTE = "<="         # 小于等于
    LIKE = "LIKE"      # 模糊匹配
    IN = "IN"          # 在集合中
    NOT_IN = "NOT IN"  # 不在集合中
    IS_NULL = "IS NULL"    # 为空
    IS_NOT_NULL = "IS NOT NULL"  # 不为空
    BETWEEN = "BETWEEN"    # 区间
    AND = "AND"
    OR = "OR"


class ConditionBuilder:
    """
    查询条件构建器
    支持链式调用，自动生成 WHERE 条件和参数
    """
    
    def __init__(self):
        self._conditions: List[Dict[str, Any]] = []
        self._params: List[Any] = []
    
    def eq(self, field: str, value: Any) -> 'ConditionBuilder':
        self._conditions.append({
            "type": "condition",
            "field": field,
            "operator": Operator.EQ,
            "value": value
        })
        self._params.append(value)
        return self
    
    def ne(self, field: str, value: Any) -> 'ConditionBuilder':
        self._conditions.append({
            "type": "condition",
            "field": field,
            "operator": Operator.NE,
            "value": value
        })
        self._params.append(value)
        return self
    
    def gt(self, field: str, value: Any) -> 'ConditionBuilder':
        self._conditions.append({
            "type": "condition",
            "field": field,
            "operator": Operator.GT,
            "value": value
        })
        self._params.append(value)
        return self
    
    def gte(self, field: str, value: Any) -> 'ConditionBuilder':
        self._conditions.append({
            "type": "condition",
            "field": field,
            "operator": Operator.GTE,
            "value": value
        })
        self._params.append(value)
        return self
    
    def lt(self, field: str, value: Any) -> 'ConditionBuilder':
        self._conditions.append({
            "type": "condition",
            "field": field,
            "operator": Operator.LT,
            "value": value
        })
        self._params.append(value)
        return self
    
    def lte(self, field: str, value: Any) -> 'ConditionBuilder':
        self._conditions.append({
            "type": "condition",
            "field": field,
            "operator": Operator.LTE,
            "value": value
        })
        self._params.append(value)
        return self
    
    def like(self, field: str, pattern: str, position: str = "both") -> 'ConditionBuilder':
        """
        模糊匹配
        Args:
            field: 字段名
            pattern: 匹配模式（无需手动加 %）
        """
        pos_map = {
            "both": f"%{pattern}%",
            "left": f"%{pattern}",
            "right": f"{pattern}%",
            "none": pattern
        }
        if position not in pos_map:
            raise ValueError("position 必须为 'both', 'left', 'right', 'none' 之一")
        like_pattern = pos_map[position]
        self._conditions.append({
            "type": "condition",
            "field": field,
            "operator": Operator.LIKE,
            "value": like_pattern
        })
        self._params.append(like_pattern)
        return self
    
    def in_(self, field: str, values: List[Any]) -> 'ConditionBuilder':
        if not values:
            raise ValueError("IN 查询的值列表不能为空")
        self._conditions.append({
            "type": "condition",
            "field": field,
            "operator": Operator.IN,
            "value": values
        })
        self._params.extend(values)
        return self
    
    def not_in(self, field: str, values: List[Any]) -> 'ConditionBuilder':
        if not values:
            raise ValueError("NOT IN 查询的值列表不能为空")
        self._conditions.append({
            "type": "condition",
            "field": field,
            "operator": Operator.NOT_IN,
            "value": values
        })
        self._params.extend(values)
        return self
    
    def is_null(self, field: str) -> 'ConditionBuilder':
        self._conditions.append({
            "type": "condition",
            "field": field,
            "operator": Operator.IS_NULL,
            "value": None
        })
        return self
    
    def is_not_null(self, field: str) -> 'ConditionBuilder':
        self._conditions.append({
            "type": "condition",
            "field": field,
            "operator": Operator.IS_NOT_NULL,
            "value": None
        })
        return self
    
    def between(self, field: str, start: Any, end: Any) -> 'ConditionBuilder':
        self._conditions.append({
            "type": "condition",
            "field": field,
            "operator": Operator.BETWEEN,
            "value": (start, end)
        })
        self._params.extend([start, end])
        return self
    
    def and_(self) -> 'ConditionBuilder':
        self._conditions.append({"type": "operator", "operator": Operator.AND})
        return self
    
    def or_(self) -> 'ConditionBuilder':
        self._conditions.append({"type": "operator", "operator": Operator.OR})
        return self
    
    def group_start(self) -> 'ConditionBuilder':
        """添加左括号标记"""
        self._conditions.append({"type": "lparen"})
        return self
    
    def group_end(self) -> 'ConditionBuilder':
        """添加右括号标记"""
        self._conditions.append({"type": "rparen"})
        return self
    
    def build_mysql(self) -> Tuple[str, Tuple[Any, ...]]:
        """
        生成 MySQL WHERE 子句和参数
        
        Returns:
            (WHERE 条件字符串, 参数元组)
        """
        if not self._conditions:
            return "", ()
        
        parts = []
        params = []
        
        for item in self._conditions:
            item_type = item.get("type")

            if item_type == "lparen":
                parts.append("(")
            elif item_type == "rparen":
                parts.append(")")
            elif item_type == "operator":
                if item["operator"] == Operator.AND:
                    parts.append("AND")
                elif item["operator"] == Operator.OR:
                    parts.append("OR")
            elif item_type == "condition":
                field = item["field"]
                operator = item["operator"]
                value = item["value"]

                if operator == Operator.EQ:
                    parts.append(f"{field} = %s")
                    params.append(value)
                elif operator == Operator.NE:
                    parts.append(f"{field} != %s")
                    params.append(value)
                elif operator == Operator.GT:
                    parts.append(f"{field} > %s")
                    params.append(value)
                elif operator == Operator.GTE:
                    parts.append(f"{field} >= %s")
                    params.append(value)
                elif operator == Operator.LT:
                    parts.append(f"{field} < %s")
                    params.append(value)
                elif operator == Operator.LTE:
                    parts.append(f"{field} <= %s")
                    params.append(value)
                elif operator == Operator.LIKE:
                    parts.append(f"{field} LIKE %s")
                    params.append(value)
                elif operator == Operator.IN:
                    placeholders = ", ".join(["%s"] * len(value))
                    parts.append(f"{field} IN ({placeholders})")
                    params.extend(value)
                elif operator == Operator.NOT_IN:
                    placeholders = ", ".join(["%s"] * len(value))
                    parts.append(f"{field} NOT IN ({placeholders})")
                    params.extend(value)
                elif operator == Operator.IS_NULL:
                    parts.append(f"{field} IS NULL")
                elif operator == Operator.IS_NOT_NULL:
                    parts.append(f"{field} IS NOT NULL")
                elif operator == Operator.BETWEEN:
                    parts.append(f"{field} BETWEEN %s AND %s")
                    params.extend(value)
            
        where_clause = " WHERE " + " ".join(parts) if parts else ""
        return where_clause, tuple(params)
    
    def build_mongodb(self) -> Dict[str, Any]:
        """
        生成 MongoDB 查询条件字典，支持 AND/OR 逻辑和括号分组。
        """
        if not self._conditions:
            return {}

        def process_conditions(cond_list):
            """递归处理条件列表，返回 MongoDB 查询字典"""
            result = {}
            current_logic = None
            i = 0
            while i < len(cond_list):
                item = cond_list[i]
                typ = item.get("type")

                if typ == "lparen":
                    # 找到匹配的右括号，递归处理子表达式
                    depth = 1
                    j = i + 1
                    while j < len(cond_list) and depth > 0:
                        sub = cond_list[j]
                        if sub.get("type") == "lparen":
                            depth += 1
                        elif sub.get("type") == "rparen":
                            depth -= 1
                        j += 1
                    sub_expr = process_conditions(cond_list[i+1:j-1])
                    # 将子表达式合并到结果中
                    if current_logic == "AND":
                        # 隐式 AND，直接合并字段
                        for k, v in sub_expr.items():
                            if k in result:
                                # 如果字段已存在且都是操作符，需要合并
                                result[k] = {**result.get(k, {}), **v}
                            else:
                                result[k] = v
                    elif current_logic == "OR":
                        # 显式 OR，需要使用 $or
                        result = {"$or": [result, sub_expr]} if result else sub_expr
                    else:
                        result = sub_expr
                    i = j - 1
                elif typ == "operator":
                    logic = item["operator"].value
                    if logic == "AND":
                        current_logic = "AND"
                    elif logic == "OR":
                        current_logic = "OR"
                elif typ == "condition":
                    field = item["field"]
                    operator = item["operator"]
                    value = item["value"]

                    cond_dict = {}
                    if operator == Operator.EQ:
                        cond_dict[field] = value
                    elif operator == Operator.NE:
                        cond_dict[field] = {"$ne": value}
                    elif operator == Operator.GT:
                        cond_dict[field] = {"$gt": value}
                    elif operator == Operator.GTE:
                        cond_dict[field] = {"$gte": value}
                    elif operator == Operator.LT:
                        cond_dict[field] = {"$lt": value}
                    elif operator == Operator.LTE:
                        cond_dict[field] = {"$lte": value}
                    elif operator == Operator.LIKE:
                        regex_pattern = value.replace("%", ".*").replace("_", ".")
                        cond_dict[field] = {"$regex": regex_pattern, "$options": "i"}
                    elif operator == Operator.IN:
                        cond_dict[field] = {"$in": value}
                    elif operator == Operator.NOT_IN:
                        cond_dict[field] = {"$nin": value}
                    elif operator == Operator.IS_NULL:
                        cond_dict[field] = {"$eq": None}
                    elif operator == Operator.IS_NOT_NULL:
                        cond_dict[field] = {"$ne": None}
                    elif operator == Operator.BETWEEN:
                        cond_dict[field] = {"$gte": value[0], "$lte": value[1]}

                    if current_logic == "AND" or current_logic is None:
                        # 合并到 result 中
                        for k, v in cond_dict.items():
                            if k in result:
                                # 如果字段已存在且都是操作符字典，合并它们
                                if isinstance(result.get(k), dict) and isinstance(v, dict):
                                    result[k] = {**result[k], **v}
                                else:
                                    # 否则覆盖（通常不会发生）
                                    result[k] = v
                            else:
                                result[k] = v
                    elif current_logic == "OR":
                        result = {"$or": [result, cond_dict]} if result else cond_dict
                    current_logic = None  # 重置
                i += 1
            return result

        return process_conditions(self._conditions)
    
    def clear(self) -> 'ConditionBuilder':
        self._conditions = []
        self._params = []
        return self
    
    @property
    def conditions(self) -> List[Dict[str, Any]]:
        """获取条件列表（只读）"""
        return self._conditions.copy()
    
    @property
    def params(self) -> Tuple[Any, ...]:
        """获取参数元组（只读）"""
        return tuple(self._params)


class QueryBuilder:
    """
    完整查询构建器（支持分页、排序、投影）
    同时代理 ConditionBuilder 的所有条件方法，支持链式调用。
    """
    
    def __init__(self):
        self._builder = ConditionBuilder()
        self._sort: List[Tuple[str, str]] = []  # [(field, "asc"|"desc")]
        self._projection: Dict[str, int] = {}
        self._page: Optional[int] = None
        self._page_size: Optional[int] = None

    # ---------- 代理 ConditionBuilder 的所有方法 ----------
    def __getattr__(self, name: str):
        """
        将未定义的方法调用转发给内部 ConditionBuilder 实例。
        支持所有 ConditionBuilder 的链式方法，如 gt, lt, eq, like, in_, group_start 等。
        """
        builder_attr = getattr(self._builder, name, None)
        if callable(builder_attr):
            def wrapper(*args, **kwargs):
                result = builder_attr(*args, **kwargs)
                # ConditionBuilder 方法通常返回 self（即 ConditionBuilder 实例），
                # 但我们需要返回 QueryBuilder 自身以维持链式调用。
                return self
            return wrapper
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    # ---------- QueryBuilder 自有方法 ----------
    def where(self, field: str = None, value: Any = None) -> 'QueryBuilder':
        """简单 WHERE 条件（等值匹配）"""
        if field is not None and value is not None:
            self._builder.eq(field, value)
        return self
    
    def and_where(self, field: str = None, value: Any = None) -> 'QueryBuilder':
        """AND 条件（等值匹配）"""
        if field is not None and value is not None:
            self._builder.and_()
            self._builder.eq(field, value)
        return self
    
    def or_where(self, field: str = None, value: Any = None) -> 'QueryBuilder':
        """OR 条件（等值匹配）"""
        if field is not None and value is not None:
            self._builder.or_()
            self._builder.eq(field, value)
        return self
    
    def where_builder(self, builder: ConditionBuilder) -> 'QueryBuilder':
        """使用 ConditionBuilder 添加复杂条件"""
        self._builder = builder
        return self
    
    def sort(self, field: str, order: str = "asc") -> 'QueryBuilder':
        """
        排序
        Args:
            field: 字段名
            order: "asc" 或 "desc"
        """
        if order.lower() not in ["asc", "desc"]:
            raise ValueError("order 必须是 'asc' 或 'desc'")
        self._sort.append((field, order.lower()))
        return self
    
    def fields(self, **kwargs) -> 'QueryBuilder':
        """
        投影（字段选择）
        Example:
            .fields(name=1, age=1)  # 只返回 name 和 age
            .fields(password=0)     # 排除 password
        """
        self._projection.update(kwargs)
        return self
    
    def paginate(self, page: int, page_size: int) -> 'QueryBuilder':
        """
        分页
        Args:
            page: 页码（从 1 开始）
            page_size: 每页条数
        """
        if page < 1:
            raise ValueError("page 必须 >= 1")
        if page_size < 1 or page_size > 1000:
            raise ValueError("page_size 必须在 1-1000 之间")
        self._page = page
        self._page_size = page_size
        return self
    
    def build_mysql(self) -> Tuple[str, Tuple[Any, ...], int, int]:
        """
        生成 MySQL 查询语句
        Returns:
            (SQL 语句, 参数元组, page, page_size)
        """
        where_clause, params = self._builder.build_mysql()
        sql = where_clause
        
        if self._sort:
            sort_parts = [f"{field} {order.upper()}" for field, order in self._sort]
            sql += " ORDER BY " + ", ".join(sort_parts)
        
        if self._page and self._page_size:
            offset = (self._page - 1) * self._page_size
            sql += f" LIMIT %s OFFSET %s"
            params = params + (self._page_size, offset)
        
        return sql, params, self._page or 1, self._page_size or 20
    
    def build_mongodb(self) -> Dict[str, Any]:
        """
        生成 MongoDB 查询文档
        """
        query = {
            "filter": self._builder.build_mongodb()
        }
        if self._sort:
            query["sort"] = {field: 1 if order == "asc" else -1 for field, order in self._sort}
        if self._projection:
            query["projection"] = self._projection
        if self._page and self._page_size:
            query["skip"] = (self._page - 1) * self._page_size
            query["limit"] = self._page_size
        return query


    def clear(self) -> 'QueryBuilder':
        """清空所有条件"""
        self._builder.clear()
        self._sort = []
        self._projection = {}
        self._page = None
        self._page_size = None
        return self
