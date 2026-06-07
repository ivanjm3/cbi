import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import App from './App';
import { useSessionStore } from './store/sessionStore';

describe('App shell layout', () => {
  beforeEach(() => {
    useSessionStore.setState({
      cards: [],
      activeCardId: null,
      chatThread: [],
      threads: [],
      bookmarks: [],
      statsPanelCollapsed: false,
      loading: false,
      canvasFullNotification: false,
    });
  });

  it('renders the three-panel layout (sidebar, canvas, stats panel)', () => {
    render(<App />);
    expect(screen.getByLabelText('Sidebar navigation')).toBeInTheDocument();
    expect(screen.getByTestId('canvas')).toBeInTheDocument();
    expect(screen.getByLabelText('Statistics Panel')).toBeInTheDocument();
  });

  it('renders the app shell container with flex layout and no overflow', () => {
    render(<App />);
    const shell = screen.getByTestId('app-shell');
    expect(shell).toHaveClass('h-screen', 'w-screen', 'flex', 'overflow-hidden');
  });

  it('sidebar has fixed 260px width', () => {
    render(<App />);
    const sidebar = screen.getByLabelText('Sidebar navigation');
    expect(sidebar).toHaveClass('w-[260px]', 'min-w-[260px]');
  });

  it('canvas has fluid width (flex-1 min-w-0)', () => {
    render(<App />);
    const canvas = screen.getByTestId('canvas');
    expect(canvas).toHaveClass('flex-1', 'min-w-0');
  });

  it('stats panel has 300px width when expanded', () => {
    render(<App />);
    const panel = screen.getByLabelText('Statistics Panel');
    expect(panel).toHaveClass('w-[300px]');
  });

  it('stats panel collapses to w-0 when toggle is clicked', () => {
    render(<App />);
    const toggleBtn = screen.getByLabelText('Collapse stats panel');
    fireEvent.click(toggleBtn);

    const panel = screen.getByLabelText('Statistics Panel');
    expect(panel).toHaveClass('w-0');
  });

  it('stats panel expand toggle restores full width', () => {
    useSessionStore.setState({ statsPanelCollapsed: true });
    render(<App />);

    const toggleBtn = screen.getByLabelText('Expand stats panel');
    fireEvent.click(toggleBtn);

    const panel = screen.getByLabelText('Statistics Panel');
    expect(panel).toHaveClass('w-[300px]');
  });

  it('connects stats panel collapse state to zustand store', () => {
    render(<App />);
    expect(useSessionStore.getState().statsPanelCollapsed).toBe(false);

    const toggleBtn = screen.getByLabelText('Collapse stats panel');
    fireEvent.click(toggleBtn);
    expect(useSessionStore.getState().statsPanelCollapsed).toBe(true);

    const expandBtn = screen.getByLabelText('Expand stats panel');
    fireEvent.click(expandBtn);
    expect(useSessionStore.getState().statsPanelCollapsed).toBe(false);
  });

  it('canvas expands when stats panel is collapsed (flex-1 occupies remaining space)', () => {
    render(<App />);
    const canvas = screen.getByTestId('canvas');
    // Canvas should always have flex-1 min-w-0 so it fills remaining space
    expect(canvas).toHaveClass('flex-1', 'min-w-0');

    // Collapse stats panel
    const toggleBtn = screen.getByLabelText('Collapse stats panel');
    fireEvent.click(toggleBtn);

    // Canvas still has flex-1 and will naturally expand since StatsPanel is w-0
    expect(canvas).toHaveClass('flex-1', 'min-w-0');
    // Verify the stats panel is indeed w-0 now
    const panel = screen.getByLabelText('Statistics Panel');
    expect(panel).toHaveClass('w-0');
  });
});
