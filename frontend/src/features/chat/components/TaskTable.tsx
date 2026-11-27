
import {
  CalendarDays,
  CheckCircle2,
  Circle,
  Clock3,
  Flag,
  ListTodo,
} from 'lucide-react'

interface TaskRow {
  title: string
  id: string
  priority: string
  status: string
  dueDate: string
}

const EM_DASH = '—'

function cleanMarkdown(value: string): string {
  return value.replace(/\*\*/g, '').trim()
}

function getField(
  block: string,
  field: string,
  fallback = EM_DASH,
): string {
  const match = block.match(
    new RegExp(`^\\s*[*-]?\\s*${field}:\\s*(.*?)\\s*$`, 'im'),
  )

  return match?.[1] ? cleanMarkdown(match[1]) : fallback
}

function parseTasks(content: string): TaskRow[] {
  const rows: TaskRow[] = []

  // Split numbered task entries, ignoring introductory text.
  const blocks = content.split(/(?=^\s*\d+[.)]\s+)/m)

  for (const block of blocks) {
    const id = block.match(/\bID:\s*([0-9a-f-]{12,})/i)?.[1]

    if (!id) continue

    // Format 1: Title: **Finish assignment**
    const explicitTitle = block.match(
      /Title:\s*\*{0,2}([^\r\n*]+)\*{0,2}/i,
    )?.[1]

    // Format 2: 1. **Finish assignment** (ID: ...)
    const numberedTitle = block.match(
      /^\s*\d+[.)]\s+(.+?)(?=\s*\(\s*ID:|\r?$)/im,
    )?.[1]

    const title = cleanMarkdown(explicitTitle ?? numberedTitle ?? '')

    if (!title) continue

    const priority = getField(block, 'Priority')
    const status = getField(block, 'Status')
    const rawDueDate = getField(block, 'Due Date')

    rows.push({
      title,
      id,
      priority,
      status,
      dueDate:
        rawDueDate.toLowerCase() === 'none'
          ? 'No due date'
          : rawDueDate,
    })
  }

  return rows
}

function badgeClass(value: string, kind: 'priority' | 'status') {
  const normalized = value.toLowerCase()

  if (kind === 'status') {
    if (normalized.includes('complete')) {
      return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300'
    }

    if (normalized.includes('progress')) {
      return 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300'
    }

    return 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300'
  }

  if (normalized.includes('high')) {
    return 'bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300'
  }

  if (normalized.includes('low')) {
    return 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
  }

  return 'bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300'
}

export function TaskTable({ content }: { content: string }) {
  const tasks = parseTasks(content)

  if (!tasks.length) {
    return (
      <div className="whitespace-pre-wrap break-words rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm leading-7 text-slate-800 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100">
        {content}
      </div>
    )
  }

  return (
    <div className="mt-3 w-full overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3 dark:border-slate-800">
        <div className="flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-100">
          <ListTodo size={17} className="text-blue-600" />
          Your tasks
        </div>

        <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700 dark:bg-blue-950 dark:text-blue-300">
          {tasks.length} tasks
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[680px] text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-800/70 dark:text-slate-400">
            <tr>
              <th className="px-4 py-3 font-semibold">Task</th>
              <th className="px-4 py-3 font-semibold">Priority</th>
              <th className="px-4 py-3 font-semibold">Status</th>
              <th className="px-4 py-3 font-semibold">Due date</th>
            </tr>
          </thead>

          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {tasks.map((task) => (
              <tr
                key={task.id}
                className="transition hover:bg-blue-50/50 dark:hover:bg-slate-800/60"
              >
                <td className="px-4 py-3.5">
                  <div className="flex items-center gap-3">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-300">
                      <Circle size={15} />
                    </span>

                    <div className="min-w-0">
                      <p className="font-medium text-slate-800 dark:text-slate-100">
                        {task.title}
                      </p>
                      <p className="mt-0.5 max-w-[230px] truncate text-[11px] text-slate-400">
                        ID: {task.id}
                      </p>
                    </div>
                  </div>
                </td>

                <td className="px-4 py-3.5">
                  <span
                    className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${badgeClass(task.priority, 'priority')}`}
                  >
                    <Flag size={12} />
                    {task.priority}
                  </span>
                </td>

                <td className="px-4 py-3.5">
                  <span
                    className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${badgeClass(task.status, 'status')}`}
                  >
                    {task.status.toLowerCase().includes('complete') ? (
                      <CheckCircle2 size={12} />
                    ) : (
                      <Clock3 size={12} />
                    )}
                    {task.status}
                  </span>
                </td>

                <td className="px-4 py-3.5 text-slate-600 dark:text-slate-300">
                  <span className="inline-flex items-center gap-2">
                    <CalendarDays size={14} className="text-slate-400" />
                    {task.dueDate}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
