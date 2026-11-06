// HomePage — the public landing page.
// Anyone (authed or not) can see this. The hero explains the product
// and its CTAs push the user toward /field (which requires auth).

import Hero from '../components/Hero'
import Footer from '../components/Footer'

export default function HomePage() {
  return (
    <>
      <Hero />
      <Footer />
    </>
  )
}
