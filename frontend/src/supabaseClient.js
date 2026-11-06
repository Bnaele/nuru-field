import { createClient } from '@supabase/supabase-js'

// Vite inlines these at build time, so they are strings or undefined -- never a
// runtime lookup. `createClient` throws immediately when either is missing, and
// because this module is imported by App.jsx that throw happens during the very
// first render: the result is a blank white page with the reason only visible in
// the console. The app is supposed to be demoable by someone who has just cloned
// it, so a missing key is handled as a configuration state instead of a crash.
const supabaseUrl = (import.meta.env.VITE_SUPABASE_URL || '').trim()
const supabaseAnonKey = (import.meta.env.VITE_SUPABASE_ANON_KEY || '').trim()

const missing = [
  !supabaseUrl && 'VITE_SUPABASE_URL',
  !supabaseAnonKey && 'VITE_SUPABASE_ANON_KEY',
].filter(Boolean)

/**
 * A human-readable description of what is wrong with the frontend environment,
 * or null when it is complete.
 */
export const configProblem = missing.length
  ? `This build has no Supabase credentials, so sign-in is unavailable. Missing: ${missing.join(', ')}.`
  : null

/** True when the anon key looks like it was pasted into the wrong variable. */
export const looksLikeServiceKey =
  supabaseAnonKey.startsWith('sb_secret_') ||
  supabaseAnonKey.startsWith('service_role')

// Deliberately null rather than a mock client. A fake client that silently
// resolves would let sign-in appear to work and fail later, somewhere less
// obvious. Callers check `supabase` before using it.
export const supabase = configProblem
  ? null
  : createClient(supabaseUrl, supabaseAnonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
      },
    })
