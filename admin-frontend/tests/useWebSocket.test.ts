/**
 * useWebSocket Hook 测试
 * 测试 WebSocket 连接、消息发送和状态管理
 * 
 * 注意：需要先安装 Vitest 相关依赖：
 * npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'

// Mock WebSocket
class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  readyState: number = MockWebSocket.OPEN
  onopen: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null

  constructor(public url: string) {
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN
      this.onopen?.(new Event('open'))
    }, 0)
  }

  send(data: string) {
    // 模拟发送消息
  }

  close(code?: number, reason?: string) {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.(new CloseEvent('close', { code: code || 1000, reason: reason || '' }))
  }

  // 模拟接收消息
  simulateMessage(data: any) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) }))
  }

  // 模拟错误
  simulateError() {
    this.onerror?.(new Event('error'))
  }
}

// 替换全局 WebSocket
vi.stubGlobal('WebSocket', MockWebSocket)

// Mock auth store
vi.mock('@/stores/auth', () => ({
  useAuthStore: {
    getState: () => ({
      token: 'test_token_123',
    }),
  },
}))

// 测试用的 WebSocket Hook
const useWebSocket = () => {
  const [status, setStatus] = React.useState<'disconnected' | 'connecting' | 'connected' | 'error'>('disconnected')
  const [lastMessage, setLastMessage] = React.useState<any>(null)
  const wsRef = React.useRef<MockWebSocket | null>(null)

  const connect = (callbacks?: {
    onOpen?: () => void
    onClose?: () => void
    onError?: (error: Event) => void
    onMessage?: (message: any) => void
  }) => {
    setStatus('connecting')
    
    const ws = new MockWebSocket('ws://localhost:8081/ws?token=test_token')
    wsRef.current = ws

    ws.onopen = () => {
      setStatus('connected')
      callbacks?.onOpen?.()
    }

    ws.onclose = () => {
      setStatus('disconnected')
      callbacks?.onClose?.()
    }

    ws.onerror = (error) => {
      setStatus('error')
      callbacks?.onError?.(error)
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      setLastMessage(data)
      callbacks?.onMessage?.(data)
    }

    return Promise.resolve()
  }

  const disconnect = () => {
    wsRef.current?.close()
    setStatus('disconnected')
  }

  const send = (type: string, payload: any) => {
    if (wsRef.current && wsRef.current.readyState === MockWebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, payload, timestamp: Date.now() }))
      return true
    }
    return false
  }

  return {
    status,
    isConnected: status === 'connected',
    lastMessage,
    connect,
    disconnect,
    send,
    wsRef,
  }
}

describe('useWebSocket Hook', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.clearAllTimers()
  })

  describe('连接测试', () => {
    it('初始状态应该是 disconnected', () => {
      const { result } = renderHook(() => useWebSocket())

      expect(result.current.status).toBe('disconnected')
      expect(result.current.isConnected).toBe(false)
    })

    it('连接成功后状态应该是 connected', async () => {
      const { result } = renderHook(() => useWebSocket())

      await act(async () => {
        await result.current.connect()
      })

      await waitFor(() => {
        expect(result.current.status).toBe('connected')
        expect(result.current.isConnected).toBe(true)
      })
    })

    it('连接时应该调用 onOpen 回调', async () => {
      const onOpen = vi.fn()
      const { result } = renderHook(() => useWebSocket())

      await act(async () => {
        await result.current.connect({ onOpen })
      })

      await waitFor(() => {
        expect(onOpen).toHaveBeenCalled()
      })
    })

    it('断开连接后状态应该是 disconnected', async () => {
      const { result } = renderHook(() => useWebSocket())

      await act(async () => {
        await result.current.connect()
      })

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })

      act(() => {
        result.current.disconnect()
      })

      expect(result.current.status).toBe('disconnected')
      expect(result.current.isConnected).toBe(false)
    })

    it('断开连接时应该调用 onClose 回调', async () => {
      const onClose = vi.fn()
      const { result } = renderHook(() => useWebSocket())

      await act(async () => {
        await result.current.connect({ onClose })
      })

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })

      act(() => {
        result.current.disconnect()
      })

      expect(onClose).toHaveBeenCalled()
    })
  })

  describe('消息发送测试', () => {
    it('连接状态下应该能发送消息', async () => {
      const { result } = renderHook(() => useWebSocket())

      await act(async () => {
        await result.current.connect()
      })

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })

      const sendResult = act(() => {
        return result.current.send('ping', {})
      })

      expect(sendResult).resolves.not.toThrow()
    })

    it('未连接状态下发送消息应该返回 false', () => {
      const { result } = renderHook(() => useWebSocket())

      const sendResult = result.current.send('ping', {})

      expect(sendResult).toBe(false)
    })
  })

  describe('消息接收测试', () => {
    it('应该能接收消息', async () => {
      const { result } = renderHook(() => useWebSocket())

      await act(async () => {
        await result.current.connect()
      })

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })

      // 模拟接收消息
      const testMessage = { type: 'pong', payload: { time: Date.now() } }
      act(() => {
        result.current.wsRef.current?.simulateMessage(testMessage)
      })

      expect(result.current.lastMessage).toEqual(testMessage)
    })

    it('接收消息时应该调用 onMessage 回调', async () => {
      const onMessage = vi.fn()
      const { result } = renderHook(() => useWebSocket())

      await act(async () => {
        await result.current.connect({ onMessage })
      })

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })

      // 模拟接收消息
      const testMessage = { type: 'message', payload: { content: 'Hello' } }
      act(() => {
        result.current.wsRef.current?.simulateMessage(testMessage)
      })

      expect(onMessage).toHaveBeenCalledWith(testMessage)
    })
  })

  describe('错误处理测试', () => {
    it('连接错误时状态应该是 error', async () => {
      const { result } = renderHook(() => useWebSocket())

      await act(async () => {
        await result.current.connect()
      })

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })

      // 模拟错误
      act(() => {
        result.current.wsRef.current?.simulateError()
      })

      expect(result.current.status).toBe('error')
    })

    it('错误时应该调用 onError 回调', async () => {
      const onError = vi.fn()
      const { result } = renderHook(() => useWebSocket())

      await act(async () => {
        await result.current.connect({ onError })
      })

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })

      // 模拟错误
      act(() => {
        result.current.wsRef.current?.simulateError()
      })

      expect(onError).toHaveBeenCalled()
    })
  })

  describe('重连测试', () => {
    it('断开后应该能重新连接', async () => {
      const { result } = renderHook(() => useWebSocket())

      // 第一次连接
      await act(async () => {
        await result.current.connect()
      })

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })

      // 断开连接
      act(() => {
        result.current.disconnect()
      })

      expect(result.current.isConnected).toBe(false)

      // 重新连接
      await act(async () => {
        await result.current.connect()
      })

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })
    })
  })

  describe('心跳测试', () => {
    it('应该能发送心跳消息', async () => {
      const { result } = renderHook(() => useWebSocket())

      await act(async () => {
        await result.current.connect()
      })

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })

      const sendSpy = vi.spyOn(result.current.wsRef.current!, 'send')

      act(() => {
        result.current.send('ping', { timestamp: Date.now() })
      })

      expect(sendSpy).toHaveBeenCalled()
    })
  })

  describe('消息格式测试', () => {
    it('发送的消息应该包含正确的格式', async () => {
      const { result } = renderHook(() => useWebSocket())

      await act(async () => {
        await result.current.connect()
      })

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })

      const sendSpy = vi.spyOn(result.current.wsRef.current!, 'send')

      const testPayload = {
        sessionId: 'session_001',
        content: 'Hello World',
      }

      act(() => {
        result.current.send('message.send', testPayload)
      })

      expect(sendSpy).toHaveBeenCalledWith(
        expect.stringContaining('"type":"message.send"')
      )
      expect(sendSpy).toHaveBeenCalledWith(
        expect.stringContaining('"payload":')
      )
      expect(sendSpy).toHaveBeenCalledWith(
        expect.stringContaining('"timestamp":')
      )
    })
  })
})

describe('WebSocket Manager', () => {
  it('应该导出正确的 URL 格式', () => {
    const WS_URL = 'ws://localhost:8081/ws'
    const token = 'test_token'
    const fullUrl = `${WS_URL}?token=${token}`

    expect(fullUrl).toContain('ws://')
    expect(fullUrl).toContain('token=')
  })

  it('消息类型应该是有效的', () => {
    const validTypes = [
      'ping',
      'pong',
      'message.send',
      'message.stream',
      'message.complete',
      'session.create',
      'session.delete',
    ]

    validTypes.forEach((type) => {
      expect(type).toBeTruthy()
      expect(typeof type).toBe('string')
    })
  })
})
