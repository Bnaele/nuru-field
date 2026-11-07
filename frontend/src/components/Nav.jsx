// Nav — the top navigation bar. Shown on all authed pages.
//
// Three links: "Your field" (conditions, crops, prices, plants),
// "Scan & Adviser" (observe and respond) and "Market" (buy supplies, sell a
// harvest). Messages hang off the market rather than the bar: a thread only
// exists because of a listing.
//
// NavLink automatically applies an "active" class to whichever route is
// current, so we can style the active link without any state. Market's
// sub-pages (/sell, /inbox) highlight it too, so a seller is never left
// wondering which part of the app they are in.

import { NavLink, Link, useLocation } from 'react-router-dom'
import Icon from './Icon'

export default function Nav({ onSignOut }) {
  const { pathname } = useLocation()
  // NavLink only knows about its own path, so /sell and /inbox - which are the
  // market's own pages - would leave every tab unhighlighted and the buyer
  // unsure where they are. One prefix test fixes that.
  const inMarket = ['/market', '/sell', '/inbox'].some((path) => pathname.startsWith(path))

  return (
    <nav className="app-nav">
      <div className="container app-nav-inner">
        <Link to="/field" className="app-nav-brand" aria-label="Nuru Field dashboard">
          <span className="brand-mark"><Icon name="leaf" size={20} /></span>
          <span>NURU<span className="brand-sub">FIELD</span></span>
        </Link>

        <div className="app-nav-links">
          <NavLink
            to="/field"
            className={({ isActive }) => 'app-nav-link' + (isActive ? ' active' : '')}
          >
            Your field
          </NavLink>
          <NavLink
            to="/scan"
            className={({ isActive }) => 'app-nav-link' + (isActive ? ' active' : '')}
          >
            Scan &amp; Adviser
          </NavLink>
          <NavLink
            to="/market"
            className={'app-nav-link' + (inMarket ? ' active' : '')}
          >
            Market
          </NavLink>
        </div>

        <button type="button" className="app-nav-signout" onClick={onSignOut} aria-label="Sign out of Nuru Field">
          Sign out
        </button>
      </div>
    </nav>
  )
}