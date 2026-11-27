import { Bot, MessageSquare, Plus, PanelLeftClose, Sun, Moon, Sparkles, ClipboardList } from 'lucide-react'
import type { ConversationSummary } from '../../features/chat/types/chat'
import { useTheme } from '../../context/useTheme'

interface SidebarProps {
  conversations: ConversationSummary[]
  activeThreadId: string | null
  onNewConversation: () => void
  onSelectConversation: (threadId: string) => void
  onClose: () => void
}

export function Sidebar({ conversations, activeThreadId, onNewConversation, onSelectConversation, onClose }: SidebarProps) {
  const { theme, toggleTheme } = useTheme()
  return (
    <aside className="flex h-full w-[286px] shrink-0 flex-col border-r border-slate-200/80 bg-white/90 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-950">
      <div className="flex h-[76px] items-center justify-between px-5">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-sky-400 to-blue-700 text-white shadow-lg shadow-blue-500/25"><Bot size={21}/></div>
          <div><span className="block text-[15px] font-bold tracking-tight text-slate-900 dark:text-white">TaskFlow AI</span><span className="text-[10px] font-medium uppercase tracking-[.16em] text-slate-400">Personal workspace</span></div>
        </div>
        <button onClick={onClose} aria-label="Close sidebar" className="rounded-lg p-2 text-slate-400 transition hover:bg-slate-100 dark:hover:bg-slate-800"><PanelLeftClose size={17}/></button>
      </div>
      <div className="px-4 pt-3">
        <button onClick={onNewConversation} className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-sky-500 to-blue-700 px-4 py-3 text-sm font-semibold text-white shadow-md shadow-blue-500/20 transition hover:-translate-y-0.5 hover:shadow-lg"><Plus size={17}/> New conversation</button>
      </div>
      <div className="mx-4 mt-8 flex items-center gap-2 px-2 text-[10px] font-bold uppercase tracking-[.17em] text-slate-400"><MessageSquare size={13}/> Recent conversations</div>
      <nav className="mt-3 flex-1 space-y-1 overflow-y-auto px-3 pb-4">
        {conversations.length === 0 ? <p className="px-3 py-5 text-sm leading-6 text-slate-400">Your conversations will appear here.</p> : conversations.map((conversation) => (
          <button key={conversation.threadId} onClick={() => onSelectConversation(conversation.threadId)}
            className={`flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-sm transition ${activeThreadId === conversation.threadId ? 'bg-blue-50 font-semibold text-blue-700 dark:bg-blue-950/60 dark:text-blue-300' : 'text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-900'}`}>
            <MessageSquare size={16} className="shrink-0 opacity-70"/><span className="truncate">{conversation.title}</span>
          </button>
        ))}
      </nav>
      <div className="mx-4 mb-3 rounded-2xl bg-gradient-to-br from-sky-50 to-blue-100/80 p-3 dark:from-slate-900 dark:to-blue-950/50">
        <div className="flex items-center gap-2 text-xs font-semibold text-blue-800 dark:text-blue-200"><Sparkles size={14}/> Your AI workspace</div>
        <p className="mt-1.5 text-[11px] leading-5 text-slate-500 dark:text-slate-400">Plan your day, manage tasks and stay focused.</p>
      </div>
      <div className="flex items-center justify-between border-t border-slate-100 px-5 py-4 dark:border-slate-800">
        <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400"><ClipboardList size={15}/> Personal assistant</div>
        <button onClick={toggleTheme} aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`} title={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`} className="rounded-xl border border-slate-200 p-2 text-slate-500 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">{theme === 'light' ? <Moon size={16}/> : <Sun size={16}/>}</button>
      </div>
    </aside>
  )
}
