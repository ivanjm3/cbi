/**
 * Tests for App shell three-panel layout.
 *
 * Validates:
 * - Three-panel structure (Sidebar, Canvas, StatsPanel)
 * - TopBar present
 * - ChatBar fixed at bottom within canvas area
 * - Stats Panel collapse/expand connected to zustand store
 * - Canvas expands when Stats Panel collapsed
 *
 * Requirements: 1.1, 1.5, 1.6, 1.8
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import App from './App';
import { useSessionStore } from './store/sessionStore';

describe('App shell layout', () => {
  beforeEach(() => {
    // Reset store state between tests
    useSessionStore.setState({ statsPanelCollapsed: false });
  });

  it('renders the TopBar', () => {
    render(<App />);
    expect(screen.getByLabelText('Top bar')).toBeInTheDocument();
  });

  it('renders the Sidebar', () => {
    render(<App />);
    expect(screen.getByLabelText('Sidebar')).toBeInTheDocument();
  });

  it('renders the Canvas', () => {
    render(<App />);
    expect(screen.getByLabelText('Canvas')).toBeInTheDocument();
  });

  it('renders the Stats Panel when expanded', () => {
    render(<App />);
    expect(screen.getByLabelText('Stats panel')).toBeInTheDocument();
    expect(screen.getByLabelText('Stats panel')).not.toHaveAttribute('aria-hidden', 'true');
  });

  it('renders the Chat Bar', () => {
    render(<App />);
    expect(screen.getByLabelText('Chat bar')).toBeInTheDocument();
  });

  it('collapses Stats Panel when toggle is clicked', () => {
    render(<App />);
    const collapseBtn = screen.getByLabelText('Collapse stats panel');
    fireEvent.click(collapseBtn);

    const panel = screen.getByLabelText('Stats panel');
    expect(panel).toHaveAttribute('aria-hidden', 'true');
    expect(panel).toHaveClass('w-0');
  });

  it('shows expand button when Stats Panel is collapsed', () => {
    useSessionStore.setState({ statsPanelCollapsed: true });
    render(<App />);
    expect(screen.getByLabelText('Expand stats panel')).toBeInTheDocument();
  });

  it('expands Stats Panel when expand button is clicked', () => {
    useSessionStore.setState({ statsPanelCollapsed: true });
    render(<App />);

    const expandBtn = screen.getByLabelText('Expand stats panel');
    fireEvent.click(expandBtn);

    const panel = screen.getByLabelText('Stats panel');
    expect(panel).not.toHaveAttribute('aria-hidden', 'true');
    expect(panel).toHaveClass('w-[300px]');
  });

  it('does not show expand button when Stats Panel is visible', () => {
    render(<App />);
    expect(screen.queryByLabelText('Expand stats panel')).not.toBeInTheDocument();
  });

  it('uses full viewport dimensions to prevent overflow', () => {
    render(<App />);
    const root = screen.getByLabelText('Top bar').parentElement;
    expect(root).toHaveClass('h-screen', 'w-screen', 'overflow-hidden');
  });
});
