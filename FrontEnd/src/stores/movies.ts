import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import type { Movie, MovieDetail } from '@/types/movie'
import { moviesApi } from '@/api/movies'

export const useMovieStore = defineStore('movies', () => {
  const movies = ref<Movie[]>([])
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(15)
  const loading = ref(false)
  const error = ref('')
  const filters = reactive({
    keyword: '',
    type_num: undefined as number | undefined,
    region: undefined as string | undefined,
    year: undefined as number | undefined,
  })
  const intervalIds = ref<string[]>([])

  async function fetchList(p = 1): Promise<void> {
    loading.value = true
    error.value = ''
    page.value = p
    try {
      const res = await moviesApi.list({
        keyword: filters.keyword || undefined,
        type_num: filters.type_num,
        interval_ids: intervalIds.value.length ? intervalIds.value.join(',') : undefined,
        region: filters.region,
        year: filters.year,
        page: p,
        page_size: pageSize.value,
      })
      movies.value = res.data.items
      total.value = res.data.total
    } catch (err: unknown) {
      error.value = (err as { response?: { data?: { error?: string } } })?.response?.data?.error || '加载失败'
      movies.value = []
      total.value = 0
    } finally {
      loading.value = false
    }
  }

  async function fetchDetail(id: number): Promise<MovieDetail | null> {
    loading.value = true
    error.value = ''
    try {
      const res = await moviesApi.detail(id)
      return res.data
    } catch (err: unknown) {
      error.value = (err as { response?: { data?: { error?: string } } })?.response?.data?.error || '加载失败'
      return null
    } finally {
      loading.value = false
    }
  }

  function setFilter(keyword: string, type_num?: number, iids?: string[], region?: string, year?: number): void {
    filters.keyword = keyword
    filters.type_num = type_num
    filters.region = region
    filters.year = year
    if (iids !== undefined) {
      intervalIds.value = iids
    }
    fetchList(1)
  }

  function setIntervalIds(iids: string[]): void {
    intervalIds.value = iids
  }

  function clearFilters(): void {
    filters.keyword = ''
    filters.type_num = undefined
    filters.region = undefined
    filters.year = undefined
    intervalIds.value = []
  }

  return {
    movies, total, page, pageSize, loading, error, filters, intervalIds,
    fetchList, fetchDetail, setFilter, setIntervalIds, clearFilters,
  }
})
