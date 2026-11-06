// AuthModal — sign in / sign up for Nuru Field.
//
// Three problems fixed in this version:
//   1. Old success message told users to "check your email", but the
//      Supabase project has email confirmation disabled. That confused
//      people. Now we just sign them in immediately on success.
//   2. Supabase returns no error when someone signs up with an email that
//      already exists (security-by-obscurity to prevent account enumeration).
//      The tell is an empty `user.identities` array. We now detect that and
//      nudge the user to sign in instead of leaving them stuck.
//   3. The component used to call an `onAuthenticated` prop that App never
//      passed. A successful sign-in therefore threw a TypeError into the catch
//      block below and reported it as a sign-in failure, while the session was
//      in fact established. App subscribes to Supabase's auth state on its own,
//      so the modal does not need to hand the session anywhere.

import { useState } from 'react';
import { supabase } from '../supabaseClient';
import Icon from './Icon';

// Supabase hands back the browser's own words when it cannot reach its servers:
// "Failed to fetch", or "Load failed" on Safari. Printed verbatim under the form
// that reads as a fault in the app rather than a problem with the connection, so
// the transport-level cases are translated here. Genuine auth messages — a wrong
// password, an unconfirmed address — still come through as they are, because they
// are the ones the person has to act on.
function describeAuthError(failure) {
  const raw = (failure?.message || '').trim();
  const unreachable =
    failure?.name === 'AuthRetryableFetchError' ||
    /failed to fetch|networkerror|load failed|fetch failed|network request failed/i.test(raw);

  if (unreachable) {
    return 'Could not reach the sign-in service. Check your connection and try again.';
  }
  if (/invalid login credentials/i.test(raw)) {
    return 'That email and password do not match an account.';
  }
  if (/email not confirmed/i.test(raw)) {
    return 'Confirm your email address first — the link is in your inbox.';
  }
  if (/rate limit|too many requests/i.test(raw)) {
    return 'Too many attempts. Wait a minute and try again.';
  }
  return raw || 'Something went wrong. Please try again.';
}

export default function AuthModal() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState(false);  // true when the last message was a failure

  // Reset any status when the user edits the fields — avoids stale
  // error messages that confuse them about what they're about to submit.
  const handleEmailChange = (e) => {
    setEmail(e.target.value);
    if (message) { setMessage(''); setError(false); }
  };
  const handlePasswordChange = (e) => {
    setPassword(e.target.value);
    if (message) { setMessage(''); setError(false); }
  };

  const handleSignUp = async () => {
    setLoading(true);
    setMessage('');
    setError(false);
    try {
      const { data, error: signUpError } = await supabase.auth.signUp({ email, password });

      if (signUpError) {
        setMessage(describeAuthError(signUpError));
        setError(true);
        return;
      }

      // Detect the "email already registered" case. Supabase returns a
      // user object with `identities: []` when the address is already
      // in use (to prevent account enumeration). We can't be 100% sure
      // which it is, so the message nudges toward sign-in instead of
      // asserting "already registered".
      const identities = data?.user?.identities;
      if (Array.isArray(identities) && identities.length === 0) {
        setMessage('That email is already registered. Try signing in instead.');
        setError(true);
        return;
      }

      // If Supabase returned a session (which it does when confirmation
      // is disabled), the user is signed in immediately and App's auth-state
      // subscription takes over from here.
      if (data?.session) {
        return;
      }

      // Otherwise confirmation must be enabled — tell them to check email.
      setMessage('Account created. Check your email to confirm, then sign in.');
    } catch (err) {
      // Network-level failure (e.g. cannot reach Supabase).
      setMessage(describeAuthError(err));
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  const handleSignIn = async (e) => {
    e?.preventDefault();
    setLoading(true);
    setMessage('');
    setError(false);
    try {
      const { data, error: signInError } = await supabase.auth.signInWithPassword({ email, password });

      if (signInError) {
        setMessage(describeAuthError(signInError));
        setError(true);
        return;
      }

      if (data?.session) {
        return;
      }
      setMessage('Sign-in succeeded but no session was returned. Try again.');
      setError(true);
    } catch (err) {
      setMessage(describeAuthError(err));
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-shell">
        <section className="auth-intro">
          <div className="auth-intro-top">
            <span className="auth-mini-mark"><Icon name="leaf" size={18} /></span>
            <span>NURU FIELD ADVISER</span>
          </div>
          <div className="auth-intro-copy">
            <p className="auth-kicker">YOUR FIELD, IN FOCUS</p>
            <h1>Grow with a little more certainty.</h1>
            <p>Practical guidance for healthier crops, smarter watering, and better days in the field.</p>
          </div>
          <div className="auth-stats" aria-label="App benefits">
            <span><strong>01</strong> Local insight</span>
            <span><strong>02</strong> Simple decisions</span>
          </div>
        </section>

        <section className="auth-form-panel">
          <div className="auth-form-heading">
            <p className="auth-kicker">WELCOME BACK</p>
            <h2>Enter your field notes.</h2>
            <p>Sign in to continue your growing journey.</p>
          </div>

          <form className="auth-form" onSubmit={handleSignIn}>
            <label htmlFor="auth-email">Email address</label>
            <input
              id="auth-email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={handleEmailChange}
              autoComplete="email"
              required
            />

            <label htmlFor="auth-password">Password</label>
            <input
              id="auth-password"
              type="password"
              placeholder="Enter your password"
              value={password}
              onChange={handlePasswordChange}
              autoComplete="current-password"
              required
            />

            <button className="auth-submit button button-dark" type="submit" disabled={loading}>
              {loading ? 'Working…' : 'Sign in'}
              {!loading && <Icon name="arrow" size={17} />}
            </button>

            <button className="auth-signup" type="button" onClick={handleSignUp} disabled={loading}>
              New here? <strong>Create an account</strong>
            </button>
          </form>

          {message && (
            <p className={`auth-message ${error ? 'auth-error' : 'auth-success'}`} role="status">
              {message}
            </p>
          )}
        </section>
      </div>
    </div>
  );
}