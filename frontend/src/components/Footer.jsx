import { Link } from 'react-router-dom';
import Icon from './Icon';

export default function Footer() {
  return (
    <>
      <section className="closing-section">
        <div className="container closing-content">
          <div className="closing-mark"><Icon name="leaf" size={37} /></div>
          <div>
            <h2>Better information. Stronger harvests.</h2>
            <p>Start with your field, then make the next good decision.</p>
          </div>
          {/* Was href="#field". The dashboard lives on /field, not on an anchor of
              the landing page, so the call to action did nothing at all. */}
          <Link className="button button-primary" to="/field">Build my field profile <Icon name="arrow" size={18} /></Link>
        </div>
      </section>
      <footer>
        <div className="container footer-inner">
          <Link className="brand footer-brand" to="/" aria-label="Nuru Field home">
            <span className="brand-mark"><Icon name="leaf" size={20} /></span>
            <span>NURU<span className="brand-sub">FIELD</span></span>
          </Link>
          <p>Made for thoughtful, resilient farming.</p>
          <p className="footer-disclaimer">Guidance is informational. Verify crop, chemical and irrigation decisions with local agricultural professionals.</p>
        </div>
      </footer>
    </>
  );
}