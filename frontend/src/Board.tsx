import { useEffect, useMemo, useState, type ClipboardEvent, type FormEvent } from 'react'
import {
  addAttachments,
  addComment,
  archiveTask,
  attachmentUrl,
  createProject,
  createTask,
  getAgentContext,
  listComments,
  listProjects,
  listTasks,
  patchTask,
  restoreTask,
  transcribe,
} from './api'
import type { Comment, Priority, Status, Task } from './types'
import { PRIORITIES, STATUSES, priorityTitle } from './types'

type Props = { onLogout: () => void }

const LAST_PROJECT_KEY = 'devboard.lastProject'
// Узкий экран — отдельная композиция (список + вкладки), а не сжатый канбан.
const NARROW_QUERY = '(max-width: 900px)'
function readLastProject(): string {
  try {
    return localStorage.getItem(LAST_PROJECT_KEY) || ''
  } catch {
    return ''
  }
}

function writeLastProject(name: string) {
  try {
    localStorage.setItem(LAST_PROJECT_KEY, name)
  } catch {
    // private mode / blocked storage
  }
}

function useNarrow() {
  const [narrow, setNarrow] = useState(() => window.matchMedia(NARROW_QUERY).matches)
  useEffect(() => {
    const media = window.matchMedia(NARROW_QUERY)
    const onChange = () => setNarrow(media.matches)
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [])
  return narrow
}

function composerProject(filter: string, projects: string[], tasks: Task[]): string {
  // Сначала текущий фильтр, затем последний использованный проект, иначе проект ближайшей задачи.
  if (filter !== 'all' && filter) return filter
  const last = readLastProject()
  if (last && (projects.length === 0 || projects.includes(last))) return last
  if (tasks[0]?.project) return tasks[0].project
  return projects[0] || 'NeuroROP'
}

function cardExcerpt(task: Task): string {
  const text = (task.description || '').replace(/\s+/g, ' ').trim()
  if (!text || text === task.title.trim()) return ''
  return text
}

export default function Board({ onLogout }: Props) {
  const narrow = useNarrow()
  const [projects, setProjects] = useState<string[]>([])
  const [project, setProject] = useState('all')
  const [statusFilter, setStatusFilter] = useState<Status>('inbox')
  const [tasks, setTasks] = useState<Task[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [noticeId, setNoticeId] = useState<string | null>(null)
  const [doneOpen, setDoneOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [creatingProject, setCreatingProject] = useState(false)
  const [archiveOpen, setArchiveOpen] = useState(false)
  const [openedId, setOpenedId] = useState<string | null>(null)
  const [dropTarget, setDropTarget] = useState<Status | null>(null)

  async function reload(selected = project, ensuredTask?: Task) {
    const [projectData, taskData] = await Promise.all([listProjects(), listTasks(selected)])
    setProjects(projectData.projects)
    const visibleEnsuredTask = ensuredTask && (selected === 'all' || ensuredTask.project === selected)
    const tasks = visibleEnsuredTask && !taskData.tasks.some((task) => task.id === ensuredTask.id)
      ? [ensuredTask, ...taskData.tasks]
      : taskData.tasks
    setTasks(tasks)
  }

  useEffect(() => {
    reload().catch((err: unknown) => setError(err instanceof Error ? err.message : 'Ошибка загрузки'))
  }, [])

  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(() => {
      setNotice('')
      setNoticeId(null)
    }, 6000)
    return () => window.clearTimeout(timer)
  }, [notice])

  useEffect(() => {
    const overlayOpen = creating || creatingProject || archiveOpen || Boolean(openedId)
    document.body.style.overflow = overlayOpen ? 'hidden' : ''
    function onKey(event: KeyboardEvent) {
      if (event.key !== 'Escape') return
      if (creatingProject) setCreatingProject(false)
      else if (creating) setCreating(false)
      else if (archiveOpen) setArchiveOpen(false)
      else if (openedId) setOpenedId(null)
    }
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = ''
      window.removeEventListener('keydown', onKey)
    }
  }, [creating, creatingProject, archiveOpen, openedId])

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

  function selectProject(value: string) {
    setProject(value)
    if (value !== 'all') writeLastProject(value)
    reload(value).catch((err: unknown) => setError(err instanceof Error ? err.message : 'Ошибка'))
  }

  function onCreatedTask(task: Task) {
    setCreating(false)
    setNotice(`Создана ${task.id}`)
    setNoticeId(task.id)
    writeLastProject(task.project)
    if (narrow) setStatusFilter('inbox')

    const selectedProject = project === 'all' || project === task.project ? project : task.project
    if (selectedProject !== project) setProject(selectedProject)
    setTasks((current) => [
      task,
      ...(selectedProject === project ? current.filter((item) => item.id !== task.id) : []),
    ])
    reload(selectedProject, task).catch((err: unknown) => setError(err instanceof Error ? err.message : 'Ошибка'))
  }

  const listItems = grouped[statusFilter]
  const showProject = project === 'all'

  return (
    <div className={`app-shell ${narrow ? 'layout-mobile' : 'layout-desktop'}`}>
      <header className="topbar">
        <div className="brand">
          <h1>DevBoard</h1>
          {narrow ? null : <span>MadBoss</span>}
        </div>
        <div className="top-actions">
          <select value={project} onChange={(event) => selectProject(event.target.value)} aria-label="Проект">
            <option value="all">Все проекты</option>
            {projects.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <button
            className="btn ghost"
            type="button"
            onClick={() => setCreatingProject(true)}
            aria-label="Новый проект"
            title="Новый проект"
          >
            {narrow ? '+' : '+ Проект'}
          </button>
          {narrow ? null : (
            <button className="btn" type="button" onClick={() => setCreating(true)}>
              Новая задача
            </button>
          )}
          <button
            className="btn ghost archive-button"
            type="button"
            onClick={() => setArchiveOpen(true)}
            aria-label="Открыть архив"
            title="Архив"
          >
            <ArchiveIcon />
            <span className="archive-label">Архив</span>
          </button>
          <button className="btn ghost" type="button" onClick={onLogout}>
            Выйти
          </button>
        </div>
      </header>
      {error ? <div className="banner error">{error}</div> : null}
      {notice ? (
        <div className="banner ok">
          <span>{notice}</span>
          {noticeId ? (
            <button
              className="banner-link"
              type="button"
              onClick={() => {
                setOpenedId(noticeId)
                setNotice('')
                setNoticeId(null)
              }}
            >
              Открыть
            </button>
          ) : null}
        </div>
      ) : null}

      {narrow ? (
        <>
          <StatusTabs
            grouped={grouped}
            current={statusFilter}
            onChange={setStatusFilter}
          />
          <main className="task-list">
            {listItems.length === 0 ? (
              <div className="empty-slot">Пока пусто</div>
            ) : (
              listItems.map((task) => (
                <TaskCard
                  key={task.id}
                  task={task}
                  draggable={false}
                  showProject={showProject}
                  onOpen={() => setOpenedId(task.id)}
                />
              ))
            )}
          </main>
          <div className="capture-bar">
            <button className="btn" type="button" onClick={() => setCreating(true)}>
              Новая задача
            </button>
          </div>
        </>
      ) : (
        <main className="board">
          {STATUSES.map((column) => {
            const items = grouped[column.id]
            const collapsed = column.id === 'done' && !doneOpen
            return (
              <section
                key={column.id}
                className={`column ${column.id} ${items.length === 0 ? 'is-empty' : ''} ${collapsed ? 'collapsed' : ''} ${dropTarget === column.id ? 'drag-over' : ''}`}
                onDragOver={(event) => {
                  event.preventDefault()
                  setDropTarget(column.id)
                }}
                onDragLeave={(event) => {
                  if (event.currentTarget.contains(event.relatedTarget as Node)) return
                  setDropTarget((current) => (current === column.id ? null : current))
                }}
                onDrop={(event) => {
                  event.preventDefault()
                  setDropTarget(null)
                  const id = event.dataTransfer.getData('text/plain')
                  if (id) changeStatus(id, column.id).catch((err: unknown) => setError(err instanceof Error ? err.message : 'Ошибка'))
                }}
              >
                <div className="column-head">
                  <h2>{column.title}</h2>
                  <span className={`count ${column.id}`}>{items.length}</span>
                </div>
                {column.id === 'done' ? (
                  <button className="btn ghost done-toggle" type="button" onClick={() => setDoneOpen((value) => !value)}>
                    {doneOpen ? 'Свернуть' : 'Показать'}
                  </button>
                ) : null}
                {collapsed ? null : items.length === 0 ? (
                  <div className="empty-slot" />
                ) : (
                  items.map((task) => (
                    <TaskCard
                      key={task.id}
                      task={task}
                      draggable
                      showProject={showProject}
                      onOpen={() => setOpenedId(task.id)}
                      onDragEnd={() => setDropTarget(null)}
                    />
                  ))
                )}
              </section>
            )
          })}
        </main>
      )}

      {creatingProject ? (
        <NewProject
          onClose={() => setCreatingProject(false)}
          onCreated={async (name) => {
            const created = await createProject(name)
            setProjects((current) => (current.includes(created.project) ? current : [...current, created.project]))
            setProject(created.project)
            writeLastProject(created.project)
            setCreatingProject(false)
            setNotice(`Проект ${created.project} создан`)
            setNoticeId(null)
            await reload(created.project)
          }}
        />
      ) : null}
      {creating ? (
        <NewTask
          projects={projects}
          defaultProject={composerProject(project, projects, tasks)}
          narrow={narrow}
          onClose={() => setCreating(false)}
          onCreated={onCreatedTask}
        />
      ) : null}
      {archiveOpen ? (
        <ArchivedTasks
          narrow={narrow}
          onClose={() => setArchiveOpen(false)}
          onRestored={(task) => {
            if (narrow) setStatusFilter(task.status)
            const selectedProject = project === 'all' || project === task.project ? project : task.project
            if (selectedProject !== project) setProject(selectedProject)
            setTasks((current) => [
              task,
              ...(selectedProject === project ? current.filter((item) => item.id !== task.id) : []),
            ])
            setNotice(`${task.id} восстановлена`)
            setNoticeId(task.id)
            reload(selectedProject, task).catch((err: unknown) => setError(err instanceof Error ? err.message : 'Ошибка'))
          }}
        />
      ) : null}
      {opened ? (
        <TaskDetail
          task={opened}
          projects={projects}
          narrow={narrow}
          onClose={() => setOpenedId(null)}
          onChange={(task) => setTasks((current) => current.map((item) => (item.id === task.id ? task : item)))}
          onArchived={(task) => {
            setTasks((current) => current.filter((item) => item.id !== task.id))
            setOpenedId(null)
            setNotice(`${task.id} перемещена в архив`)
            setNoticeId(null)
          }}
        />
      ) : null}
    </div>
  )
}

function ArchiveIcon() {
  return (
    <svg className="archive-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 7h16v13H4zM3 4h18v4H3zm6 7h6" />
    </svg>
  )
}

function ArchivedTasks({
  narrow,
  onClose,
  onRestored,
}: {
  narrow: boolean
  onClose: () => void
  onRestored: (task: Task) => void
}) {
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [restoringId, setRestoringId] = useState<string | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    listTasks('all', true)
      .then((result) => setTasks(result.tasks))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Не удалось открыть архив'))
      .finally(() => setLoading(false))
  }, [])

  async function restore(task: Task) {
    setRestoringId(task.id)
    setError('')
    try {
      const result = await restoreTask(task.id)
      setTasks((current) => current.filter((item) => item.id !== task.id))
      onRestored(result.task)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось восстановить задачу')
    } finally {
      setRestoringId(null)
    }
  }

  return (
    <div className={`overlay ${narrow ? 'sheet' : ''}`} onClick={onClose}>
      <div className={`panel ${narrow ? 'sheet' : 'drawer'} archive-panel`} onClick={(event) => event.stopPropagation()}>
        <div className="sheet-head">
          <button className="btn ghost" type="button" onClick={onClose}>
            Закрыть
          </button>
          <h2>Архив</h2>
          <span className="archive-count">{tasks.length}</span>
        </div>

        {loading ? <div className="muted">Загружаю…</div> : null}
        {!loading && tasks.length === 0 ? <div className="empty-slot">В архиве пусто</div> : null}
        <div className="archive-list">
          {tasks.map((task) => (
            <div className="archive-item" key={task.id}>
              <div className="archive-item-copy">
                <div className="archive-item-meta">
                  <span className="mono">{task.id}</span>
                  <span>{task.project}</span>
                  <span>{STATUSES.find((item) => item.id === task.status)?.title}</span>
                </div>
                <div className="archive-item-title">{task.title}</div>
              </div>
              <button
                className="btn secondary"
                type="button"
                disabled={restoringId === task.id}
                onClick={() => restore(task).catch(() => undefined)}
              >
                {restoringId === task.id ? '…' : 'Восстановить'}
              </button>
            </div>
          ))}
        </div>
        {error ? <div className="status-error">{error}</div> : null}
      </div>
    </div>
  )
}

