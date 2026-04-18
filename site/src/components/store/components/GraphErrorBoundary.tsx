import { Component } from 'react';
import type { ReactNode } from 'react';

export class GraphErrorBoundary extends Component<{ children: ReactNode; fallback?: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };
  static getDerivedStateFromError() { return { hasError: true }; }
  render() {
    if (this.state.hasError) return this.props.fallback || (
      <div className="flex items-center justify-center py-12 text-center">
        <p className="text-[#8a8a8a]">3D graph unavailable on this device.</p>
      </div>
    );
    return this.props.children;
  }
}
