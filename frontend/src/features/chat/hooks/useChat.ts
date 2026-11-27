import { useCallback, useState } from 'react'
import { chatApi } from '../services/chatApi'
import type {
  ChatMessage,
  HistoryMessage,
  PendingApproval,
} from '../types/chat'

function toChatMessage(message: HistoryMessage): ChatMessage {
  return {
    id: message.message_id,
    role: message.role,
    content: message.content,
    createdAt: message.created_at,
  }
}

export function useChat() {
  const [threadId, setThreadId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isSending, setIsSending] = useState(false)
  const [isLoadingHistory, setIsLoadingHistory] = useState(false)
  const [isLoadingOlder, setIsLoadingOlder] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)

  const reset = useCallback(() => {
    setThreadId(null)
    setMessages([])
    setError(null)
    setNextCursor(null)
    setHasMore(false)
  }, [])

  const loadConversation = useCallback(async (id: string) => {
    setIsLoadingHistory(true)
    setError(null)

    try {
      const result = await chatApi.getHistory(id)

      setThreadId(result.thread_id)
      setMessages(result.messages.map(toChatMessage))
      setNextCursor(result.next_cursor)
      setHasMore(result.has_more)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Unable to load conversation.',
      )
    } finally {
      setIsLoadingHistory(false)
    }
  }, [])

  const loadOlderMessages = useCallback(async () => {
    if (!threadId || !nextCursor || isLoadingOlder) return

    setIsLoadingOlder(true)
    setError(null)

    try {
      const result = await chatApi.getHistory(threadId, nextCursor)

      setMessages((current) => {
        const existingIds = new Set(current.map((item) => item.id))
        const older = result.messages
          .map(toChatMessage)
          .filter((item) => !existingIds.has(item.id))

        return [...older, ...current]
      })

      setNextCursor(result.next_cursor)
      setHasMore(result.has_more)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Unable to load older messages.',
      )
    } finally {
      setIsLoadingOlder(false)
    }
  }, [threadId, nextCursor, isLoadingOlder])

  const sendMessage = useCallback(async (content: string) => {
    const trimmed = content.trim()
    if (!trimmed || isSending) return null

    setError(null)
    setIsSending(true)

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: trimmed,
      createdAt: new Date().toISOString(),
    }

    setMessages((current) => [...current, userMessage])

    try {
      const result = await chatApi.sendMessage({
        thread_id: threadId,
        message: trimmed,
      })

      setThreadId(result.thread_id)

      const assistantMessage: ChatMessage = {
        id: result.message_id,
        role: 'assistant',
        content: result.assistant_message,
        createdAt: new Date().toISOString(),
        pendingApproval: result.pending_approval ?? undefined,
        approvalState: result.pending_approval ? 'pending' : undefined,
      }

      setMessages((current) => [...current, assistantMessage])

      return {
        threadId: result.thread_id,
        status: result.status,
        pendingApproval: result.pending_approval,
        title: trimmed.slice(0, 48),
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Unable to send message.',
      )
      setMessages((current) =>
        current.filter((message) => message.id !== userMessage.id),
      )
      return null
    } finally {
      setIsSending(false)
    }
  }, [threadId, isSending])

  const submitApproval = useCallback(async (
    approval: PendingApproval,
    decision: 'approve' | 'reject',
  ) => {
    if (!threadId) return false

    setError(null)

    try {
      const result = await chatApi.submitApproval(threadId, {
        approval_id: approval.approval_id,
        decision,
      })

      setMessages((current) => [
        ...current.map((message) =>
          message.pendingApproval?.approval_id === approval.approval_id
            ? { ...message, approvalState: decision === 'approve' ? 'approved' as const : 'rejected' as const }
            : message,
        ),
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: result.assistant_message,
          createdAt: new Date().toISOString(),
        },
      ])

      return true
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Unable to submit approval.',
      )
      return false
    }
  }, [threadId])

  return {
    threadId,
    messages,
    isSending,
    isLoadingHistory,
    isLoadingOlder,
    error,
    hasMore,
    reset,
    loadConversation,
    loadOlderMessages,
    sendMessage,
    submitApproval,
  }
}
