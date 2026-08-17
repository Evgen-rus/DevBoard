import type { Comment, Priority, Status, Task } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: 'include',
    ...init,
  })
  if (response.status === 401) {
    throw new AuthError('Нужна авторизация')
  }
  if (!response.ok) {
    let detail = `Ошибка ${response.status}`
    try {
      const payload = (await response.json()) as { detail?: string }
      if (payload.detail) detail = payload.detail
    } catch {
      // оставляем стандартный текст
    }
    throw new Error(detail)
  }
  if (response.status === 204) {
    return {} as T
  }
  return (await response.json()) as T
}

export class AuthError extends Error {}

export function me() {
  return request<{ ok: boolean }>('/api/me')
}

export function login(password: string) {
  return request<{ ok: boolean }>('/api/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  })
}

export function logout() {
  return request<{ ok: boolean }>('/api/logout', { method: 'POST' })
}

export function listProjects() {
  return request<{ projects: string[] }>('/api/projects')
}

export function createProject(name: string) {
  return request<{ project: string }>('/api/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
}

export function listTasks(project?: string, archived = false) {
  const query = new URLSearchParams()
  if (project && project !== 'all') query.set('project', project)
  if (archived) query.set('archived', 'true')
  const suffix = query.size ? `?${query.toString()}` : ''
  return request<{ tasks: Task[] }>(`/api/tasks${suffix}`)
}

export function getTask(id: string) {
  return request<{ task: Task }>(`/api/tasks/${encodeURIComponent(id)}`)
}

export function getAgentContext(id: string) {
  const query = new URLSearchParams({ public_url: window.location.origin })
  return request<{ agent_prompt: string }>(
    `/api/tasks/${encodeURIComponent(id)}/agent-context?${query.toString()}`,
  )
}

export function createTask(input: {
  project: string
  title: string
  description: string
  priority: Priority
  transcript: string
  files: File[]
}) {
  const body = new FormData()
  body.append('project', input.project)
  body.append('title', input.title)
  body.append('description', input.description)
  body.append('priority', input.priority)
  body.append('transcript', input.transcript)
  for (const file of input.files) {
    body.append('files', file)
  }
  return request<{ task: Task }>('/api/tasks', { method: 'POST', body })
}

export function patchTask(
  id: string,
  patch: Partial<{
    title: string
    description: string
    transcript: string
    status: Status
    priority: Priority
    project: string
  }>,
) {
  return request<{ task: Task }>(`/api/tasks/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
}

export function addAttachments(id: string, files: File[]) {
  const body = new FormData()
  for (const file of files) body.append('files', file)
  return request<{ task: Task }>(`/api/tasks/${encodeURIComponent(id)}/attachments`, {
    method: 'POST',
    body,
  })
}

export function archiveTask(id: string) {
  return request<{ task: Task }>(`/api/tasks/${encodeURIComponent(id)}/archive`, {
    method: 'POST',
  })
}

export function restoreTask(id: string) {
  return request<{ task: Task }>(`/api/tasks/${encodeURIComponent(id)}/restore`, {
    method: 'POST',
  })
}

export function listComments(id: string) {
  return request<{ comments: Comment[] }>(`/api/tasks/${encodeURIComponent(id)}/comments`)
}

export function addComment(id: string, body: string) {
  return request<{ comment: Comment }>(`/api/tasks/${encodeURIComponent(id)}/comments`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ body }),
  })
}

export function transcribe(audio: File) {
  const body = new FormData()
  body.append('audio', audio)
  return request<{ text: string }>('/api/transcribe', { method: 'POST', body })
}

export function attachmentUrl(taskId: string, filename: string) {
  return `/api/tasks/${encodeURIComponent(taskId)}/attachments/${encodeURIComponent(filename)}`
}