function StatusTabs({
  grouped,
  current,
  onChange,
}: {
  grouped: Record<Status, Task[]>
  current: Status
  onChange: (status: Status) => void
}) {
  return (
    <div className="status-tabs" role="tablist" aria-label="Статус">
      {STATUSES.map((column) => (
        <button
          key={column.id}
          className={`status-tab ${column.id} ${current === column.id ? 'is-on' : ''}`}
          type="button"
          role="tab"
          aria-selected={current === column.id}
          onClick={() => onChange(column.id)}
        >
          <span>{column.title}</span>
          <span className="tab-count">{grouped[column.id].length}</span>
        </button>
      ))}
    </div>
  )
}

function TaskCard({
  task,
  draggable,
  showProject,
  onOpen,
  onDragEnd,
}: {
  task: Task
  draggable: boolean
  showProject: boolean
  onOpen: () => void
  onDragEnd?: () => void
}) {
  const images = task.attachments.filter((item) => item.kind === 'image')
  const audioCount = task.attachments.filter((item) => item.kind === 'audio').length
  const fileCount = task.attachments.filter((item) => item.kind === 'file').length
  const preview = images[0]
  const excerpt = cardExcerpt(task)
  const marks = [
    audioCount ? (audioCount > 1 ? `голос ${audioCount}` : 'голос') : '',
    images.length ? (images.length > 1 ? `${images.length} фото` : 'фото') : '',
    fileCount ? (fileCount > 1 ? `${fileCount} файл` : 'файл') : '',
    task.comments_count ? `${task.comments_count} комм.` : '',
  ].filter(Boolean)

  return (
    <button
      className="task-card"
      type="button"
      draggable={draggable}
      onDragStart={draggable ? (event) => event.dataTransfer.setData('text/plain', task.id) : undefined}
      onDragEnd={onDragEnd}
      onClick={onOpen}
    >
      <div className="task-main">
        <div className="task-head">
          <div className="task-id mono">{task.id}</div>
          {task.priority === 'high' ? (
            <span className="pill high">
              <span className={`priority-dot ${task.priority}`} />
              {priorityTitle(task.priority)}
            </span>
          ) : (
            <span className={`priority-dot ${task.priority}`} title={priorityTitle(task.priority)} />
          )}
        </div>
        <div className="task-title">{task.title}</div>
        {excerpt ? <div className="task-excerpt">{excerpt}</div> : null}
        <div className="meta-row">
          {showProject ? <span className="pill project">{task.project}</span> : null}
          {marks.map((mark) => (
            <span className="meta-chip" key={mark}>
              {mark}
            </span>
          ))}
        </div>
      </div>
      {preview ? <img className="task-thumb" src={attachmentUrl(task.id, preview.filename)} alt="" /> : null}
    </button>
  )
}

