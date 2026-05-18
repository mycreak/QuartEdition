/**
 * api/ws.ts — WebSocket 连接管理器

 * 后端 WS 端点: /ws/notifications?token=<JWT>
 * 消息类型:
 *   system_status  — Monitor 每 10s 广播全体管理员（含 Puller/Worker/CPU/DB/队列）
 *   task_failure   — 任务失败时推送给提交者
 *   task_success   — 任务成功时推送给提交者
 *   worker_crash   — Worker 崩溃时广播全体管理员
 *   storage_alert  — DB 写入异常突增时广播全体管理员

 * 特性:
 *   - 单例模式（全局唯一连接）
 *   - 心跳 ping/pong 保持连接
 *   - 断线指数退避重连（1s→2s→4s→8s→max 30s）
 *   - 事件回调分派（onSystemStatus / onTaskFailure / onTaskSuccess / onWorkerCrash）
 */

type MessageHandler = (data: any) => void

interface ConnectionState {
  status: 'disconnected' | 'connecting' | 'connected'
  retryCount: number
}

class WsManager {
  private _ws: WebSocket | null = null
  private _state: ConnectionState = { status: 'disconnected', retryCount: 0 }
  private _pingTimer: ReturnType<typeof setInterval> | null = null
  private _reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private _handlers: Record<string, MessageHandler[]> = {}
  private _token: string | null = null
  private _suppressErrors: boolean = false

  get status(): string { return this._state.status }
  get retryCount(): number { return this._state.retryCount }

  /** 注册消息处理回调 */
  on(type: string, handler: MessageHandler): () => void {
    if (!this._handlers[type]) this._handlers[type] = []
    this._handlers[type].push(handler)
    return () => {
      this._handlers[type] = this._handlers[type].filter(h => h !== handler)
    }
  }

  /** 建立连接 */
  connect(token: string): void {
    this._token = token
    
    if (this._ws && (this._ws.readyState === WebSocket.OPEN || this._ws.readyState === WebSocket.CONNECTING)) {
      return
    }

    this._cleanup()
    this._state.status = 'connecting'

    const wsUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/notifications'
    const url = `${wsUrl}?token=${encodeURIComponent(token)}`

    try {
      this._ws = new WebSocket(url)
    } catch {
      this._state.status = 'disconnected'
      this._scheduleReconnect()
      return
    }

    this._ws.addEventListener('open', () => {
      console.log('[WS] Connected successfully')
      this._state.status = 'connected'
      this._state.retryCount = 0
      this._suppressErrors = false
      this._startPing()
    })

    this._ws.addEventListener('message', (evt) => {
      try {
        if (evt.data === 'pong') return
        
        const msg = JSON.parse(evt.data)
        console.log('[WS] Received message:', msg)
        if (msg.type && this._handlers[msg.type]) {
          this._handlers[msg.type].forEach(h => h(msg))
        }
      } catch (e) {
        console.error('[WS] Failed to parse message:', evt.data, e)
      }
    })

    this._ws.addEventListener('close', () => {
      this._state.status = 'disconnected'
      this._stopPing()
      this._scheduleReconnect()
    })

    this._ws.addEventListener('error', (evt) => {
      // 抑制错误日志，避免控制台刷屏
      evt.stopPropagation()
      evt.preventDefault()
      // close 事件会紧随 error 触发，不在此处理
    })
  }

  /** 断开连接 */
  disconnect(): void {
    this._token = null
    this._cleanup()
    this._state.status = 'disconnected'
  }

  private _startPing(): void {
    this._stopPing()
    this._pingTimer = setInterval(() => {
      if (this._ws?.readyState === WebSocket.OPEN) {
        this._ws.send('ping')
      }
    }, 30_000)
  }

  private _stopPing(): void {
    if (this._pingTimer) {
      clearInterval(this._pingTimer)
      this._pingTimer = null
    }
  }

  private _scheduleReconnect(): void {
    if (!this._token) return
    if (this._reconnectTimer) return
    const delay = Math.min(1000 * Math.pow(2, this._state.retryCount), 30_000)
    this._state.retryCount++
    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null
      if (this._token) {
        this.connect(this._token)
      }
    }, delay)
  }

  private _cleanup(): void {
    this._stopPing()
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer)
      this._reconnectTimer = null
    }
    if (this._ws) {
      this._ws.close()
      this._ws = null
    }
  }
}

export const wsManager = new WsManager()
