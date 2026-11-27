
import { Bot, User } from 'lucide-react'
import type { ChatMessage } from '../types/chat'
import { ApprovalCard } from './ApprovalCard'
import { TaskTable } from './TaskTable'

interface MessageItemProps {
  message: ChatMessage
  onApproval: (
    approval: NonNullable<ChatMessage['pendingApproval']>,
    decision: 'approve' | 'reject',
  ) => void
  approvalBusy: boolean
}

export function MessageItem({
  message,
  onApproval,
  approvalBusy,
}: MessageItemProps) {
  const isUser = message.role === 'user'

  const hasTaskTable =
    !isUser &&
    /\bID:\s*[0-9a-f-]{12,}/i.test(message.content) &&
    /Priority:/i.test(message.content) &&
    /Status:/i.test(message.content)

  return (
    <article className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl ${
          isUser
            ? 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200'
            : 'bg-gradient-to-br from-sky-400 to-blue-600 text-white shadow-md shadow-blue-500/20'
        }`}
      >
        {isUser ? <User size={17} /> : <Bot size={18} />}
      </div>

      <div
        className={`min-w-0 ${
          hasTaskTable ? 'w-full max-w-[95%]' : 'max-w-[85%]'
        } ${isUser ? 'text-right' : ''}`}
      >
        <div className="mb-1.5 text-xs font-semibold text-slate-400">
          {isUser ? 'You' : 'TaskFlow AI'}
        </div>

        {hasTaskTable ? (
          <TaskTable content={message.content} />
        ) : (
          <div
            className={`inline-block whitespace-pre-wrap break-words rounded-2xl px-4 py-3 text-left text-sm leading-7 ${
              isUser
                ? 'rounded-tr-md bg-gradient-to-br from-blue-600 to-indigo-600 text-white shadow-md shadow-blue-600/10'
                : 'rounded-tl-md border border-slate-200 bg-white text-slate-800 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100'
            }`}
          >
            {message.content}
          </div>
        )}

        {message.pendingApproval && (
          <ApprovalCard
            approval={message.pendingApproval}
            state={message.approvalState}
            disabled={
              approvalBusy || message.approvalState !== 'pending'
            }
            onDecision={(decision) =>
              onApproval(message.pendingApproval!, decision)
            }
          />
        )}
      </div>
    </article>
  )
}
