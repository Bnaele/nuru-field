// MarketPage — the two-sided market, split into sections a beginner can read.
//
// The split is not decided here: the backend owns the section list (label,
// plain-language hint, icon) and sends it with a live count in each. That way
// adding "Beekeeping" or "Irrigation" later is one entry in marketplace.py, and
// the tabs, the chips, the sell form and the write validation all follow.
//
// Looking does not need a session on the API, but the page sits behind login
// with the rest of the app so the nav and the sign-out behave the same
// everywhere.

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import Icon from '../components/Icon'
import { api } from '../lib/api'

/** Rands, because that is what a seller types and what a buyer expects. */
function formatPrice(cents) {
  if (cents === null || cents === undefined) return 'Price on request'
  return `R${(cents / 100).toLocaleString('en-ZA', { maximumFractionDigits: 2 })}`
}

function formatDate(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString('en-ZA', { day: 'numeric', month: 'short' })
}

export default function MarketPage() {
  // A crop guide links straight to the section it is about - /market?kind=input
  // &category=tools - so "you will need a spade" lands on spades instead of on
  // the whole market for the grower to search again.
  const [params] = useSearchParams()
  const [groups, setGroups] = useState([])
  const [tab, setTab] = useState(params.get('kind') === 'produce' ? 'produce' : 'input')
  const [section, setSection] = useState(params.get('category') || '')
  const [query, setQuery] = useState('')
  const [needle, setNeedle] = useState('')
  const [rows, setRows] = useState([])
  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')
  const [active, setActive] = useState(null)

  // Sections carry the counts, so they are fetched once. A failed fetch must not
  // take the listings down with it: browsing still works without the chips.
  useEffect(() => {
    let cancelled = false
    api
      .marketSections()
      .then((data) => {
        if (!cancelled) setGroups(data.groups || [])
      })
      .catch((failure) => {
        if (!cancelled) setError(failure.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Typing should not fire a request per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => setNeedle(query.trim()), 300)
    return () => clearTimeout(timer)
  }, [query])

  useEffect(() => {
    const controller = new AbortController()
    setStatus('loading')
    api
      .listings({
        kind: tab,
        category: section || undefined,
        q: needle || undefined,
        signal: controller.signal,
      })
      .then((data) => {
        setRows(data)
        setStatus('ready')
        setError('')
      })
      .catch((failure) => {
        if (failure.name === 'AbortError') return
        setError(failure.message)
        setStatus('error')
      })
    return () => controller.abort()
  }, [tab, section, needle])

  const group = useMemo(() => groups.find((item) => item.kind === tab), [groups, tab])
  const openSection = useMemo(
    () => group?.sections.find((item) => item.key === section) || null,
    [group, section],
  )

  // A section named in the URL may not exist on this tab, or may have been
  // renamed since the link was written. Clearing it shows the whole tab rather
  // than an empty grid with no chip highlighted.
  useEffect(() => {
    if (!section || !group) return
    if (!group.sections.some((item) => item.key === section)) setSection('')
  }, [group, section])

  const switchTab = useCallback((kind) => {
    setTab(kind)
    setSection('')
  }, [])

  return (
    <main className="market-page">
      <div className="container">
        <header className="market-head">
          <div>
            <p className="market-kicker">Nuru Market</p>
            <h1>Buy what you need. Sell what you grow.</h1>
            <p className="market-lede">
              Every listing is posted by a grower, a co-op or a supplier. Pick the section
              that matches your problem and talk to the seller directly.
            </p>
          </div>
          <div className="market-head-actions">
            <Link to="/sell" className="button button-primary">
              Post something
            </Link>
            <Link to="/inbox" className="market-link-quiet">
              <Icon name="chat" size={15} />
              Messages
            </Link>
          </div>
        </header>

        {/* Said once, at the top, so nobody reaches for a card. */}
        <p className="market-proto">
          <Icon name="spark" size={15} />
          <span>
            Prototype. Deal directly with the seller - Nuru takes no payment, no commission
            and holds nothing in escrow.
          </span>
        </p>

        <div className="market-tabs" role="tablist" aria-label="Market halves">
          {(groups.length ? groups : [{ kind: 'input' }, { kind: 'produce' }]).map((item) => (
            <button
              key={item.kind}
              type="button"
              role="tab"
              aria-selected={tab === item.kind}
              className={'market-tab' + (tab === item.kind ? ' active' : '')}
              onClick={() => switchTab(item.kind)}
            >
              <span className="market-tab-label">
                {item.label || (item.kind === 'input' ? 'Supplies' : 'Harvest')}
                {typeof item.count === 'number' && (
                  <em>{item.count === 0 ? 'nothing yet' : `${item.count} listed`}</em>
                )}
              </span>
              <span className="market-tab-hint">{item.hint}</span>
            </button>
          ))}
        </div>

        <div className="market-toolbar">
          <div className="market-search">
            <Icon name="search" size={16} />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={tab === 'input' ? 'Search seed, compost, sprayer…' : 'Search tomatoes, eggs…'}
              aria-label="Search the market"
            />
          </div>
          <Link to="/sell" className="market-link-quiet">
            Selling? Post it in a minute
            <Icon name="arrow" size={15} />
          </Link>
        </div>

        <div className="market-rail" role="group" aria-label="Sections">
          <button
            type="button"
            className={'market-chip' + (section === '' ? ' active' : '')}
            onClick={() => setSection('')}
          >
            Everything in {group?.label || (tab === 'input' ? 'Supplies' : 'Harvest')}
          </button>
          {(group?.sections || []).map((item) => (
            <button
              key={item.key}
              type="button"
              className={'market-chip' + (section === item.key ? ' active' : '')}
              onClick={() => setSection(item.key)}
            >
              <Icon name={item.icon || 'leaf'} size={14} />
              {item.label}
              {item.count > 0 && <em>{item.count}</em>}
            </button>
          ))}
        </div>

        {/* The section's own sentence, so an empty section still teaches
            something instead of showing a blank grid. */}
        {openSection && <p className="market-section-hint">{openSection.hint}</p>}

        {status === 'error' && (
          <p className="card-error">
            <strong>The market did not load.</strong> {error}
          </p>
        )}

        {status === 'loading' && (
          <div className="market-grid" aria-busy="true">
            {[0, 1, 2].map((key) => (
              <div className="skeleton-card" key={key}>
                <div className="skeleton skeleton-line medium" />
                <div className="skeleton skeleton-line full" />
                <div className="skeleton skeleton-line full" />
              </div>
            ))}
          </div>
        )}

        {status === 'ready' && rows.length === 0 && (
          <div className="market-empty">
            <span className="market-empty-mark">
              <Icon name={openSection?.icon || 'leaf'} size={22} />
            </span>
            <h3>{needle ? 'Nothing matches that search' : 'Nothing here yet'}</h3>
            <p>
              {needle
                ? 'Try a shorter word, or look in another section.'
                : `${openSection?.hint || 'This half of the market is empty.'} If that is what you sell, post the first one.`}
            </p>
            <Link to="/sell" className="button button-primary">
              Post a listing
            </Link>
          </div>
        )}

        {status === 'ready' && rows.length > 0 && (
          <div className="market-grid">
            {rows.map((row) => (
              <article className="market-card" key={row.id}>
                <button type="button" className="market-card-open" onClick={() => setActive(row)}>
                  <span className="market-card-art">
                    {row.images?.[0] ? (
                      <img src={row.images[0]} alt="" loading="lazy" />
                    ) : (
                      <Icon
                        name={
                          group?.sections.find((item) => item.key === row.category)?.icon || 'leaf'
                        }
                        size={26}
                      />
                    )}
                  </span>
                  <span className="market-card-body">
                    <span className="market-card-tag">{row.category_label}</span>
                    <strong className="market-card-title">{row.title}</strong>
                    {row.quantity && <span className="market-card-qty">{row.quantity}</span>}
                    <span className="market-card-price">
                      {formatPrice(row.price_cents)}
                      {row.price_cents !== null && row.unit && <em>{row.unit}</em>}
                    </span>
                    <span className="market-card-meta">
                      {row.seller_name}
                      {row.region ? ` · ${row.region}` : ''}
                      {row.created_at ? ` · ${formatDate(row.created_at)}` : ''}
                    </span>
                  </span>
                </button>
              </article>
            ))}
          </div>
        )}
      </div>

      {active && <ListingPanel listing={active} onClose={() => setActive(null)} />}
    </main>
  )
}

function ListingPanel({ listing, onClose }) {
  const [detail, setDetail] = useState(listing)
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState(false)
  const [problem, setProblem] = useState('')

  // The list row is enough to render the panel, so it paints immediately; the
  // detail call only adds what a grid does not carry (full description, the
  // seller's own note).
  useEffect(() => {
    let cancelled = false
    api
      .listing(listing.id)
      .then((data) => {
        if (!cancelled) setDetail(data)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [listing.id])

  useEffect(() => {
    const onKey = (event) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  async function send(event) {
    event.preventDefault()
    setSending(true)
    setProblem('')
    try {
      await api.expressInterest(listing.id, message)
      setSent(true)
    } catch (failure) {
      setProblem(failure.message)
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="market-panel" role="dialog" aria-modal="true" aria-label={detail.title}>
      <button type="button" className="market-panel-scrim" onClick={onClose} aria-label="Close" />
      <div className="market-dialog">
        <button type="button" className="market-dialog-close" onClick={onClose} aria-label="Close">
          <Icon name="close" size={18} />
        </button>

        {detail.images?.[0] && (
          <div className="market-dialog-photo">
            <img src={detail.images[0]} alt="" />
          </div>
        )}

        <div className="market-dialog-body">
          <p className="market-card-tag">{detail.category_label}</p>
          <h2>{detail.title}</h2>
          <p className="market-dialog-price">
            {formatPrice(detail.price_cents)}
            {detail.price_cents !== null && detail.unit && <em>{detail.unit}</em>}
          </p>
          <p className="market-dialog-meta">
            <Icon name="location" size={14} />
            {detail.seller_name}
            {detail.region ? ` · ${detail.region}` : ''}
          </p>
          {detail.description && <p className="market-dialog-text">{detail.description}</p>}
          {detail.seller_profile?.contact_note && (
            <p className="market-dialog-note">
              <strong>From the seller:</strong> {detail.seller_profile.contact_note}
            </p>
          )}

          {sent ? (
            <div className="market-sent">
              <Icon name="check" size={18} />
              <div>
                <strong>Message sent to {detail.seller_name}.</strong>
                <p>
                  They reply in your messages. Agree the price and the pickup between you -
                  nothing is charged here.
                </p>
                <Link to="/inbox" className="button button-primary">
                  Open messages
                </Link>
              </div>
            </div>
          ) : (
            <form className="market-contact" onSubmit={send}>
              <label htmlFor="market-message">Ask about this</label>
              <textarea
                id="market-message"
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                rows={3}
                maxLength={1000}
                placeholder={
                  detail.kind === 'input'
                    ? 'e.g. Do you have 20 of these, and can I collect on Saturday?'
                    : 'e.g. Is this still available, and how much for the whole crate?'
                }
              />
              {problem && <p className="form-error">{problem}</p>}
              <button type="submit" className="button button-primary" disabled={sending}>
                {sending ? 'Sending…' : 'Send to seller'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
