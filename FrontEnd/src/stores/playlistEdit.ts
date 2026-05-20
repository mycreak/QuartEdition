import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import type { Movie } from '@/types/movie'

const SESSION_KEY = 'playlistEditState'

interface PlaylistEditState {
  id: number | null
  title: string
  description: string
  cover_url: string
  movie_ids: number[]
  sort_order: number
  publish_at: string | null
  unpublish_at: string | null
  movies: Movie[]
}

function loadFromSession(): PlaylistEditState | null {
  try {
    const data = sessionStorage.getItem(SESSION_KEY)
    if (data) {
      return JSON.parse(data) as PlaylistEditState
    }
  } catch {
    // ignore
  }
  return null
}

function saveToSession(state: PlaylistEditState): void {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(state))
  } catch {
    // ignore
  }
}

function clearSession(): void {
  sessionStorage.removeItem(SESSION_KEY)
}

export const usePlaylistEditStore = defineStore('playlistEdit', () => {
  const id = ref<number | null>(null)
  const title = ref('')
  const description = ref('')
  const cover_url = ref('')
  const movie_ids = ref<number[]>([])
  const sort_order = ref(0)
  const publish_at = ref<string | null>(null)
  const unpublish_at = ref<string | null>(null)
  const movies = ref<Movie[]>([])

  const hasUnsavedChanges = computed(() => {
    // 简单判断：只要输入了标题或有电影就算有变化
    return title.value.trim() !== '' || movie_ids.value.length > 0
  })

  function initState(editId: number | null = null): void {
    id.value = editId
    title.value = ''
    description.value = ''
    cover_url.value = ''
    movie_ids.value = []
    sort_order.value = 0
    publish_at.value = null
    unpublish_at.value = null
    movies.value = []
  }

  function loadStateFromSession(): boolean {
    const saved = loadFromSession()
    if (saved) {
      id.value = saved.id
      title.value = saved.title
      description.value = saved.description
      cover_url.value = saved.cover_url
      movie_ids.value = saved.movie_ids
      sort_order.value = saved.sort_order
      publish_at.value = saved.publish_at
      unpublish_at.value = saved.unpublish_at
      movies.value = saved.movies
      return true
    }
    return false
  }

  function addMovie(movie: Movie): void {
    if (!movie_ids.value.includes(movie.id)) {
      movie_ids.value.push(movie.id)
      movies.value.push(movie)
    }
  }

  function removeMovie(movieId: number): void {
    const idx = movie_ids.value.indexOf(movieId)
    if (idx !== -1) {
      movie_ids.value.splice(idx, 1)
      movies.value.splice(idx, 1)
    }
  }

  function saveToSessionStorage(): void {
    saveToSession({
      id: id.value,
      title: title.value,
      description: description.value,
      cover_url: cover_url.value,
      movie_ids: movie_ids.value,
      sort_order: sort_order.value,
      publish_at: publish_at.value,
      unpublish_at: unpublish_at.value,
      movies: movies.value,
    })
  }

  function clearState(): void {
    initState()
    clearSession()
  }

  // 自动保存到 sessionStorage
  watch([title, description, cover_url, movie_ids, sort_order, publish_at, unpublish_at, movies], () => {
    saveToSessionStorage()
  }, { deep: true })

  return {
    id,
    title,
    description,
    cover_url,
    movie_ids,
    sort_order,
    publish_at,
    unpublish_at,
    movies,
    hasUnsavedChanges,
    initState,
    loadStateFromSession,
    addMovie,
    removeMovie,
    saveToSessionStorage,
    clearState,
  }
})
