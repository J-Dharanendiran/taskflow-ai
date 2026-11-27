export type ChatStatus =
  | 'completed'
  | 'clarification_required'
  | 'approval_required'

export interface PendingApproval {
  approval_id: string
  deletion_request_id: string
  task_id: string
  message: string
}

export interface ChatRequest {
  thread_id: string | null
  message: string
}

export interface ChatResponse {
  thread_id: string
  message_id: string
  status: ChatStatus
  assistant_message: string
  pending_approval: PendingApproval | null
}

export interface ApprovalRequest {
  approval_id: string
  decision: 'approve' | 'reject'
}

export interface ApprovalResponse {
  thread_id: string
  approval_id: string
  status: 'completed'
  assistant_message: string
}

export interface HistoryMessage {
  message_id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface HistoryResponse {
  thread_id: string
  messages: HistoryMessage[]
  next_cursor: string | null
  has_more: boolean
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt: string
  pendingApproval?: PendingApproval
  approvalState?: 'pending' | 'approved' | 'rejected'
}

export interface ConversationSummary {
  threadId: string
  title: string
  updatedAt: string
}
