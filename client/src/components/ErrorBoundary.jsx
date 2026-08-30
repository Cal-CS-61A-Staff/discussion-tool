import { Component } from 'react';

// Catches render-time crashes anywhere below it so one broken page shows a
// recoverable message instead of a blank white screen with nothing but a
// console error — React doesn't offer a hook equivalent, only this
// lifecycle pair, hence the lone class component in an otherwise all-hooks
// codebase.
export default class ErrorBoundary extends Component {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    console.error('Unhandled error in the app:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="page-loading">
          <p>Something went wrong loading this page.</p>
          <button type="button" className="btn btn-primary" onClick={() => window.location.reload()}>
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
