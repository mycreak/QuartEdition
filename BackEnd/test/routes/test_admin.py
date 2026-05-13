"""
管理端端点集成测试
"""
import pytest
import time

pytestmark = [pytest.mark.integration, pytest.mark.admin]


class TestAdminPermissions:
    """权限验证测试"""

    async def get_auth_headers(self, client, username: str, password: str) -> dict:
        """登录获取认证头"""
        response = await client.post("/auth/login", json={
            "username": username,
            "password": password
        })
        assert response.status_code == 200
        data = await response.get_json()
        token = data["token"]
        return {"Authorization": f"Bearer {token}"}

    async def test_admin_endpoint_unauthorized(self, client):
        """未登录访问管理端端点 -> 401"""
        response = await client.get("/admin/users")
        assert response.status_code == 401

    async def test_admin_endpoint_forbidden(self, client, test_user):
        """登录但无权限访问 -> 403"""
        headers = await self.get_auth_headers(client, test_user.username, "TestPass123")
        response = await client.get("/admin/users", headers=headers)
        assert response.status_code == 403


class TestAdminUsers:
    """用户管理测试"""

    async def get_auth_headers(self, client, username: str, password: str) -> dict:
        """登录获取认证头"""
        response = await client.post("/auth/login", json={
            "username": username,
            "password": password
        })
        assert response.status_code == 200
        data = await response.get_json()
        token = data["token"]
        return {"Authorization": f"Bearer {token}"}

    async def test_create_user_success(self, client, admin_user):
        """创建用户成功"""
        from test.conftest import generate_unique_username
        unique_username = generate_unique_username("admin_test")
        
        headers = await self.get_auth_headers(client, admin_user.username, "AdminPass123")
        response = await client.post("/admin/users", headers=headers, json={
            "username": unique_username,
            "password": "NewPass123",
            "display_name": "新用户"
        })
        assert response.status_code == 201

    async def test_create_user_duplicate(self, client, admin_user):
        """创建重复用户 -> 409"""
        from test.conftest import generate_unique_username
        unique_username = generate_unique_username("admin_test_dup")
        
        headers = await self.get_auth_headers(client, admin_user.username, "AdminPass123")
        await client.post("/admin/users", headers=headers, json={
            "username": unique_username,
            "password": "NewPass123",
            "display_name": "重复用户"
        })
        # 再次创建
        response = await client.post("/admin/users", headers=headers, json={
            "username": unique_username,
            "password": "NewPass123",
            "display_name": "重复用户2"
        })
        assert response.status_code == 409

    async def test_patch_user_success(self, client, admin_user, test_user):
        """修改用户信息"""
        headers = await self.get_auth_headers(client, admin_user.username, "AdminPass123")
        response = await client.patch(f"/admin/users/{test_user.id}", headers=headers, json={
            "display_name": "修改后的用户"
        })
        assert response.status_code == 200

    async def test_patch_user_disable_self(self, client, admin_user):
        """禁用自己 -> 422"""
        headers = await self.get_auth_headers(client, admin_user.username, "AdminPass123")
        response = await client.patch(f"/admin/users/{admin_user.id}", headers=headers, json={
            "is_active": False
        })
        assert response.status_code == 422

    async def test_set_user_permissions(self, client, admin_user, test_user):
        """设置用户权限"""
        headers = await self.get_auth_headers(client, admin_user.username, "AdminPass123")
        response = await client.post(f"/admin/users/{test_user.id}/permissions", headers=headers, json={
            "permission_codes": ["movie:read"]
        })
        assert response.status_code == 200


class TestAdminMovies:
    """电影管理测试"""

    async def get_auth_headers(self, client, username: str, password: str) -> dict:
        """登录获取认证头"""
        response = await client.post("/auth/login", json={
            "username": username,
            "password": password
        })
        assert response.status_code == 200
        data = await response.get_json()
        token = data["token"]
        return {"Authorization": f"Bearer {token}"}

    async def test_get_movie_list(self, client, admin_user, db):
        """获取电影列表"""
        from test.conftest import generate_test_movie_data, create_test_movie
        movie_data = generate_test_movie_data(published=True)
        await create_test_movie(db, movie_data)
        
        headers = await self.get_auth_headers(client, admin_user.username, "AdminPass123")
        response = await client.get("/admin/movies", headers=headers)
        assert response.status_code == 200

    async def test_get_movie_detail(self, client, admin_user, db):
        """获取电影详情"""
        from test.conftest import generate_test_movie_data, create_test_movie
        movie_data = generate_test_movie_data(published=True)
        movie_id = await create_test_movie(db, movie_data)
        
        headers = await self.get_auth_headers(client, admin_user.username, "AdminPass123")
        response = await client.get(f"/admin/movies/{movie_id}", headers=headers)
        assert response.status_code == 200

    async def test_patch_movie(self, client, admin_user, db):
        """编辑电影信息"""
        from test.conftest import generate_test_movie_data, create_test_movie
        movie_data = generate_test_movie_data(published=True)
        movie_id = await create_test_movie(db, movie_data)
        
        headers = await self.get_auth_headers(client, admin_user.username, "AdminPass123")
        response = await client.patch(f"/admin/movies/{movie_id}", headers=headers, json={
            "title": "修改后的标题"
        })
        assert response.status_code == 200

    async def test_publish_unpublish_movie(self, client, admin_user, db):
        """电影上下架"""
        from test.conftest import generate_test_movie_data, create_test_movie
        movie_data = generate_test_movie_data(published=False)
        movie_id = await create_test_movie(db, movie_data)
        
        headers = await self.get_auth_headers(client, admin_user.username, "AdminPass123")
        
        # 上架
        response = await client.post(f"/admin/movies/{movie_id}/publish", headers=headers)
        assert response.status_code == 200
        
        # 下架
        response = await client.post(f"/admin/movies/{movie_id}/unpublish", headers=headers)
        assert response.status_code == 200


