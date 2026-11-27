import type { ConversationSummary } from '../../chat/types/chat'

const STORAGE_KEY = 'taskflow-ai-conversations'

export function loadConversations(): ConversationSummary[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []

    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed as ConversationSummary[] : []
  } catch {
    return []
  }
}

export function saveConversations(
  conversations: ConversationSummary[],
): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations))
}

export function upsertConversation(
  conversations: ConversationSummary[],
  conversation: ConversationSummary,
): ConversationSummary[] {
  const remaining = conversations.filter(
    (item) => item.threadId !== conversation.threadId,
  )

  return [conversation, ...remaining].sort(
    (a, b) =>
      new Date(b.updatedAt).getTime() -
      new Date(a.updatedAt).getTime(),
  )
}
