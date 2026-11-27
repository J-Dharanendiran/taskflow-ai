import { ArrowUp, LoaderCircle, Paperclip, Sparkles } from 'lucide-react'
import { useState, type FormEvent, type KeyboardEvent } from 'react'

interface ComposerProps { disabled?: boolean; onSend: (message: string) => void }

export function Composer({ disabled, onSend }: ComposerProps) {
  const [value, setValue] = useState('')
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!value.trim() || disabled) return
    onSend(value.trim())
    setValue('')
  }
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      event.currentTarget.form?.requestSubmit()
    }
  }
  return (
    <form onSubmit={submit} className="mx-auto flex max-w-4xl items-end gap-2 rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-lg shadow-slate-200/50 backdrop-blur focus-within:border-blue-300 focus-within:ring-4 focus-within:ring-blue-100/70 dark:border-slate-700 dark:bg-slate-900/95 dark:shadow-black/20 dark:focus-within:ring-blue-950">
      <span className="mb-2 hidden pl-1 text-blue-500 sm:block"><Sparkles size={18}/></span>
      <textarea value={value} onChange={(event) => setValue(event.target.value)} onKeyDown={handleKeyDown}
        disabled={disabled} rows={1} placeholder="Message TaskFlow AI..." aria-label="Message"
        className="max-h-40 min-h-10 flex-1 resize-y bg-transparent px-2 py-2 text-sm text-slate-800 outline-none placeholder:text-slate-400 dark:text-slate-100" />
      <button type="button" aria-label="Attachments (coming soon)" title="Attachments are not available yet" className="mb-1 hidden h-9 w-9 items-center justify-center rounded-xl text-slate-400 sm:flex"><Paperclip size={17}/></button>
      <button type="submit" disabled={disabled || !value.trim()} aria-label="Send message"
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-sky-500 to-blue-700 text-white shadow-md shadow-blue-500/25 transition hover:-translate-y-0.5 hover:shadow-lg disabled:cursor-not-allowed disabled:opacity-40">
        {disabled ? <LoaderCircle size={18} className="animate-spin"/> : <ArrowUp size={19}/>}
      </button>
    </form>
  )
}