class TestAdminReviews:
    """评论管理测试"""

    async def get_auth_headers(self, client, username: str, password: str) -> dict:
        """登录获取认证头"""
        response = await client.post("/auth/login", json={
            "username": username,
            "password": password
        })
        assert response.status_code == 200
        data = await response.get_json()
        token = data["token"]
        return {"Authorization": f"Bearer {token}"}

    async def test_get_review_list(self, client, admin_user):
        """获取长评列表"""
        headers = await self.get_auth_headers(client, admin_user.username, "AdminPass123")
        response = await client.get("/admin/reviews", headers=headers)
        assert response.status_code == 200

    async def test_get_comment_list(self, client, admin_user):
        """获取短评列表"""
        headers = await self.get_auth_headers(client, admin_user.username, "AdminPass123")
        response = await client.get("/admin/comments", headers=headers)
        assert response.status_code == 200


class TestAdminTasks:
    """任务与 douban_id 测试"""

    async def get_auth_headers(self, client, username: str, password: str) -> dict:
        """登录获取认证头"""
        response = await client.post("/auth/login", json={
            "username": username,
            "password": password
        })
        assert response.status_code == 200
        data = await response.get_json()
        token = data["token"]
        return {"Authorization": f"Bearer {token}"}

    async def test_submit_task_invalid_type(self, client, admin_user):
        """提交不支持的任务类型 -> 400"""
        headers = await self.get_auth_headers(client, admin_user.username, "AdminPass123")
        response = await client.post("/admin/tasks", headers=headers, json={
            "type": "invalid_task_type"
        })
        assert response.status_code == 400

    async def test_get_task_progress(self, client, admin_user):
        """获取任务进度"""
        headers = await self.get_auth_headers(client, admin_user.username, "AdminPass123")
        response = await client.get("/admin/tasks", headers=headers)
        assert response.status_code == 200

    async def test_get_task_history(self, client, admin_user):
        """获取任务历史"""
        headers = await self.get_auth_headers(client, admin_user.username, "AdminPass123")
        response = await client.get("/admin/task-history", headers=headers)
        assert response.status_code == 200

    async def test_get_douban_id_list(self, client, admin_user):
        """获取 douban_id 列表"""
        headers = await self.get_auth_headers(client, admin_user.username, "AdminPass123")
        response = await client.get("/admin/douban-ids", headers=headers)
        assert response.status_code == 200


class TestAdminInfra:
    """基础设施测试"""

    async def get_auth_headers(self, client, username: str, password: str) -> dict:
        """登录获取认证头"""
        response = await client.post("/auth/login", json={
            "username": username,
            "password": password
        })
        assert response.status_code == 200
        data = await response.get_json()
        token = data["token"]
        return {"Authorization": f"Bearer {token}"}

    async def test_get_system_status(self, client, admin_user):
        """获取系统状态"""
        headers = await self.get_auth_headers(client, admin_user.username, "AdminPass123")
        response = await client.get("/admin/status", headers=headers)
        assert response.status_code == 200

    async def test_get_task_queue(self, client, admin_user):
        """获取任务队列"""
        headers = await self.get_auth_headers(client, admin_user.username, "AdminPass123")
        response = await client.get("/admin/tasks/queue", headers=headers)
        assert response.status_code == 200

    async def test_get_logs(self, client, admin_user):
        """获取日志"""
        headers = await self.get_auth_headers(client, admin_user.username, "AdminPass123")
        response = await client.get("/admin/logs?limit=10", headers=headers)
        assert response.status_code == 200

    async def test_get_proxies(self, client, admin_user):
        """获取代理池"""
        headers = await self.get_auth_headers(client, admin_user.username, "AdminPass123")
        response = await client.get("/admin/proxies", headers=headers)
        assert response.status_code == 200

    @pytest.mark.skip(reason="Cookie 服务可能未启动")
    async def test_get_cookies(self, client, admin_user):
        """获取 Cookie 列表"""
        headers = await self.get_auth_headers(client, admin_user.username, "AdminPass123")
        response = await client.get("/admin/cookies", headers=headers)
        # Cookie 服务可能未启动，接受 200 或 503
        assert response.status_code in [200, 503]
