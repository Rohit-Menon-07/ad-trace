import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  /** Changing this key clears a caught error (e.g. a new search or page). */
  resetKey?: unknown;
}

interface State {
  error: Error | null;
  resetKey: unknown;
}

/** A rendering bug must never leave a blank screen: show what failed and how to continue. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, resetKey: this.props.resetKey };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    return props.resetKey !== state.resetKey ? { error: null, resetKey: props.resetKey } : null;
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('UI error', error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="rounded border-2 border-amber-500 bg-amber-50 p-4 text-sm text-amber-950 dark:bg-amber-950/30 dark:text-amber-50">
        <p className="font-semibold">This part of the page failed to display.</p>
        <p className="mt-1">
          The answer was not shown, so nothing on screen should be relied on. Run the search again; if it repeats, use the
          request id in the audit log. Error: <code className="font-mono">{this.state.error.message}</code>
        </p>
      </div>
    );
  }
}
