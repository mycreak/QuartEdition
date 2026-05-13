"""
用户端端点集成测试
测试路由: /user/*
"""
import pytest
from typing import Dict, Any
from test.conftest import generate_unique_username, generate_valid_password


@pytest.mark.integration
@pytest.mark.user_endpoint
class TestUserFilterPacket:
    """
    SC-User-Filter - 筛选器端点测试 (GET /user/filter-packet)
    """

    async def get_auth_headers(self, client, test_user):
        """获取认证 Headers"""
        login_resp = await client.post(
            "/auth/login",
            json={
                "username": test_user.username,
                "password": "TestPass123"
            }
        )
        assert login_resp.status_code == 200
        login_data = await login_resp.get_json()
        token = login_data["token"]
        return {"Authorization": f"Bearer {token}"}

    async def test_filter_packet_success(self, client, test_user):
        """
        TC-User-Filter-01: 登录后访问
        预期: 200 OK，返回 types 和 intervals 两个字段
        """
        headers = await self.get_auth_headers(client, test_user)
        response = await client.get("/user/filter-packet", headers=headers)
        assert response.status_code == 200
        data = await response.get_json()
        assert "types" in data
        assert "intervals" in data

    async def test_filter_packet_types_structure(self, client, test_user):
        """
        TC-User-Filter-02: types 字段完整性
        预期: 包含 type_num, type_name, movie_count
        """
        headers = await self.get_auth_headers(client, test_user)
        response = await client.get("/user/filter-packet", headers=headers)
        data = await response.get_json()
        if len(data["types"]) > 0:
            first_type = data["types"][0]
            assert "type_num" in first_type
            assert "type_name" in first_type
            assert "movie_count" in first_type

    async def test_filter_packet_intervals_structure(self, client, test_user):
        """
        TC-User-Filter-03: intervals 字段完整性
        预期: 包含 interval_id, label, movie_count
        """
        headers = await self.get_auth_headers(client, test_user)
        response = await client.get("/user/filter-packet", headers=headers)
        data = await response.get_json()
        if len(data["intervals"]) > 0:
            first_interval = data["intervals"][0]
            assert "interval_id" in first_interval
            assert "label" in first_interval
            assert "movie_count" in first_interval

    async def test_filter_packet_unauthorized(self, client):
        """
        TC-User-Filter-04: 未登录访问
        预期: 401 Unauthorized
        """
        response = await client.get("/user/filter-packet")
        assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.user_endpoint
class TestUserGenres:
    """
    SC-User-Genres - 类型端点测试 (GET /user/genres & /user/genre-stats)
    """

    async def get_auth_headers(self, client, test_user):
        """获取认证 Headers"""
        login_resp = await client.post(
            "/auth/login",
            json={
                "username": test_user.username,
                "password": "TestPass123"
            }
        )
        assert login_resp.status_code == 200
        login_data = await login_resp.get_json()
        token = login_data["token"]
        return {"Authorization": f"Bearer {token}"}

    async def test_list_genres_success(self, client, test_user):
        """
        TC-User-Genres-01: list_genres 返回格式正确
        预期: 200 OK，items 包含 id, name 字段
        """
        headers = await self.get_auth_headers(client, test_user)
        response = await client.get("/user/genres", headers=headers)
        assert response.status_code == 200
        data = await response.get_json()
        assert "items" in data
        if len(data["items"]) > 0:
            first_genre = data["items"][0]
            assert "id" in first_genre
            assert "name" in first_genre

    async def test_genre_stats_success(self, client, test_user):
        """
        TC-User-Genres-02: genre_stats 返回格式正确
        预期: 200 OK，items 包含 type_num, genre_name, movie_count, avg_rating
        """
        headers = await self.get_auth_headers(client, test_user)
        response = await client.get("/user/genre-stats", headers=headers)
        assert response.status_code == 200
        data = await response.get_json()
        assert "items" in data

    async def test_list_genres_unauthorized(self, client):
        """
        TC-User-Genres-03: list_genres 未登录访问
        预期: 401 Unauthorized
        """
        response = await client.get("/user/genres")
        assert response.status_code == 401

    async def test_genre_stats_unauthorized(self, client):
        """
        TC-User-Genres-04: genre_stats 未登录访问
        预期: 401 Unauthorized
        """
        response = await client.get("/user/genre-stats")
        assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.user_endpoint
