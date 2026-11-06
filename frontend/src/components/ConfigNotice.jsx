// Shown instead of the app when the frontend environment is incomplete.
//
// The alternative — what the code used to do — is `createClient(undefined,
// undefined)` throwing during the first render, which produces a blank white page
// with the reason only in the console. A reader who has just cloned the repo
// deserves to be told what is missing and where to put it.

import { looksLikeServiceKey } from '../supabaseClient'

export default function ConfigNotice({ problem }) {
  return (
    <div className="config-notice" role="alert">
      <div className="config-notice-inner">
        <p className="config-notice-kicker">Configuration</p>
        <h1>This build has no database credentials</h1>
        <p>{problem}</p>

        {looksLikeServiceKey && (
          <p className="config-notice-danger">
            <strong>Stop:</strong> the value in <code>VITE_SUPABASE_ANON_KEY</code> looks
            like a <em>service</em> key. Vite inlines this value into the public
            JavaScript bundle, so shipping it would hand every visitor full database
            access. Put the anon key here and the service key in <code>backend/.env</code>.
          </p>
        )}

        <ol className="config-notice-steps">
          <li>
            Copy <code>frontend/.env.example</code> to <code>frontend/.env</code>.
          </li>
          <li>
            Fill in <code>VITE_SUPABASE_URL</code> and{' '}
            <code>VITE_SUPABASE_ANON_KEY</code> from your Supabase project&apos;s
            settings, under API.
          </li>
          <li>
            Restart the dev server — Vite only reads <code>.env</code> at startup.
          </li>
        </ol>

        <p className="config-notice-footnote">
          The API does not need these values. Weather, soil, region, crop matching and
          market prices all run on keyless public sources, so{' '}
          <code>cd backend &amp;&amp; uvicorn main:app --reload</code> works with an empty{' '}
          <code>backend/.env</code>.
        </p>
      </div>
    </div>
  )
}
