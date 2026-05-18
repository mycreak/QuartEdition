import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/auth/LoginView.vue'),
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/auth/RegisterView.vue'),
  },
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/user/HomeView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/movies/:id',
    name: 'MovieDetail',
    component: () => import('@/views/user/MovieDetail.vue'),
    meta: { requiresAuth: true },
  },
  {
      path: '/reviews',
      name: 'Reviews',
      component: () => import('@/views/user/ReviewsView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/profile',
      name: 'Profile',
      component: () => import('@/views/user/ProfileView.vue'),
      meta: { requiresAuth: true },
    },
  {
    path: '/admin',
    name: 'Admin',
    component: () => import('@/components/layout/AdminLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'Dashboard',
        component: () => import('@/views/admin/DashboardView.vue'),
        meta: { requiresAuth: true, permission: 'system:monitor' },
      },
      {
        path: 'crawler',
        name: 'AdminCrawler',
        component: () => import('@/views/admin/TasksView.vue'),
        meta: { requiresAuth: true, permission: 'crawler:task:write' },
      },
      {
        path: 'movies',
        name: 'AdminMovies',
        component: () => import('@/views/admin/MoviesView.vue'),
        meta: { requiresAuth: true, permission: 'movie:read' },
      },
      {
        path: 'movies/:id',
        name: 'AdminMovieDetail',
        component: () => import('@/views/admin/AdminMovieDetail.vue'),
        meta: { requiresAuth: true, permission: 'movie:read' },
      },
      {
        path: 'reviews',
        name: 'AdminReviews',
        component: () => import('@/views/admin/ReviewsView.vue'),
        meta: { requiresAuth: true, permission: 'comment:read' },
      },
      {
        path: 'users',
        name: 'AdminUsers',
        component: () => import('@/views/admin/UsersView.vue'),
        meta: { requiresAuth: true, permission: 'user:manage' },
      },
      {
        path: 'infra',
        name: 'AdminInfra',
        component: () => import('@/views/admin/InfraView.vue'),
        meta: { requiresAuth: true, permission: ['infra:proxy:read', 'infra:cookie:read', 'system:monitor'] },
      },
      {
          path: 'douban-ids',
          name: 'AdminDoubanIds',
          component: () => import('@/views/admin/DoubanIdsView.vue'),
          meta: { requiresAuth: true, permission: 'crawler:task:read' },
        },
        {
          path: 'profile',
          name: 'AdminProfile',
          component: () => import('@/views/admin/AdminProfileView.vue'),
          meta: { requiresAuth: true },
        }
      ],
    },
  {
    path: '/403',
    name: 'Forbidden',
    component: () => import('@/views/ForbiddenView.vue'),
  },
  {
    path: '/test/tos-image',
    name: 'TosImageTest',
    component: () => import('@/views/TosImageTestView.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
