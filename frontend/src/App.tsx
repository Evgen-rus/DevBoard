import { useEffect, useState, type FormEvent } from 'react'
import { AuthError, login, logout, me } from './api'
import Board from './Board'

export default function App() {
  const [ready, setReady] = useState(false)
  const [authed, setAuthed] = useState(false)
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    me()
      .then(() => setAuthed(true))
      .catch((err: unknown) => {
        if (!(err instanceof AuthError)) setError(err instanceof Error ? err.message : 'Ошибка')
      })
      .finally(() => setReady(true))
  }, [])

  async function onLogin(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(password)
      setAuthed(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось войти')
    } finally {
      setBusy(false)
    }
  }

  async function onLogout() {
    await logout()
    setAuthed(false)
  }

  if (!ready) {
    return (
      <div className="splash">
        <div className="muted">Открываю DevBoard…</div>
      </div>
    )
  }

  if (!authed) {
    return (
      <div className="login-wrap">
        <form className="login-card" onSubmit={onLogin}>
          <h1>DevBoard</h1>
          <p>Внутренняя доска задач для агентной разработки. Один общий пароль.</p>
          <div className="field">
            <label htmlFor="password">Пароль</label>
            <input
              id="password"
              type="password"
              autoFocus
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          {error ? <div className="status-error">{error}</div> : null}
          <div className="row-actions">
            <button className="btn" type="submit" disabled={busy || !password}>
              {busy ? 'Вхожу…' : 'Войти'}
            </button>
          </div>
        </form>
      </div>
    )
  }

  return <Board onLogout={onLogout} />
}