function NewProject({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: (name: string) => Promise<void>
}) {
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (!name.trim()) return
    setBusy(true)
    setError('')
    try {
      await onCreated(name.trim())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось создать проект')
      setBusy(false)
    }
  }

  return (
    <div className="overlay center" onClick={onClose}>
      <form className="panel modal" onClick={(event) => event.stopPropagation()} onSubmit={onSubmit}>
        <h2>Новый проект</h2>
        <div className="field">
          <label htmlFor="project-name">Название</label>
          <input
            id="project-name"
            autoFocus
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="NeuroROP"
          />
        </div>
        {error ? <div className="status-error">{error}</div> : null}
        <div className="row-actions">
          <button className="btn" type="submit" disabled={busy || !name.trim()}>
            {busy ? 'Создаю…' : 'Создать'}
          </button>
          <button className="btn ghost" type="button" onClick={onClose}>
            Отмена
          </button>
        </div>
      </form>
    </div>
  )
}

function NewTask({
  projects,
  defaultProject,
  narrow,
  onClose,
  onCreated,
}: {
  projects: string[]
  defaultProject: string
  narrow: boolean
  onClose: () => void
  onCreated: (task: Task) => void
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
  const [fileHover, setFileHover] = useState(false)

  function addFiles(list: FileList | File[]) {
    setFiles((current) => [...current, ...Array.from(list)])
  }

  function pasteImages(event: ClipboardEvent<HTMLFormElement>) {
    const images = Array.from(event.clipboardData.files).filter((file) => file.type.startsWith('image/'))
    if (!images.length) return
    event.preventDefault()
    addFiles(images)
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
      onCreated(result.task)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось создать задачу')
    } finally {
      setBusy(false)
    }
  }

  const canSave = Boolean(title || description || files.length || transcript)
  const projectOptions = projects.includes(project) ? projects : [project, ...projects]

  return (
    <div className={`overlay ${narrow ? 'sheet' : ''}`} onClick={onClose}>
      <form
        className={`panel ${narrow ? 'sheet' : 'drawer'} composer`}
        onClick={(event) => event.stopPropagation()}
        onSubmit={onSubmit}
        onPaste={pasteImages}
        onDragOver={(event) => {
          event.preventDefault()
          setFileHover(true)
        }}
        onDragLeave={() => setFileHover(false)}
        onDrop={(event) => {
          event.preventDefault()
          setFileHover(false)
          if (event.dataTransfer.files.length) addFiles(event.dataTransfer.files)
        }}
      >
        <div className="sheet-head">
          <button className="btn ghost" type="button" onClick={onClose}>
            Отмена
          </button>
          <h2>Новая задача</h2>
          <button className="btn" type="submit" disabled={busy || recording || !canSave}>
            {busy ? 'Сохраняю…' : 'Создать'}
          </button>
        </div>

        <div className={`composer-body ${fileHover ? 'is-hover' : ''}`}>
          <div className="field">
            <select value={project} onChange={(event) => setProject(event.target.value)} aria-label="Проект">
              {projectOptions.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Название"
              autoFocus={!narrow}
            />
          </div>

          <div
            className={`image-dropzone ${fileHover ? 'is-hover' : ''}`}
            onDragOver={(event) => {
              event.preventDefault()
              setFileHover(true)
            }}
            onDrop={(event) => {
              event.preventDefault()
              event.stopPropagation()
              setFileHover(false)
              const images = Array.from(event.dataTransfer.files).filter((file) => file.type.startsWith('image/'))
              if (images.length) addFiles(images)
              else setError('Перетащите файл изображения')
            }}
          >
            Перетащите картинку сюда или вставьте через Ctrl+V
          </div>

          <div className="capture-actions">
            {recording ? (
              <button className="btn danger" type="button" onClick={stopRecording}>
                <span className="rec-dot" />
                Стоп
              </button>
            ) : (
              <button
                className="btn secondary"
                type="button"
                onClick={() => startRecording().catch((err: unknown) => setError(err instanceof Error ? err.message : 'Нет доступа к микрофону'))}
              >
                Записать
              </button>
            )}
            <FilePicker
              id="new-task-images"
              label="Скриншот / Ctrl+V"
              accept="image/*"
              multiple
              onFiles={addFiles}
            />
          </div>

          {transcribing ? <div className="muted">Расшифровываю…</div> : null}
          {transcript ? <div className="transcript-snip">{transcript}</div> : null}
          <FilePreview files={files} />

          <details className="more">
            <summary>Дополнительно</summary>
            <div className="field">
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Описание"
              />
            </div>
            <div className="field">
              <label htmlFor="new-priority">Приоритет</label>
              <select
                id="new-priority"
                value={priority}
                onChange={(event) => setPriority(event.target.value as Priority)}
              >
                {PRIORITIES.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <textarea
                className="transcript-field"
                value={transcript}
                onChange={(event) => setTranscript(event.target.value)}
                placeholder="Транскрипт"
              />
            </div>
            <div className="row-actions">
              <FilePicker id="new-task-files" label="Файлы" multiple onFiles={addFiles} />
              <FilePicker
                id="new-task-audio"
                label="Аудиофайл"
                accept="audio/*,video/webm"
                onFiles={(list) => {
                  const file = list[0]
                  if (!file) return
                  addFiles([file])
                  transcribeFile(file).catch(() => undefined)
                }}
              />
            </div>
          </details>
          {error ? <div className="status-error">{error}</div> : null}
        </div>
      </form>
    </div>
  )
}

function StatusSeg({
  value,
  onChange,
}: {
  value: Status
  onChange: (status: Status) => void
}) {
  return (
    <div className="status-seg" role="group" aria-label="Статус">
      {STATUSES.map((item) => (
        <button
          key={item.id}
          className={`status-seg-btn ${item.id} ${value === item.id ? 'is-on' : ''}`}
          type="button"
          aria-pressed={value === item.id}
          onClick={() => onChange(item.id)}
        >
          {item.title}
        </button>
      ))}
    </div>
  )
}

function TaskDetail({
  task,
  projects,
  narrow,
  onClose,
  onChange,
  onArchived,
}: {
  task: Task
  projects: string[]
  narrow: boolean
  onClose: () => void
  onChange: (task: Task) => void
  onArchived: (task: Task) => void
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
  const [copied, setCopied] = useState(false)
  const [saving, setSaving] = useState(false)
  const [archiving, setArchiving] = useState(false)

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

  async function patchFields(patch: Parameters<typeof patchTask>[1]) {
    try {
      const result = await patchTask(task.id, patch)
      onChange(result.task)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить')
    }
  }

  async function save() {
    setSaving(true)
    setError('')
    try {
      const result = await patchTask(task.id, { title, description, transcript, status, priority, project })
      onChange(result.task)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить')
    } finally {
      setSaving(false)
    }
  }

  async function copyPrompt() {
    setError('')
    try {
      const context = await getAgentContext(task.id)
      await navigator.clipboard.writeText(context.agent_prompt)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось скопировать промпт')
    }
  }

  async function archive() {
    if (!window.confirm(`Архивировать ${task.id}? Задачу и файлы можно будет восстановить.`)) return
    setArchiving(true)
    setError('')
    try {
      const result = await archiveTask(task.id)
      onArchived(result.task)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось архивировать задачу')
    } finally {
      setArchiving(false)
    }
  }

  return (
    <div className={`overlay ${narrow ? 'sheet' : ''}`} onClick={onClose}>
      <div className={`panel ${narrow ? 'sheet' : 'drawer'}`} onClick={(event) => event.stopPropagation()}>
        <div className="sheet-head">
          <button className="btn ghost" type="button" onClick={onClose}>
            Закрыть
          </button>
          <div className="mono detail-id">{task.id}</div>
          <button className="btn" type="button" onClick={() => save().catch(() => undefined)} disabled={saving}>
            {saving ? '…' : 'Сохранить'}
          </button>
        </div>

        <StatusSeg
          value={status}
          onChange={(next) => {
            setStatus(next)
            patchFields({ status: next }).catch(() => undefined)
          }}
        />

        <div className="detail-meta">
          <select
            value={project}
            onChange={(event) => {
              const next = event.target.value
              setProject(next)
              patchFields({ project: next }).catch(() => undefined)
            }}
            aria-label="Проект"
          >
            {projects.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <select
            value={priority}
            onChange={(event) => {
              const next = event.target.value as Priority
              setPriority(next)
              patchFields({ priority: next }).catch(() => undefined)
            }}
            aria-label="Приоритет"
          >
            {PRIORITIES.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </select>
        </div>

        <div className="row-actions">
          <button className="btn secondary" type="button" onClick={copyPrompt}>
            {copied ? 'Скопировано' : 'Промпт агенту'}
          </button>
          <a className="quiet-link" href={task.github_url} target="_blank" rel="noreferrer">
            GitHub
          </a>
        </div>
        {task.transcription_error ? <div className="status-error">{task.transcription_error}</div> : null}

        <div className="field">
          <label htmlFor="task-title">Название</label>
          <input id="task-title" value={title} onChange={(event) => setTitle(event.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="task-description">Описание</label>
          <textarea id="task-description" value={description} onChange={(event) => setDescription(event.target.value)} />
        </div>
        {task.transcript || transcript ? (
          <div className="field">
            <label htmlFor="task-transcript">Транскрипт</label>
            <textarea
              id="task-transcript"
              className="transcript-field"
              value={transcript}
              onChange={(event) => setTranscript(event.target.value)}
            />
          </div>
        ) : null}

        <div className="field attachments">
          {task.attachments.length === 0 ? null : (
            task.attachments.map((item) => (
              <div key={item.filename} className="attach-item">
                {item.kind === 'image' ? (
                  <a href={attachmentUrl(task.id, item.filename)} target="_blank" rel="noreferrer">
                    <img src={attachmentUrl(task.id, item.filename)} alt={item.filename} />
                  </a>
                ) : null}
                {item.kind === 'audio' ? (
                  <audio controls src={attachmentUrl(task.id, item.filename)} />
                ) : null}
                {item.kind !== 'image' ? (
                  <a href={attachmentUrl(task.id, item.filename)} target="_blank" rel="noreferrer">
                    {item.filename}
                  </a>
                ) : null}
              </div>
            ))
          )}
          <FilePicker
            id={`task-files-${task.id}`}
            label="Добавить"
            multiple
            onFiles={async (list) => {
              const result = await addAttachments(task.id, Array.from(list))
              onChange(result.task)
            }}
          />
        </div>
        {error ? <div className="status-error">{error}</div> : null}

        {comments.length ? (
          <div className="comment-list">
            {comments.map((item) => (
              <div className="comment" key={`${item.created_at}-${item.body}`}>
                <div className="muted">
                  {item.author} · {item.created_at.slice(0, 16).replace('T', ' ')}
                </div>
                <div>{item.body}</div>
              </div>
            ))}
          </div>
        ) : null}
        <textarea value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Комментарий" />
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
            Добавить
          </button>
        </div>
        <div className="archive-task-action">
          <button
            className="btn ghost archive-task-button"
            type="button"
            disabled={archiving}
            onClick={() => archive().catch(() => undefined)}
          >
            {archiving ? 'Архивирую…' : 'Архивировать задачу'}
          </button>
        </div>
      </div>
    </div>
  )
}

function FilePicker({
  id,
  label,
  accept,
  multiple,
  onFiles,
}: {
  id: string
  label: string
  accept?: string
  multiple?: boolean
  onFiles: (files: FileList) => void
}) {
  return (
    <>
      <input
        id={id}
        className="file-input"
        type="file"
        accept={accept}
        multiple={multiple}
        onChange={(event) => {
          if (event.target.files?.length) onFiles(event.target.files)
          event.target.value = ''
        }}
      />
      <label htmlFor={id} className="btn secondary">
        {label}
      </label>
    </>
  )
}

function FilePreview({ files }: { files: File[] }) {
  const items = useMemo(
    () =>
      files.map((file, index) => ({
        file,
        index,
        url: file.type.startsWith('image/') ? URL.createObjectURL(file) : '',
      })),
    [files],
  )

  useEffect(() => {
    return () => {
      for (const item of items) {
        if (item.url) URL.revokeObjectURL(item.url)
      }
    }
  }, [items])

  if (!files.length) return null
  return (
    <div className="preview-grid">
      {items.map((item) =>
        item.url ? (
          <img key={`${item.file.name}-${item.index}`} src={item.url} alt={item.file.name} />
        ) : (
          <div className="file-chip" key={`${item.file.name}-${item.index}`}>
            {item.file.name}
          </div>
        ),
      )}
    </div>
  )
}
