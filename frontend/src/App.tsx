import { useEffect, useState } from 'react'
import { Menu, Sparkles, Bot, CalendarCheck2, ListTodo, WandSparkles, Sun, Moon } from 'lucide-react'
import { Sidebar } from './components/layout/Sidebar'
import { Composer } from './features/chat/components/Composer'
import { MessageItem } from './features/chat/components/MessageItem'
import { useChat } from './features/chat/hooks/useChat'
import { useTheme } from './context/useTheme'
import { loadConversations, saveConversations, upsertConversation } from './features/conversations/services/conversationStorage'
import type { ConversationSummary, PendingApproval } from './features/chat/types/chat'

function App() {
  const chat = useChat()
  const { toggleTheme } = useTheme()
  const [conversations, setConversations] = useState<ConversationSummary[]>(() => loadConversations())
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [approvalBusy, setApprovalBusy] = useState(false)

  useEffect(() => { saveConversations(conversations) }, [conversations])

  async function handleSend(message: string) {
    const result = await chat.sendMessage(message)
    if (!result) return
    const conversation: ConversationSummary = { threadId: result.threadId, title: result.title, updatedAt: new Date().toISOString() }
    setConversations((current) => upsertConversation(current, conversation))
  }

  async function handleApproval(approval: PendingApproval, decision: 'approve' | 'reject') {
    setApprovalBusy(true)
    try { await chat.submitApproval(approval, decision) } finally { setApprovalBusy(false) }
  }

  function handleNewConversation() { chat.reset() }
  async function handleSelectConversation(threadId: string) { await chat.loadConversation(threadId) }

  const activeConversation = conversations.find((item) => item.threadId === chat.threadId)
  const suggestions = [
    { icon: ListTodo, title: 'View my tasks', prompt: 'Show me all my tasks.', tint: 'bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-300' },
    { icon: CalendarCheck2, title: 'Plan my day', prompt: 'Help me organize my workload for today.', tint: 'bg-cyan-50 text-cyan-700 dark:bg-cyan-950 dark:text-cyan-300' },
    { icon: WandSparkles, title: 'Create a task', prompt: 'Create a task to finish my assignment.', tint: 'bg-violet-50 text-violet-600 dark:bg-violet-950 dark:text-violet-300' },
    { icon: Sparkles, title: 'Set priorities', prompt: 'Help me prioritize my pending tasks.', tint: 'bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300' },
  ]

  return (
    <div className="flex h-screen min-h-[560px] overflow-hidden bg-[#f5f9ff] text-slate-900 transition-colors dark:bg-[#080f1d] dark:text-slate-100">
      {sidebarOpen && <div className="fixed inset-0 z-30 md:static md:z-auto">
        <button className="absolute inset-0 bg-slate-950/40 backdrop-blur-sm md:hidden" aria-label="Close sidebar overlay" onClick={() => setSidebarOpen(false)}/>
        <div className="relative z-10 h-full"><Sidebar conversations={conversations} activeThreadId={chat.threadId} onNewConversation={handleNewConversation} onSelectConversation={handleSelectConversation} onClose={() => setSidebarOpen(false)}/></div>
      </div>}
      <main className="relative flex min-w-0 flex-1 flex-col">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-gradient-to-br from-sky-100/80 via-blue-50/40 to-transparent dark:from-blue-950/40 dark:via-slate-900/20"/>
        <header className="relative flex h-[76px] shrink-0 items-center justify-between border-b border-slate-200/70 bg-white/70 px-4 backdrop-blur-xl sm:px-7 dark:border-slate-800 dark:bg-slate-950/60">
          <div className="flex min-w-0 items-center gap-3">
            <button onClick={() => setSidebarOpen((open) => !open)} aria-label="Toggle sidebar" className="rounded-xl p-2 text-slate-500 transition hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"><Menu size={19}/></button>
            <div className="min-w-0"><h1 className="truncate text-sm font-bold text-slate-800 dark:text-slate-100">{activeConversation?.title ?? 'Your workspace'}</h1><p className="text-xs text-slate-400">Your AI-powered personal task manager</p></div>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden items-center gap-2 rounded-full border border-blue-100 bg-white/80 px-3 py-1.5 text-xs font-semibold text-blue-700 sm:flex dark:border-blue-900 dark:bg-slate-900 dark:text-blue-300"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500"/> AI assistant</span>
            <button onClick={toggleTheme} aria-label="Toggle color theme" className="rounded-xl border border-slate-200 bg-white/80 p-2 text-slate-500 hover:bg-white dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"><Sun size={16} className="hidden dark:block"/><Moon size={16} className="dark:hidden"/></button>
          </div>
        </header>
        <section className="relative flex min-h-0 flex-1 flex-col">
          <div className="flex-1 overflow-y-auto px-4 py-7 sm:px-8 sm:py-9">
            <div className="mx-auto max-w-5xl space-y-7">
              {chat.hasMore && chat.threadId && <div className="text-center"><button onClick={chat.loadOlderMessages} disabled={chat.isLoadingOlder} className="rounded-full border border-slate-200 bg-white/80 px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-white disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">{chat.isLoadingOlder ? 'Loading...' : 'Load older messages'}</button></div>}
              {chat.isLoadingHistory ? <div className="py-20 text-center text-sm text-slate-400">Loading conversation...</div> : chat.messages.length === 0 ? (
                <div className="flex min-h-[58vh] flex-col items-center justify-center py-8 text-center">
                  <div className="relative mb-6">
                    <div className="absolute -inset-5 rounded-[2rem] bg-gradient-to-br from-cyan-200/70 to-blue-300/60 blur-2xl dark:from-blue-700/30 dark:to-cyan-600/20"/>
                    <div className="relative flex h-16 w-16 items-center justify-center rounded-[1.35rem] bg-gradient-to-br from-sky-400 via-blue-600 to-indigo-700 text-white shadow-xl shadow-blue-500/25"><Bot size={30}/></div>
                  </div>
                  <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-blue-100 bg-white/70 px-3 py-1 text-[11px] font-bold uppercase tracking-[.16em] text-blue-700 dark:border-blue-900 dark:bg-slate-900/70 dark:text-blue-300"><Sparkles size={13}/> Your personal AI assistant</div>
                  <h2 className="max-w-2xl text-4xl font-semibold leading-[1.12] tracking-[-.045em] text-slate-950 sm:text-5xl dark:text-white">Everything you need to <span className="bg-gradient-to-r from-sky-500 via-blue-600 to-indigo-600 bg-clip-text text-transparent">stay on track.</span></h2>
                  <p className="mt-4 max-w-lg text-sm leading-7 text-slate-500 dark:text-slate-400">Create tasks, set priorities, manage your workload and make progress — all through a simple conversation.</p>
                  <div className="mt-9 grid w-full max-w-2xl gap-3 sm:grid-cols-2">
                    {suggestions.map(({ icon: Icon, title, prompt, tint }) => <button key={title} onClick={() => handleSend(prompt)} className="group flex items-center gap-3 rounded-2xl border border-slate-200/80 bg-white/85 p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-lg hover:shadow-blue-900/5 dark:border-slate-800 dark:bg-slate-900/80 dark:hover:border-blue-800">
                      <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${tint}`}><Icon size={19}/></span>
                      <span className="flex-1"><span className="block text-sm font-semibold text-slate-800 dark:text-slate-100">{title}</span><span className="mt-0.5 block text-xs text-slate-400">{prompt}</span></span>
                      <span className="text-lg text-slate-300 transition group-hover:translate-x-1 group-hover:text-blue-500">›</span>
                    </button>)}
                  </div>
                </div>
              ) : chat.messages.map((message) => <MessageItem key={message.id} message={message} onApproval={handleApproval} approvalBusy={approvalBusy}/>)}
              {chat.isSending && <div className="flex items-center gap-3 text-sm text-slate-400"><div className="flex h-9 w-9 items-center justify-center rounded-2xl bg-gradient-to-br from-sky-400 to-blue-600 text-white"><Bot size={18}/></div><span className="animate-pulse">TaskFlow AI is thinking...</span></div>}
              {chat.error && <div role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">{chat.error}</div>}
            </div>
          </div>
          <footer className="shrink-0 border-t border-slate-200/70 bg-white/75 px-4 pb-4 pt-4 backdrop-blur-xl sm:px-8 dark:border-slate-800 dark:bg-slate-950/70">
            <Composer disabled={chat.isSending || chat.isLoadingHistory} onSend={handleSend}/>
            <p className="mx-auto mt-3 max-w-4xl text-center text-[10px] text-slate-400">TaskFlow AI can make mistakes. Review important actions before approving them.</p>
          </footer>
        </section>
      </main>
    </div>
  )
}

export default App
