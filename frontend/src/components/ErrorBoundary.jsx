// ErrorBoundary — keeps a rendering failure inside the section that threw.
//
// Without one, a component that throws during render unmounts the entire React
// tree: the user gets a blank white page with the reason only in the console, on
// a screen where every other card may have loaded fine. That is the same failure
// mode the boot-time config guard exists to prevent, one layer further in.
//
// The boundary is deliberately dumb: it names the section, offers a retry that
// remounts the subtree, and stays out of the way otherwise. It does not try to
// interpret the error, because a stack trace with no source map is not useful to
// a grower standing in a field.

import { Component } from 'react'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { failed: false }
  }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error, info) {
    // Still reported, so a developer with the console open sees what happened.
    console.error(`[Nuru] ${this.props.section || 'section'} failed to render`, error, info)
  }

  render() {
    if (!this.state.failed) return this.props.children

    const { section = 'This section' } = this.props

    return (
      <div className="container">
        <div className="card-error card render-failure" role="alert">
          <strong>{section} could not be displayed.</strong>
          <p>
            Something in the data for this screen did not match what the interface
            expected. Nothing else on the page is affected.
          </p>
          <button
            type="button"
            className="button button-dark"
            onClick={() => this.setState({ failed: false })}
          >
            Try again
          </button>
        </div>
      </div>
    )
  }
}
