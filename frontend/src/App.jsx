// App — routing, session, and the three features that outlive a page change.
//
// This file used to hold the field-profile fetch, the photo scan, the chat
// conversation and the auth wiring in one component, and every one of those had
// a defect that only made sense once separated (see the hooks for each). What is
// left here is the part that genuinely belongs to the app shell.

import { useCallback, useEffect, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import './App.css'

import Nav from './components/Nav'
import AuthModal from './components/AuthModal'
import ConfigNotice from './components/ConfigNotice'
import HomePage from './pages/HomePage'
import FieldPage from './pages/FieldPage'
import ScanPage from './pages/ScanPage'
import { useAdviserChat } from './hooks/useAdviserChat'
import { useFieldProfile } from './hooks/useFieldProfile'
import { useSoilScan } from './hooks/useSoilScan'
import { setAccessToken } from './lib/api'
import { configProblem, supabase } from './supabaseClient'

export default function App() {
  const [session, setSession] = useState(undefined)

  const field = useFieldProfile()
  const scan = useSoilScan()

  // A stable callback, so the chat hook is not rebuilt on every render and the
  // adviser always sees the latest field summary when it needs it.
  const getFieldContext = useCallback(
    () => field.profile?.summary || '',
    [field.profile],
  )
  const chat = useAdviserChat({ getFieldContext })

  useEffect(() => {
    // Without a client the environment is incomplete. ConfigNotice explains that,
    // and there is no auth state to subscribe to.
    if (!supabase) {
      setSession(null)
      return undefined
    }

    let active = true
    // getSession reads from local storage and rejects if the stored token is
    // corrupt. Unhandled, that rejection leaves the app on "Loading…" forever.
    supabase.auth
      .getSession()
      .then(({ data }) => { if (active) setSession(data.session ?? null) })
      .catch(() => { if (active) setSession(null) })

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, nextSession) => setSession(nextSession),
    )

    return () => {
      active = false
      subscription.unsubscribe()
    }
  }, [])

  // The API client holds the token itself, so no component has to pass it down.
  useEffect(() => {
    setAccessToken(session?.access_token)
  }, [session])

  const handleSignOut = async () => {
    // Clear local state even when the network call fails, otherwise a failed
    // sign-out leaves the user looking signed in with a dead token.
    try {
      await supabase?.auth.signOut()
    } finally {
      setSession(null)
    }
  }

  if (configProblem) {
    return <ConfigNotice problem={configProblem} />
  }

  if (session === undefined) {
    return (
      <main className="auth-page">
        <p className="app-loading" role="status">Loading your session…</p>
      </main>
    )
  }

  const isAuthed = session !== null

  const authedField = (
    <>
      <Nav onSignOut={handleSignOut} />
      <FieldPage
        fieldProfile={field.profile}
        locationStatus={field.status}
        locationTone={field.tone}
        locationLoading={field.loading}
        onUseMyLocation={field.locate}
        onMapPick={field.load}
      />
    </>
  )

  const authedScan = (
    <>
      <Nav onSignOut={handleSignOut} />
      <ScanPage
        scan={scan}
        fieldProfile={field.profile}
        chat={chat}
      />
    </>
  )

  return (
    <Routes>
      <Route path="/" element={<HomePage />} />

      <Route path="/field" element={isAuthed ? authedField : <Navigate to="/login" replace />} />
      <Route path="/scan" element={isAuthed ? authedScan : <Navigate to="/login" replace />} />

      {/* Hero linked to /adviser, which was never a route: it fell through the
          catch-all and silently sent people to the home page. The adviser lives
          on /scan, so that is where the old path now goes. */}
      <Route path="/adviser" element={<Navigate to="/scan" replace />} />

      <Route
        path="/login"
        element={isAuthed ? <Navigate to="/field" replace /> : <AuthModal />}
      />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
