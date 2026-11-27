import { Check, X, ShieldCheck, Trash2 } from 'lucide-react'
import type { PendingApproval } from '../types/chat'

interface ApprovalCardProps {
  approval: PendingApproval
  state?: 'pending' | 'approved' | 'rejected'
  disabled?: boolean
  onDecision: (decision: 'approve' | 'reject') => void
}

export function ApprovalCard({ approval, state, disabled, onDecision }: ApprovalCardProps) {
  const resolved = state === 'approved' || state === 'rejected'
  return (
    <section className="mt-4 max-w-xl overflow-hidden rounded-2xl border border-amber-200 bg-amber-50/90 shadow-sm dark:border-amber-900 dark:bg-amber-950/30">
      <div className="flex items-center gap-2 border-b border-amber-200/70 px-4 py-3 text-sm font-semibold text-amber-900 dark:border-amber-900 dark:text-amber-200">
        <ShieldCheck size={18}/> Deletion approval required
      </div>
      <div className="p-4">
        <p className="text-sm leading-6 text-slate-700 dark:text-slate-200">{approval.message}</p>
        <p className="mt-2 break-all text-xs text-slate-500 dark:text-slate-400">Task ID: {approval.task_id}</p>
        {resolved ? (
          <p className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
            {state === 'approved' ? <Check size={16} className="text-emerald-600"/> : <X size={16} className="text-rose-600"/>}
            {state === 'approved' ? 'Approved' : 'Rejected'}
          </p>
        ) : (
          <div className="mt-4 flex flex-wrap gap-2">
            <button disabled={disabled} onClick={() => onDecision('approve')} className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-50"><Check size={16}/> Approve deletion</button>
            <button disabled={disabled} onClick={() => onDecision('reject')} className="inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"><X size={16}/> Keep task</button>
          </div>
        )}
      </div>
      <div className="flex items-center gap-2 bg-amber-100/60 px-4 py-2 text-[11px] text-amber-800 dark:bg-amber-900/20 dark:text-amber-300"><Trash2 size={12}/> This action requires your confirmation.</div>
    </section>
  )
}
