import { Component, type ReactNode } from 'react'

type Props = {
  panelName: string
  children: ReactNode
}

type State = {
  failed: boolean
}

export default class DashboardErrorBoundary extends Component<Props, State> {
  state: State = { failed: false }

  static getDerivedStateFromError(): State {
    return { failed: true }
  }

  render() {
    if (this.state.failed) {
      return (
        <section role="alert" className="dashboard-panel dashboard-panel-unavailable">
          <h2>{this.props.panelName} unavailable</h2>
          <p>This dashboard panel could not be rendered.</p>
        </section>
      )
    }

    return this.props.children
  }
}
