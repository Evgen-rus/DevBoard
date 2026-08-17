export type Status = 'inbox' | 'next' | 'in_progress' | 'done'
export type Priority = 'low' | 'medium' | 'high'
export type AttachmentKind = 'image' | 'audio' | 'file'

export type Attachment = {
  id: string
  filename: string
  original_filename?: string
  kind: AttachmentKind
  content_type: string
  size: number
  storage_path: string
}

export type Task = {
  id: string
  number: number
  project: string
  title: string
  description: string
  status: Status
  priority: Priority
  created_at: string
  updated_at: string
  transcript: string
  attachments: Attachment[]
  github_url: string
  comments_count: number
  transcription_error?: string | null
}

export type Comment = {
  id?: number
  author: string
  body: string
  created_at: string
}

export const STATUSES: { id: Status; title: string; hint: string }[] = [
  { id: 'inbox', title: 'Inbox', hint: 'Ещё не разобрано' },
  { id: 'next', title: 'Next', hint: 'Следующая к реализации' },
  { id: 'in_progress', title: 'In Progress', hint: 'Сейчас в работе' },
  { id: 'done', title: 'Done', hint: 'Готово' },
]

export const PRIORITIES: { id: Priority; title: string }[] = [
  { id: 'low', title: 'Low' },
  { id: 'medium', title: 'Medium' },
  { id: 'high', title: 'High' },
]
