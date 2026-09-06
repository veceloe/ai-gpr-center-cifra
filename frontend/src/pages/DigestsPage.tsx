/** Дайджест под получателя — US7, FR-070…FR-072. */

import { useEffect, useRef, useState } from 'react'
import { ApiError, api } from '../api/client'
import type { Digest } from '../api/types'
import { formatFullDate, formatIndex, plural } from '../lib/format'

interface Props {
  selection: number[]
  onSelectionChange: (ids: number[]) => void
  onToast: (message: string) => void
}

export function DigestsPage({ selection, onSelectionChange, onToast }: Props) {
  const [digests, setDigests] = useState<Digest[]>([])
  const [error, setError] = useState<string | null>(null)
  const [recipient, setRecipient] = useState('')
  const [title, setTitle] = useState('')
  const dialog = useRef<HTMLDialogElement>(null)

  async function load() {
    try {
      setDigests(await api.digests())
      setError(null)
    } catch (e) {
      setError((e as ApiError).message)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  async function create() {
    try {
      await api.createDigest({
        recipient: recipient.trim(),
        title: title.trim() || undefined,
        item_ids: selection,
      })
      dialog.current?.close()
      setRecipient('')
      setTitle('')
      onSelectionChange([])
      await load()
      onToast('Дайджест собран')
    } catch (e) {
      onToast((e as ApiError).message)
    }
  }

  async function toggle(digestId: number, itemId: number, excluded: boolean) {
    const updated = await api.toggleDigestEntry(digestId, itemId, excluded)
    setDigests((prev) => prev.map((d) => (d.id === updated.id ? updated : d)))
    onToast(excluded ? 'Материал исключён из дайджеста, в ленте он остался' : 'Материал возвращён')
  }

  return (
    <>
      <div className="filters">
        <button
          type="button"
          className="btn btn-primary"
          disabled={selection.length === 0}
          onClick={() => dialog.current?.showModal()}
        >
          Собрать дайджест из отобранных ({selection.length})
        </button>
        {selection.length > 0 && (
          <button type="button" className="btn btn-ghost" onClick={() => onSelectionChange([])}>
            сбросить отбор
          </button>
        )}
      </div>

      {selection.length === 0 && digests.length === 0 && (
        <div className="empty">
          <h3>Дайджестов пока нет</h3>
          <p>
            Отметьте материалы галочками в ленте, затем вернитесь сюда и соберите
            дайджест для конкретного получателя.
          </p>
        </div>
      )}

      {error && (
        <div className="card" style={{ borderColor: 'var(--risk)' }}>
          <b>Не удалось загрузить дайджесты.</b> {error}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {digests.map((digest) => {
          const included = digest.entries.filter((e) => !e.is_excluded)
          return (
            <div className="card" key={digest.id}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                <div>
                  <h2 style={{ fontFamily: 'var(--font-head)', fontSize: 16, margin: 0 }}>
                    {digest.title}
                  </h2>
                  <p style={{ margin: '3px 0 0', fontSize: 12.5, color: 'var(--muted)' }}>
                    Получатель: {digest.recipient} · {formatFullDate(digest.created_at)} ·{' '}
                    {plural(included.length, 'материал', 'материала', 'материалов')}
                  </p>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <a className="btn btn-sm" href={api.digestExportUrl(digest.id, 'html')} target="_blank" rel="noreferrer">
                    HTML
                  </a>
                  <a className="btn btn-sm" href={api.digestExportUrl(digest.id, 'md')} target="_blank" rel="noreferrer">
                    Markdown
                  </a>
                </div>
              </div>

              <table className="grid" style={{ marginTop: 12 }}>
                <tbody>
                  {digest.entries.map((entry) => (
                    <tr key={entry.item.id} style={{ opacity: entry.is_excluded ? 0.45 : 1 }}>
                      <td className="num" style={{ width: 60 }}>
                        {formatIndex(entry.item.index_value)}
                      </td>
                      <td>
                        <div style={{ textDecoration: entry.is_excluded ? 'line-through' : 'none' }}>
                          {entry.item.title}
                        </div>
                        <div style={{ fontSize: 11.5, color: 'var(--faint)' }}>
                          {entry.item.source.title}
                        </div>
                      </td>
                      <td style={{ width: 130 }}>
                        <button
                          type="button"
                          className="btn btn-sm"
                          onClick={() => toggle(digest.id, entry.item.id, !entry.is_excluded)}
                        >
                          {entry.is_excluded ? 'вернуть' : 'исключить'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        })}
      </div>

      <dialog ref={dialog}>
        <div className="dialog-head">
          <h2>Дайджест для получателя</h2>
        </div>
        <div className="dialog-body">
          <div className="form-row">
            <label htmlFor="d-recipient">Кому</label>
            <input
              id="d-recipient"
              value={recipient}
              onChange={(e) => setRecipient(e.target.value)}
              placeholder="например: директор по развитию"
            />
          </div>
          <div className="form-row">
            <label htmlFor="d-title">Заголовок (необязательно)</label>
            <input id="d-title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: 0 }}>
            Отобрано {plural(selection.length, 'материал', 'материала', 'материалов')}.
            Порядок сохранится тем, в котором вы их отметили.
          </p>
        </div>
        <div className="dialog-foot">
          <button type="button" className="btn" onClick={() => dialog.current?.close()}>
            Отмена
          </button>
          <button type="button" className="btn btn-primary" disabled={!recipient.trim()} onClick={create}>
            Собрать
          </button>
        </div>
      </dialog>
    </>
  )
}
