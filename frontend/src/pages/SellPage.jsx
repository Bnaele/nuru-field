// SellPage — post a listing.
//
// Two steps, in this order on purpose: who you are, then what you are selling.
// A listing with no name behind it is the quickest way to make a market feel
// like a scam, so the API refuses to accept one and this page asks first.
//
// Prices are typed in rands and stored in cents, because floating-point money
// is a defect waiting to happen.

import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Icon from '../components/Icon'
import { api } from '../lib/api'

const BLANK = {
  displayName: '',
  region: '',
  contactNote: '',
}

export default function SellPage() {
  const navigate = useNavigate()
  const [profile, setProfile] = useState(null)
  const [groups, setGroups] = useState([])
  const [checking, setChecking] = useState(true)
  const [savingProfile, setSavingProfile] = useState(false)
  const [form, setForm] = useState({ ...BLANK })
  const [kind, setKind] = useState('input')
  const [category, setCategory] = useState('')
  const [listing, setListing] = useState({
    title: '',
    description: '',
    price: '',
    unit: '',
    quantity: '',
    region: '',
  })
  const [saving, setSaving] = useState(false)
  const [problem, setProblem] = useState('')
  const [created, setCreated] = useState(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([
      api.profile().catch(() => null),
      api.marketSections().then((data) => data.groups || []).catch(() => []),
    ])
      .then(([me, sections]) => {
        if (cancelled) return
        setProfile(me)
        setGroups(sections)
        if (me) {
          setForm({
            displayName: me.display_name || '',
            region: me.region || '',
            contactNote: me.contact_note || '',
          })
          setListing((current) => ({ ...current, region: me.region || '' }))
        }
        setCategory(sections.find((group) => group.kind === 'input')?.sections?.[0]?.key || '')
      })
      .finally(() => {
        if (!cancelled) setChecking(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const group = useMemo(() => groups.find((item) => item.kind === kind), [groups, kind])

  function switchKind(next) {
    setKind(next)
    const first = groups.find((item) => item.kind === next)?.sections?.[0]?.key || ''
    setCategory(first)
  }

  async function saveProfile(event) {
    event.preventDefault()
    setProblem('')
    setSavingProfile(true)
    try {
      const saved = await api.saveProfile({
        display_name: form.displayName.trim(),
        region: form.region.trim(),
        role: 'both',
        contact_note: form.contactNote.trim(),
      })
      setProfile(saved)
      setListing((current) => ({ ...current, region: current.region || saved.region || '' }))
    } catch (failure) {
      setProblem(failure.message)
    } finally {
      setSavingProfile(false)
    }
  }

  async function post(event) {
    event.preventDefault()
    setProblem('')

    const rand = listing.price.trim()
    const priceCents = rand === '' ? null : Math.round(Number(rand) * 100)
    if (priceCents !== null && (!Number.isFinite(priceCents) || priceCents < 0)) {
      setProblem('The price must be a number, like 45 or 12.50. Leave it empty for "on request".')
      return
    }

    setSaving(true)
    try {
      const result = await api.createListing({
        kind,
        category,
        title: listing.title.trim(),
        description: listing.description.trim(),
        price_cents: priceCents,
        unit: listing.unit.trim(),
        quantity: listing.quantity.trim(),
        region: listing.region.trim(),
      })
      setCreated(result)
    } catch (failure) {
      // 409 means the API has no profile for this account: fall back to the
      // name step rather than leaving the seller staring at an error.
      if (failure.status === 409) setProfile(null)
      setProblem(failure.message)
    } finally {
      setSaving(false)
    }
  }

  if (checking) {
    return (
      <main className="market-page">
        <div className="container">
          <div className="skeleton-card">
            <div className="skeleton skeleton-title" />
            <div className="skeleton skeleton-line full" />
            <div className="skeleton skeleton-line medium" />
          </div>
        </div>
      </main>
    )
  }

  if (created) {
    return (
      <main className="market-page">
        <div className="container market-narrow">
          <div className="market-empty">
            <span className="market-empty-mark">
              <Icon name="check" size={22} />
            </span>
            <h2>“{created.title}” is live</h2>
            <p>
              It is in {created.category_label || 'your section'} on the market now. Buyers
              message you here, and you reply in Messages.
            </p>
            <div className="market-success-actions">
              <Link to="/market" className="button button-primary">
                See it on the market
              </Link>
              <button
                type="button"
                className="market-link-quiet"
                onClick={() => {
                  setCreated(null)
                  setListing({
                    title: '',
                    description: '',
                    price: '',
                    unit: '',
                    quantity: '',
                    region: profile?.region || '',
                  })
                }}
              >
                Post another
              </button>
            </div>
          </div>
        </div>
      </main>
    )
  }

  return (
    <main className="market-page">
      <div className="container market-narrow">
        <header className="market-head">
          <div>
            <p className="market-kicker">Sell on Nuru</p>
            <h1>Post what you are selling</h1>
            <p className="market-lede">
              Seed, seedlings, compost, feed, tools, water fittings - or the harvest itself.
              One listing, one section, and buyers can ask you directly.
            </p>
          </div>
        </header>

        {!profile && (
          <form className="market-form" onSubmit={saveProfile}>
            <h2>First, who is selling?</h2>
            <p className="market-form-note">
              This is the name and area buyers see on every listing you post.
            </p>

            <label htmlFor="sell-name">Display name or business name</label>
            <input
              id="sell-name"
              required
              minLength={2}
              maxLength={60}
              value={form.displayName}
              onChange={(event) => setForm({ ...form, displayName: event.target.value })}
              placeholder="e.g. Thando's Nursery, or Sipho M."
            />

            <label htmlFor="sell-region">Town or area</label>
            <input
              id="sell-region"
              maxLength={80}
              value={form.region}
              onChange={(event) => setForm({ ...form, region: event.target.value })}
              placeholder="e.g. Umlazi, Durban"
            />

            <label htmlFor="sell-note">How should buyers reach you? (optional)</label>
            <input
              id="sell-note"
              maxLength={200}
              value={form.contactNote}
              onChange={(event) => setForm({ ...form, contactNote: event.target.value })}
              placeholder="e.g. Collect at the market stall on Saturdays"
            />

            {problem && <p className="form-error">{problem}</p>}
            <button type="submit" className="button button-primary" disabled={savingProfile}>
              {savingProfile ? 'Saving…' : 'Save and continue'}
            </button>
          </form>
        )}

        {profile && (
          <form className="market-form" onSubmit={post}>
            <p className="market-form-note">
              Posting as <strong>{profile.display_name}</strong>
              {profile.region ? ` in ${profile.region}` : ''}.{' '}
              <button
                type="button"
                className="market-inline-link"
                onClick={() => setProfile(null)}
              >
                Change
              </button>
            </p>

            <span className="market-form-legend">What are you selling?</span>
            <div className="market-kind-picker">
              {(groups.length ? groups : [{ kind: 'input', label: 'Supplies' }, { kind: 'produce', label: 'Harvest' }]).map(
                (item) => (
                  <button
                    key={item.kind}
                    type="button"
                    className={'market-kind' + (kind === item.kind ? ' active' : '')}
                    onClick={() => switchKind(item.kind)}
                  >
                    <strong>{item.label || (item.kind === 'input' ? 'Supplies' : 'Harvest')}</strong>
                    <span>{item.hint}</span>
                  </button>
                ),
              )}
            </div>

            <label htmlFor="sell-category">Section</label>
            <select
              id="sell-category"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              required
            >
              {(group?.sections || []).map((item) => (
                <option key={item.key} value={item.key}>
                  {item.label} - {item.hint}
                </option>
              ))}
            </select>

            <label htmlFor="sell-title">What is it?</label>
            <input
              id="sell-title"
              required
              minLength={3}
              maxLength={120}
              value={listing.title}
              onChange={(event) => setListing({ ...listing, title: event.target.value })}
              placeholder={
                kind === 'input' ? 'e.g. Spinach seedlings in trays of 12' : 'e.g. Spinach, 20 bunches'
              }
            />

            <label htmlFor="sell-description">Details a buyer needs (optional)</label>
            <textarea
              id="sell-description"
              rows={4}
              maxLength={2000}
              value={listing.description}
              onChange={(event) => setListing({ ...listing, description: event.target.value })}
              placeholder="Variety, size, condition, when it is ready, delivery or collection."
            />

            <div className="market-form-row">
              <div>
                <label htmlFor="sell-price">Price in rand (optional)</label>
                <input
                  id="sell-price"
                  inputMode="decimal"
                  value={listing.price}
                  onChange={(event) => setListing({ ...listing, price: event.target.value })}
                  placeholder="45"
                />
              </div>
              <div>
                <label htmlFor="sell-unit">Per what?</label>
                <input
                  id="sell-unit"
                  maxLength={40}
                  value={listing.unit}
                  onChange={(event) => setListing({ ...listing, unit: event.target.value })}
                  placeholder="per tray / per kg / each"
                />
              </div>
            </div>

            <div className="market-form-row">
              <div>
                <label htmlFor="sell-quantity">How many available? (optional)</label>
                <input
                  id="sell-quantity"
                  maxLength={40}
                  value={listing.quantity}
                  onChange={(event) => setListing({ ...listing, quantity: event.target.value })}
                  placeholder="e.g. 40 trays"
                />
              </div>
              <div>
                <label htmlFor="sell-area">Area</label>
                <input
                  id="sell-area"
                  maxLength={80}
                  value={listing.region}
                  onChange={(event) => setListing({ ...listing, region: event.target.value })}
                  placeholder="e.g. Umlazi, Durban"
                />
              </div>
            </div>

            {problem && <p className="form-error">{problem}</p>}
            <button type="submit" className="button button-primary" disabled={saving}>
              {saving ? 'Posting…' : 'Post listing'}
            </button>
            <p className="market-form-foot">
              No payment is taken here. You and the buyer agree the price and the handover
              between you.
            </p>
          </form>
        )}

        <p className="market-back">
          <button type="button" className="market-inline-link" onClick={() => navigate('/market')}>
            Back to the market
          </button>
        </p>
      </div>
    </main>
  )
}
