import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, beforeEach } from 'vitest';
import { Sidebar } from './Sidebar';
import { useSessionStore } from '../store/sessionStore';
import type { ThreadSummary, Bookmark, ChatMessage, CardState } from '../types';

// Reset store state before each test
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

describe('Sidebar', () => {
  it('renders the sidebar with New Chat button, History, and Bookmarks sections', () => {
    render(<Sidebar />);

    expect(screen.getByLabelText('Sidebar navigation')).toBeInTheDocument();
    expect(screen.getByLabelText('Start new chat')).toBeInTheDocument();
    expect(screen.getByText('History')).toBeInTheDocument();
    expect(screen.getByText('Bookmarks')).toBeInTheDocument();
  });

  it('displays empty state messages when there are no threads or bookmarks', () => {
    render(<Sidebar />);

    expect(screen.getByText('No chat history yet')).toBeInTheDocument();
    expect(screen.getByText('No bookmarks saved')).toBeInTheDocument();
  });

  it('displays up to 50 thread history entries most recent first', () => {
    const threads: ThreadSummary[] = Array.from({ length: 55 }, (_, i) => ({
      id: `thread-${i}`,
      firstMessage: `Thread message ${i}`,
      lastActivity: Date.now() - i * 60000,
      messageCount: 1,
    }));

    useSessionStore.setState({ threads });
    render(<Sidebar />);

    // Should only show 50 threads
    expect(screen.getByText('Thread message 0')).toBeInTheDocument();
    expect(screen.getByText('Thread message 49')).toBeInTheDocument();
    expect(screen.queryByText('Thread message 50')).not.toBeInTheDocument();
  });

  it('displays bookmarks with formatted timestamps', () => {
    const now = Date.now();
    const bookmarks: Bookmark[] = [
      {
        id: 'bm-1',
        name: 'Recent session',
        savedAt: now - 2 * 60 * 60 * 1000, // 2 hours ago
        chatThread: [],
        cards: [],
      },
      {
        id: 'bm-2',
        name: 'Old session',
        savedAt: now - 48 * 60 * 60 * 1000, // 2 days ago
        chatThread: [],
        cards: [],
      },
    ];

    useSessionStore.setState({ bookmarks });
    render(<Sidebar />);

    expect(screen.getByText('Recent session')).toBeInTheDocument();
    expect(screen.getByText('Old session')).toBeInTheDocument();
    // Recent bookmark should show relative time
    expect(screen.getByText('2 hours ago')).toBeInTheDocument();
  });

  it('starts a new chat when the New Chat button is clicked', async () => {
    const chatThread: ChatMessage[] = [
      { id: 'msg-1', role: 'user', content: 'hello', timestamp: Date.now() },
    ];
    useSessionStore.setState({ chatThread });

    render(<Sidebar />);

    const user = userEvent.setup();
    await user.click(screen.getByLabelText('Start new chat'));

    const state = useSessionStore.getState();
    expect(state.chatThread).toHaveLength(0);
    expect(state.cards).toHaveLength(0);
  });

  it('shows a confirmation prompt when deleting a bookmark', async () => {
    const bookmarks: Bookmark[] = [
      {
        id: 'bm-1',
        name: 'Test bookmark',
        savedAt: Date.now(),
        chatThread: [],
        cards: [],
      },
    ];

    useSessionStore.setState({ bookmarks });
    render(<Sidebar />);

    const user = userEvent.setup();
    const deleteBtn = screen.getByLabelText('Delete bookmark: Test bookmark');
    await user.click(deleteBtn);

    // Confirmation dialog should appear
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(
      screen.getByText(/Are you sure you want to delete this bookmark/),
    ).toBeInTheDocument();
  });

  it('deletes a bookmark after confirmation', async () => {
    const bookmarks: Bookmark[] = [
      {
        id: 'bm-1',
        name: 'Test bookmark',
        savedAt: Date.now(),
        chatThread: [],
        cards: [],
      },
    ];

    useSessionStore.setState({ bookmarks });
    render(<Sidebar />);

    const user = userEvent.setup();
    await user.click(screen.getByLabelText('Delete bookmark: Test bookmark'));
    await user.click(screen.getByText('Delete'));

    const state = useSessionStore.getState();
    expect(state.bookmarks).toHaveLength(0);
  });

  it('cancels bookmark deletion when Cancel is clicked', async () => {
    const bookmarks: Bookmark[] = [
      {
        id: 'bm-1',
        name: 'Test bookmark',
        savedAt: Date.now(),
        chatThread: [],
        cards: [],
      },
    ];

    useSessionStore.setState({ bookmarks });
    render(<Sidebar />);

    const user = userEvent.setup();
    await user.click(screen.getByLabelText('Delete bookmark: Test bookmark'));
    await user.click(screen.getByText('Cancel'));

    // Dialog should close and bookmark should remain
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    const state = useSessionStore.getState();
    expect(state.bookmarks).toHaveLength(1);
  });
});
