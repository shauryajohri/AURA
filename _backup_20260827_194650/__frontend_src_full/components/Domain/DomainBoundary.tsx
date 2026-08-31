import { Component, type ErrorInfo, type ReactNode } from "react";

// ============================================================================
// A crash in one view should cost you that view, not the whole Domain.
//
// Without this, a single undefined field anywhere in the tree unmounts
// everything and you get a black screen with no explanation. Now the nav, the
// header and the chat keep working, and the failing pane explains itself.
// ============================================================================

interface Props {
  children: ReactNode;
  /** Changing this (e.g. the current section) clears a previous error. */
  resetKey?: string;
}

interface State {
  error: Error | null;
  info: string;
}

export default class DomainBoundary extends Component<Props, State> {
  state: State = { error: null, info: "" };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Keep it in the console too — the stack is what actually helps debugging.
    console.error("[AURA Domain] view crashed:", error, info.componentStack);
    this.setState({ info: (info.componentStack ?? "").split("\n").slice(1, 4).join("\n") });
  }

  componentDidUpdate(prev: Props) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null, info: "" });
    }
  }

  render() {
    const { error, info } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="dcrash">
        <div className="dcrash__icon">⚠</div>
        <h3>This view hit a problem</h3>
        <p>
          The rest of the Domain is fine — switch sections in the rail, or try again.
        </p>
        <pre className="dcrash__msg">{error.message}</pre>
        {info && <pre className="dcrash__stack">{info.trim()}</pre>}
        <div className="dcrash__btns">
          <button onClick={() => this.setState({ error: null, info: "" })}>Try again</button>
          <button
            className="dcrash__reset"
            onClick={() => {
              if (
                confirm(
                  "Reset the Domain's saved layout and project data?\n\n" +
                  "This clears locally stored projects, tasks and notes for the Domain only."
                )
              ) {
                localStorage.removeItem("aura.domain");
                location.reload();
              }
            }}
          >
            Reset Domain data
          </button>
        </div>
      </div>
    );
  }
}
