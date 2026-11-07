// InboxPage — the conversations a listing opens.
//
// A thread exists only between a buyer and the seller of one listing, so every
// row is a person asking about a specific thing. Opening a listing from the
// market sends the first message; this page is where both sides carry on.
//
// There is no polling. A reply shows up on the next load, which is honest for a
// prototype and cheaper than a socket that is usually idle.

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Icon from '../components/Icon'
import { api } from '../lib/api'

function formatWhen(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('en-ZA', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function InboxPage() {
  const [threads, setThreads] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [thread, setThread] = useState(null)
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)

  useEffect(() => {
    let cancelled = false
    api
      .conversations()
      .then((data) => {
        if (cancelled) return
        setThreads(data)
        setStatus('ready')
        if (data.length) setActiveId(data[0].id)
      })
      .catch((failure) => {
        if (cancelled) return
        setError(failure.message)
        setStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!activeId) {
      setThread(null)
      return undefined
    }
    let cancelled = false
    api
      .conversation(activeId)
      .then((data) => {
        if (!cancelled) setThread(data)
      })
      .catch((failure) => {
        if (!cancelled) setError(failure.message)
      })
    return () => {
      cancelled = true
    }
  }, [activeId])

  async function send(event) {
    event.preventDefault()
    const body = draft.trim()
    if (!body || !activeId) return
    setSending(true)
    setError('')
    try {
      const message = await api.sendMessage(activeId, body)
      setDraft('')
      setThread((current) =>
        current ? { ...current, messages: [...(current.messages || []), message] } : current,
      )
    } catch (failure) {
      setError(failure.message)
    } finally {
      setSending(false)
    }
  }

  // The row that carries the listing title and which side this viewer is on.
  const activeThread = threads.find((item) => item.id === activeId) || null

  return (
    <main className="market-page">
      <div className="container">
        <header className="market-head">
          <div>
            <p className="market-kicker">Messages</p>
            <h1>Talk to the other side</h1>
            <p className="market-lede">
              Every thread is attached to one listing. Agree the price, the quantity and the
              handover here - Nuru never handles the money.
            </p>
          </div>
        </header>

        {error && (
          <p className="card-error">
            <strong>Something went wrong.</strong> {error}
          </p>
        )}

        {status === 'ready' && threads.length === 0 && (
          <div className="market-empty">
            <span className="market-empty-mark">
              <Icon name="chat" size={22} />
            </span>
            <h3>No messages yet</h3>
            <p>
              Ask a seller about a listing and the thread lands here. Or post something
              yourself and wait for a buyer.
            </p>
            <Link to="/market" className="button button-primary">
              Browse the market
            </Link>
          </div>
        )}

        {threads.length > 0 && (
          <div className="inbox-layout">
            <ul className="inbox-list">
              {threads.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className={'inbox-row' + (item.id === activeId ? ' active' : '')}
                    onClick={() => setActiveId(item.id)}
                  >
                    <strong>{item.listing_title}</strong>
                    <span>
                      {item.is_seller ? `Buyer: ${item.other_name}` : `Seller: ${item.other_name}`}
                    </span>
                    <span className="inbox-when">{formatWhen(item.created_at)}</span>
                  </button>
                </li>
              ))}
            </ul>

            <div className="inbox-thread">
              {thread ? (
                <>
                  <div className="inbox-thread-head">
                    <strong>{activeThread?.listing_title}</strong>
                    <span>{activeThread?.is_seller ? 'You are the seller' : 'You are the buyer'}</span>
                  </div>

                  <div className="inbox-messages">
                    {(thread.messages || []).map((message) => {
                      // Your own side sits on the right, whichever side that is:
                      // the seller reading their own inbox should not find their
                      // replies on the stranger's side of the thread.
                      const mine = activeThread?.is_seller
                        ? message.sender_id !== thread.buyer_id
                        : message.sender_id === thread.buyer_id
                      return (
                        <div key={message.id} className={'inbox-message' + (mine ? ' buyer' : '')}>
                          <span>{message.body}</span>
                          <time>{formatWhen(message.created_at)}</time>
                        </div>
                      )
                    })}
                  </div>

                  <form className="inbox-form" onSubmit={send}>
                    <input
                      value={draft}
                      onChange={(event) => setDraft(event.target.value)}
                      placeholder="Write a reply…"
                      aria-label="Reply"
                      maxLength={2000}
                    />
                    <button type="submit" disabled={sending || !draft.trim()} aria-label="Send">
                      <Icon name="arrow" size={16} />
                    </button>
                  </form>
                </>
              ) : (
                <p className="inbox-placeholder">Pick a conversation.</p>
              )}
            </div>
          </div>
        )}
      </div>
    </main>
  )
}
