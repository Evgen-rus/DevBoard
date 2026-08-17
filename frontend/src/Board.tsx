import { useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  addAttachments,
  addComment,
  attachmentUrl,
  createProject,
  createTask,
  listComments,
  listProjects,
  listTasks,
  patchTask,
  transcribe,
} from './api'
import type { Comment, Priority, Status, Task } from './types'
import { PRIORITIES, STATUSES } from './types'

type Props = { onLogout: () => void }

const AGENT_PROMPT = (task: Task) =>
  `Возьми ${task.id}, изучи задачу и текущий проект, составь план и реализуй.`

export default function Board({ onLogout }: Props) {
  const [projects, setProjects] = useState<string[]>([])
  const [project, setProject] = useState('all')
  const [tasks, setTasks] = useState<Task[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [doneOpen, setDoneOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [openedId, setOpenedId] = useState<string | null>(null)

  async function reload(selected = project) {
    const [projectData, taskData] = await Promise.all([listProjects(), listTasks(selected)])
    setProjects(projectData.projects)
    setTasks(taskData.tasks)
  }

  useEffect(() => {
    reload().catch((err: unknown) => setError(err instanceof Error ? err.message : 'Ошибка загрузки'))
  }, [])

  const opened = tasks.find((task) => task.id === openedId) || null
  const grouped = useMemo(() => {
    const map: Record<Status, Task[]> = { inbox: [], next: [], in_progress: [], done: [] }
    for (const task of tasks) map[task.status].push(task)
    return map
  }, [tasks])

  async function changeStatus(id: string, status: Status) {
    const result = await patchTask(id, { status })
    setTasks((current) => current.map((task) => (task.id === id ? result.task : task)))
  }

  async function onCreateProject() {
    const name = window.prompt('Название нового проекта')
    if (!name) return
    try {
      const created = await createProject(name)
      setProjects((current) => (current.includes(created.project) ? current : [...current, created.project]))
      setProject(created.project)
      await reload(created.project)
      setNotice(`Проект ${created.project} создан`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось создать проект')
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <h1>DevBoard</h1>
          <span>задачи для людей и агентов</span>
        </div>
        <div className="top-actions">
          <select
            value={project}
            onChange={(event) => {
              const value = event.target.value
              setProject(value)
              reload(value).catch((err: unknown) => setError(err instanceof Error ? err.message : 'Ошибка'))
            }}
            aria-label="Проект"
          >
            <option value="all">Все проекты</option>
            {projects.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <button className="btn secondary" type="button" onClick={onCreateProject}>
            + Проект
          </button>
          <button className="btn" type="button" onClick={() => setCreating(true)}>
            + New Task
          </button>
          <button className="btn ghost" type="button" onClick={onLogout}>
            Выйти
          </button>
        </div>
      </header>
      {error ? <div className="banner error">{error}</div> : null}
      {notice ? <div className="banner ok">{notice}</div> : null}
      <main className="board">
        {STATUSES.map((column) => {
          const items = grouped[column.id]
          const collapsed = column.id === 'done' && !doneOpen
          return (
            <section
              key={column.id}
              className={`column ${column.id === 'done' ? 'done' : ''} ${collapsed ? 'collapsed' : ''}`}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                const id = event.dataTransfer.getData('text/plain')
                if (id) changeStatus(id, column.id).catch((err: unknown) => setError(err instanceof Error ? err.message : 'Ошибка'))
              }}
            >
              <div className="column-head">
                <h2>
                  {column.title}
                  <small>{column.hint}</small>
                </h2>
                <span className="count">{items.length}</span>
              </div>
              {column.id === 'done' ? (
                <button className="btn ghost" type="button" onClick={() => setDoneOpen((value) => !value)}>
                  {doneOpen ? 'Свернуть Done' : 'Показать Done'}
                </button>
              ) : null}
              {collapsed ? null : items.length === 0 ? (
                <div className="empty">Пусто</div>
              ) : (
                items.map((task) => (
                  <TaskCard key={task.id} task={task} onOpen={() => setOpenedId(task.id)} />
                ))
              )}
            </section>
          )
        })}
      </main>
      {creating ? (
        <NewTask
          projects={projects}
          defaultProject={project === 'all' ? projects[0] || 'NeuroROP' : project}
          onClose={() => setCreating(false)}
          onCreated={async (task) => {
            setCreating(false)
            setNotice(`Создана ${task.id}`)
            setOpenedId(task.id)
            await reload(project)
          }}
        />
      ) : null}
      {opened ? (
        <TaskDetail
          task={opened}
          projects={projects}
          onClose={() => setOpenedId(null)}
          onChange={(task) => setTasks((current) => current.map((item) => (item.id === task.id ? task : item)))}
        />
      ) : null}
    </div>
  )
}

function TaskCard({ task, onOpen }: { task: Task; onOpen: () => void }) {
  const images = task.attachments.filter((item) => item.kind === 'image').length
  const audio = task.attachments.filter((item) => item.kind === 'audio').length
  const files = task.attachments.filter((item) => item.kind === 'file').length
  return (
    <button
      className="task-card"
      type="button"
      draggable
      onDragStart={(event) => event.dataTransfer.setData('text/plain', task.id)}
      onClick={onOpen}
    >
      <div className="task-id mono">{task.id}</div>
      <div className="task-title">{task.title}</div>
      <div className="meta-row">
        <span className="pill project">{task.project}</span>
        <span className={`pill ${task.priority}`}>{task.priority}</span>
      </div>
      <div className="icon-row">
        {audio ? <span>🎤 {audio}</span> : null}
        {images ? <span>📷 {images}</span> : null}
        {files ? <span>📎 {files}</span> : null}
        {task.transcript ? <span>Aa</span> : null}
        {task.status === 'done' ? <span>✓</span> : null}
      </div>
    </button>
  )
}

function NewTask({
  projects,
  defaultProject,
  onClose,
  onCreated,
}: {
  projects: string[]
  defaultProject: string
  onClose: () => void
  onCreated: (task: Task) => Promise<void>
}) {
  const [project, setProject] = useState(defaultProject)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [priority, setPriority] = useState<Priority>('medium')
  const [files, setFiles] = useState<File[]>([])
  const [transcript, setTranscript] = useState('')
  const [recording, setRecording] = useState(false)
  const [recorder, setRecorder] = useState<MediaRecorder | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [transcribing, setTranscribing] = useState(false)

  function addFiles(list: FileList | File[]) {
    setFiles((current) => [...current, ...Array.from(list)])
  }

  async function transcribeFile(file: File) {
    setTranscribing(true)
    setError('')
    try {
      const result = await transcribe(file)
      setTranscript((current) => (current ? `${current}\n${result.text}` : result.text))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось расшифровать аудио')
    } finally {
      setTranscribing(false)
    }
  }

  async function startRecording() {
    setError('')
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : 'audio/webm'
    const media = new MediaRecorder(stream, { mimeType: mime })
    const chunks: BlobPart[] = []
    media.ondataavailable = (event) => {
      if (event.data.size) chunks.push(event.data)
    }
    media.onstop = () => {
      stream.getTracks().forEach((track) => track.stop())
      const blob = new Blob(chunks, { type: media.mimeType || 'audio/webm' })
      const file = new File([blob], `voice-${Date.now()}.webm`, { type: blob.type })
      addFiles([file])
      transcribeFile(file).catch(() => undefined)
    }
    media.start()
    setRecorder(media)
    setRecording(true)
  }

  function stopRecording() {
    recorder?.stop()
    setRecorder(null)
    setRecording(false)
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const result = await createTask({ project, title, description, priority, transcript, files })
      await onCreated(result.task)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось создать задачу')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <form className="panel" onClick={(event) => event.stopPropagation()} onSubmit={onSubmit}>
        <h2>Новая задача</h2>
        <p className="muted">Можно коротко текстом, скриншотами и голосом. Техническое ТЗ не обязательно.</p>
        <div className="field">
          <label>Project</label>
          <select value={project} onChange={(event) => setProject(event.target.value)}>
            {(projects.includes(project) ? projects : [project, ...projects]).map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Title</label>
          <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Можно оставить пустым" />
        </div>
        <div className="field">
          <label>Description</label>
          <textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Пара фраз своими словами" />
        </div>
        <div className="field">
          <label>Attachments / Screenshots</label>
          <div
            className="dropzone"
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault()
              if (event.dataTransfer.files.length) addFiles(event.dataTransfer.files)
            }}
          >
            Перетащите файлы сюда или выберите
            <div className="row-actions">
              <input type="file" multiple onChange={(event) => event.target.files && addFiles(event.target.files)} />
            </div>
          </div>
          <FileList files={files} />
        </div>
        <div className="field">
          <label>Audio / Record voice</label>
          <div className="record-box">
            {recording ? <span className="rec-dot" /> : null}
            {recording ? (
              <button className="btn danger" type="button" onClick={stopRecording}>
                Остановить запись
              </button>
            ) : (
              <button className="btn secondary" type="button" onClick={() => startRecording().catch((err: unknown) => setError(err instanceof Error ? err.message : 'Нет доступа к микрофону'))}>
                Записать голос
              </button>
            )}
            <input
              type="file"
              accept="audio/*,video/webm"
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (!file) return
                addFiles([file])
                transcribeFile(file).catch(() => undefined)
              }}
            />
          </div>
          {transcribing ? <div className="muted">Расшифровываю аудио…</div> : null}
        </div>
        <div className="field">
          <label>Transcript</label>
          <textarea value={transcript} onChange={(event) => setTranscript(event.target.value)} placeholder="Появится после записи или загрузки аудио" />
        </div>
        <div className="field">
          <label>Priority</label>
          <select value={priority} onChange={(event) => setPriority(event.target.value as Priority)}>
            {PRIORITIES.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </select>
        </div>
        {error ? <div className="status-error">{error}</div> : null}
        <div className="row-actions">
          <button className="btn" type="submit" disabled={busy || !(title || description || files.length || transcript)}>
            {busy ? 'Сохраняю…' : 'Create'}
          </button>
          <button className="btn secondary" type="button" onClick={onClose}>
            Отмена
          </button>
        </div>
      </form>
    </div>
  )
}

function TaskDetail({
  task,
  projects,
  onClose,
  onChange,
}: {
  task: Task
  projects: string[]
  onClose: () => void
  onChange: (task: Task) => void
}) {
  const [title, setTitle] = useState(task.title)
  const [description, setDescription] = useState(task.description)
  const [transcript, setTranscript] = useState(task.transcript)
  const [status, setStatus] = useState<Status>(task.status)
  const [priority, setPriority] = useState<Priority>(task.priority)
  const [project, setProject] = useState(task.project)
  const [comments, setComments] = useState<Comment[]>([])
  const [comment, setComment] = useState('')
  const [error, setError] = useState('')
  const [copied, setCopied] = useState('')

  useEffect(() => {
    setTitle(task.title)
    setDescription(task.description)
    setTranscript(task.transcript)
    setStatus(task.status)
    setPriority(task.priority)
    setProject(task.project)
    listComments(task.id)
      .then((result) => setComments(result.comments))
      .catch(() => setComments([]))
  }, [task])

  async function save() {
    try {
      const result = await patchTask(task.id, { title, description, transcript, status, priority, project })
      onChange(result.task)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить')
    }
  }

  async function copyPrompt() {
    await navigator.clipboard.writeText(AGENT_PROMPT(task))
    setCopied('Промпт для агента скопирован')
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="panel" onClick={(event) => event.stopPropagation()}>
        <div className="mono detail-id">{task.id}</div>
        <a className="muted" href={task.github_url} target="_blank" rel="noreferrer">
          GitHub Issue
        </a>
        <div className="row-actions">
          <button className="btn" type="button" onClick={copyPrompt}>
            Скопировать промпт агенту
          </button>
          <button className="btn secondary" type="button" onClick={onClose}>
            Закрыть
          </button>
        </div>
        {copied ? <div className="banner ok">{copied}</div> : null}
        {task.transcription_error ? <div className="status-error">{task.transcription_error}</div> : null}
        <div className="field">
          <label>Title</label>
          <input value={title} onChange={(event) => setTitle(event.target.value)} />
        </div>
        <div className="field">
          <label>Project</label>
          <select value={project} onChange={(event) => setProject(event.target.value)}>
            {projects.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Status</label>
          <select value={status} onChange={(event) => setStatus(event.target.value as Status)}>
            {STATUSES.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Priority</label>
          <select value={priority} onChange={(event) => setPriority(event.target.value as Priority)}>
            {PRIORITIES.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Description</label>
          <textarea value={description} onChange={(event) => setDescription(event.target.value)} />
        </div>
        <div className="field">
          <label>Transcript</label>
          <textarea value={transcript} onChange={(event) => setTranscript(event.target.value)} />
        </div>
        <div className="field attachments">
          <label>Вложения</label>
          {task.attachments.length === 0 ? <div className="muted">Нет файлов</div> : null}
          {task.attachments.map((item) => (
            <div key={item.filename} className="field">
              {item.kind === 'image' ? (
                <img src={attachmentUrl(task.id, item.filename)} alt={item.filename} />
              ) : null}
              {item.kind === 'audio' ? (
                <audio controls src={attachmentUrl(task.id, item.filename)} />
              ) : null}
              <a href={attachmentUrl(task.id, item.filename)} target="_blank" rel="noreferrer">
                {item.filename}
              </a>
            </div>
          ))}
          <input
            type="file"
            multiple
            onChange={async (event) => {
              if (!event.target.files?.length) return
              const result = await addAttachments(task.id, Array.from(event.target.files))
              onChange(result.task)
            }}
          />
        </div>
        {error ? <div className="status-error">{error}</div> : null}
        <div className="row-actions">
          <button className="btn" type="button" onClick={() => save().catch(() => undefined)}>
            Сохранить
          </button>
        </div>
        <h3>Комментарии</h3>
        {comments.map((item) => (
          <div className="comment" key={`${item.created_at}-${item.body}`}>
            <div className="muted">
              {item.author} · {item.created_at.slice(0, 16).replace('T', ' ')}
            </div>
            <div>{item.body}</div>
          </div>
        ))}
        <textarea value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Комментарий в GitHub Issue" />
        <div className="row-actions">
          <button
            className="btn secondary"
            type="button"
            disabled={!comment.trim()}
            onClick={async () => {
              const result = await addComment(task.id, comment.trim())
              setComments((current) => [...current, result.comment])
              setComment('')
            }}
          >
            Добавить комментарий
          </button>
        </div>
      </div>
    </div>
  )
}

function FileList({ files }: { files: File[] }) {
  if (!files.length) return null
  return (
    <div className="preview-grid">
      {files.map((file, index) =>
        file.type.startsWith('image/') ? (
          <img key={`${file.name}-${index}`} src={URL.createObjectURL(file)} alt={file.name} />
        ) : (
          <div className="file-chip" key={`${file.name}-${index}`}>
            {file.name}
          </div>
        ),
      )}
    </div>
  )
}