class TestUserMovies:
    """
    SC-User-Movies - 电影列表端点测试 (GET /user/movies)
    """

    async def get_auth_headers(self, client, test_user):
        """获取认证 Headers"""
        login_resp = await client.post(
            "/auth/login",
            json={
                "username": test_user.username,
                "password": "TestPass123"
            }
        )
        assert login_resp.status_code == 200
        login_data = await login_resp.get_json()
        token = login_data["token"]
        return {"Authorization": f"Bearer {token}"}

    async def test_list_movies_default_pagination(self, client, test_user):
        """
        TC-User-Movies-01: 无参数访问（默认分页）
        预期: 200 OK，返回 items, total, page, page_size
        """
        headers = await self.get_auth_headers(client, test_user)
        response = await client.get("/user/movies", headers=headers)
        assert response.status_code == 200
        data = await response.get_json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data

    async def test_list_movies_keyword_search(self, client, test_user):
        """
        TC-User-Movies-02: keyword 搜索（匹配片名）
        预期: 200 OK，items 中只包含符合搜索的电影（如果有）
        """
        headers = await self.get_auth_headers(client, test_user)
        # 搜一个不太可能的词
        response = await client.get(
            "/user/movies",
            query_string={"keyword": "非存在电影123"},
            headers=headers
        )
        assert response.status_code == 200

    async def test_list_movies_type_num_filter(self, client, test_user):
        """
        TC-User-Movies-03: type_num 过滤
        预期: 200 OK（如果有 type_num 的电影）
        """
        headers = await self.get_auth_headers(client, test_user)
        # 用一个常见的 type_num（比如 11 剧情）
        response = await client.get(
            "/user/movies",
            query_string={"type_num": 11},
            headers=headers
        )
        assert response.status_code == 200

    async def test_list_movies_interval_single_filter(self, client, test_user):
        """
        TC-User-Movies-04: interval_ids 评分区间过滤（单个区间）
        预期: 200 OK
        """
        headers = await self.get_auth_headers(client, test_user)
        response = await client.get(
            "/user/movies",
            query_string={"interval_ids": "100:90"},
            headers=headers
        )
        assert response.status_code == 200

    async def test_list_movies_interval_multi_filter(self, client, test_user):
        """
        TC-User-Movies-05: interval_ids 评分区间过滤（多个区间，逗号分隔）
        预期: 200 OK
        """
        headers = await self.get_auth_headers(client, test_user)
        response = await client.get(
            "/user/movies",
            query_string={"interval_ids": "100:90,90:80"},
            headers=headers
        )
        assert response.status_code == 200

    async def test_list_movies_multi_filter(self, client, test_user):
        """
        TC-User-Movies-06: 多条件组合过滤
        预期: 200 OK
        """
        headers = await self.get_auth_headers(client, test_user)
        response = await client.get(
            "/user/movies",
            query_string={
                "keyword": "电影",
                "type_num": 11,
                "interval_ids": "100:90,90:80"
            },
            headers=headers
        )
        assert response.status_code == 200

    async def test_list_movies_custom_pagination(self, client, test_user):
        """
        TC-User-Movies-07: 自定义分页（page=2, page_size=10）
        预期: 200 OK，items 长度不超过 10，page 为 2
        """
        headers = await self.get_auth_headers(client, test_user)
        response = await client.get(
            "/user/movies",
            query_string={"page": 2, "page_size": 10},
            headers=headers
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["page"] == 2
        assert data["page_size"] == 10
        assert len(data["items"]) <= 10

    async def test_list_movies_unauthorized(self, client):
        """
        TC-User-Movies-08: 未登录访问
        预期: 401 Unauthorized
        """
        response = await client.get("/user/movies")
        assert response.status_code == 401

    async def test_list_movies_published_only(self, client, test_user, db):
        """
        TC-User-Movies-09: 电影列表只包含已上架电影
        预期: 200 OK（默认就是 published_only）
        """
        headers = await self.get_auth_headers(client, test_user)
        response = await client.get("/user/movies", headers=headers)
        assert response.status_code == 200


@pytest.mark.integration
@pytest.mark.user_endpoint
class TestUserMovieDetail:
    """
    SC-User-Movie-Detail - 电影详情端点测试 (GET /user/movies/<id>)
    """

    async def get_auth_headers(self, client, test_user):
        """获取认证 Headers"""
        login_resp = await client.post(
            "/auth/login",
            json={
                "username": test_user.username,
                "password": "TestPass123"
            }
        )
        assert login_resp.status_code == 200
        login_data = await login_resp.get_json()
        token = login_data["token"]
        return {"Authorization": f"Bearer {token}"}

    async def test_movie_detail_nonexistent(self, client, test_user):
        """
        TC-User-Movie-Detail-02: 访问不存在的电影
        预期: 404 Not Found
        """
        headers = await self.get_auth_headers(client, test_user)
        response = await client.get("/user/movies/999999999", headers=headers)
        assert response.status_code == 404

    async def test_movie_detail_unauthorized(self, client):
        """
        TC-User-Movie-Detail-04: 未登录访问
        预期: 401 Unauthorized
        """
        response = await client.get("/user/movies/1")
        assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.user_endpoint
class TestUserReviews:
    """
    SC-User-Reviews - 评论端点测试 (GET /user/reviews & /user/comments)
    """

    async def get_auth_headers(self, client, test_user):
        """获取认证 Headers"""
        login_resp = await client.post(
            "/auth/login",
            json={
                "username": test_user.username,
                "password": "TestPass123"
            }
        )
        assert login_resp.status_code == 200
        login_data = await login_resp.get_json()
        token = login_data["token"]
        return {"Authorization": f"Bearer {token}"}

    async def test_list_reviews_without_movie_id(self, client, test_user):
        """
        TC-User-Reviews-01: list_reviews 无 movie_id 返回所有长评
        预期: 200 OK
        """
        headers = await self.get_auth_headers(client, test_user)
        response = await client.get("/user/reviews", headers=headers)
        assert response.status_code == 200

    async def test_list_reviews_with_movie_id(self, client, test_user):
        """
        TC-User-Reviews-02: list_reviews 指定 movie_id 过滤
        预期: 200 OK
        """
        headers = await self.get_auth_headers(client, test_user)
        response = await client.get(
            "/user/reviews",
            query_string={"movie_id": 1},
            headers=headers
        )
        assert response.status_code == 200

    async def test_list_reviews_pagination(self, client, test_user):
        """
        TC-User-Reviews-03: list_reviews 分页功能
        预期: 200 OK
        """
        headers = await self.get_auth_headers(client, test_user)
        response = await client.get(
            "/user/reviews",
            query_string={"page": 2, "page_size": 5},
            headers=headers
        )
        assert response.status_code == 200

    async def test_list_comments_without_movie_id(self, client, test_user):
        """
        TC-User-Reviews-04: list_comments 无 movie_id 返回所有短评
        预期: 200 OK
        """
        headers = await self.get_auth_headers(client, test_user)
        response = await client.get("/user/comments", headers=headers)
        assert response.status_code == 200

    async def test_list_comments_with_movie_id(self, client, test_user):
        """
        TC-User-Reviews-05: list_comments 指定 movie_id 过滤
        预期: 200 OK
        """
        headers = await self.get_auth_headers(client, test_user)
        response = await client.get(
            "/user/comments",
            query_string={"movie_id": 1},
            headers=headers
        )
        assert response.status_code == 200

    async def test_list_comments_pagination(self, client, test_user):
        """
        TC-User-Reviews-06: list_comments 分页功能
        预期: 200 OK
        """
        headers = await self.get_auth_headers(client, test_user)
        response = await client.get(
            "/user/comments",
            query_string={"page": 2, "page_size": 5},
            headers=headers
        )
        assert response.status_code == 200

    async def test_list_reviews_unauthorized(self, client):
        """
        TC-User-Reviews-07: list_reviews 未登录访问
        预期: 401 Unauthorized
        """
        response = await client.get("/user/reviews")
        assert response.status_code == 401

    async def test_list_comments_unauthorized(self, client):
        """
        TC-User-Reviews-08: list_comments 未登录访问
        预期: 401 Unauthorized
        """
        response = await client.get("/user/comments")
        assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.user_endpoint
class TestUserFullSequence:
    """
    SC-User-Full-Sequence - 完整流程集成测试
    """

    async def get_auth_headers(self, client, username, password):
        """获取认证 Headers"""
        login_resp = await client.post(
            "/auth/login",
            json={
                "username": username,
                "password": password
            }
        )
        assert login_resp.status_code == 200
        login_data = await login_resp.get_json()
        token = login_data["token"]
        return {"Authorization": f"Bearer {token}"}

    async def test_full_browse_sequence(self, client, clean_auth_data):
        """
        TC-User-Full-Sequence-01: 完整浏览流程：
        注册 → 登录 → 查看筛选器 → 查类型统计 → 搜电影 → 看评论
        预期: 所有步骤成功
        """
        # 1. 注册
        username = generate_unique_username("testfull")
        password = generate_valid_password()
        register_resp = await client.post(
            "/auth/register",
            json={
                "username": username,
                "password": password,
                "display_name": "全流程测试用户"
            }
        )
        assert register_resp.status_code == 201

        # 2. 登录
        headers = await self.get_auth_headers(client, username, password)

        # 3. 查看筛选器
        filter_resp = await client.get("/user/filter-packet", headers=headers)
        assert filter_resp.status_code == 200

        # 4. 查看类型统计
        genre_stats_resp = await client.get("/user/genre-stats", headers=headers)
        assert genre_stats_resp.status_code == 200

        # 5. 搜索电影
        movies_resp = await client.get(
            "/user/movies",
            query_string={"keyword": "电影", "page": 1, "page_size": 20},
            headers=headers
        )
        assert movies_resp.status_code == 200
        movies_data = await movies_resp.get_json()

        # 6. 如果有电影，看评论
        if len(movies_data["items"]) > 0:
            movie_id = movies_data["items"][0].get("id")
            if movie_id:
                reviews_resp = await client.get(
                    "/user/reviews",
                    query_string={"movie_id": movie_id},
                    headers=headers
                )
                assert reviews_resp.status_code == 200

                comments_resp = await client.get(
                    "/user/comments",
                    query_string={"movie_id": movie_id},
                    headers=headers
                )
                assert comments_resp.status_code == 200
