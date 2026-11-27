import type {
  ApprovalRequest,
  ApprovalResponse,
  ChatRequest,
  ChatResponse,
  HistoryResponse,
} from '../types/chat'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })

  if (!response.ok) {
    let message = `Request failed (${response.status})`

    try {
      const body = await response.json()
      message =
        typeof body.detail === 'string'
          ? body.detail
          : JSON.stringify(body.detail ?? body)
    } catch {
      // Keep the HTTP status message when the body is not JSON.
    }

    throw new Error(message)
  }

  return response.json() as Promise<T>
}

export const chatApi = {
  sendMessage(payload: ChatRequest) {
    return request<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },

  submitApproval(threadId: string, payload: ApprovalRequest) {
    return request<ApprovalResponse>(
      `/chat/${encodeURIComponent(threadId)}/approval`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    )
  },

  getHistory(threadId: string, cursor?: string | null) {
    const params = new URLSearchParams({ limit: '50' })

    if (cursor) {
      params.set('cursor', cursor)
    }

    return request<HistoryResponse>(
      `/chat/${encodeURIComponent(threadId)}/history?${params}`,
    )
  },
}
