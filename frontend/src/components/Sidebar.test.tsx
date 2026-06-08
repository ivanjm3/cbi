/**
 * Unit tests for the Sidebar component.
 *
 * Requirements: 1.2, 8.2, 8.5
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { Sidebar } from './Sidebar';
import { useSessionStore } from '../store/sessionStore';
import type { ThreadSummary, Bookmark } from '../types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createThread(overrides: Partial<ThreadSummary> = {}): ThreadSummary {
  return {
    id: crypto.randomUUID(),
    firstMessage: 'Show revenue by quarter for 2024',
    lastActivity: Date.now() - 60_000, // 1 minute ago
    messageCount: 3,
    ...overrides,
  };
}

function createBookmark(overrides: Partial<Bookmark> = {}): Bookmark {
  return {
    id: crypto.randomUUID(),
    name: 'Q4 Analysis',
    savedAt: Date.now() - 3600_000, // 1 hour ago
    chatThread: [],
    cards: [],
    workspaceName: 'Test Workspace',
    ...overrides,
  };
}

// Reset store before each test
beforeEach(() => {
  useSessionStore.setState({
    threads: [],
    bookmarks: [],
    chatThread: [],
    cards: [],
    activeCardId: null,
    statsPanelCollapsed: false,
    loading: false,
    workspaceName: 'Untitled Workspace',
  });
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Sidebar', () => {
  it('renders with correct aria-label', () => {
    render(<Sidebar />);
    expect(screen.getByRole('complementary', { name: 'Sidebar' })).toBeInTheDocument();
  });

  it('renders the New Chat button', () => {
    render(<Sidebar />);
    expect(screen.getByRole('button', { name: 'New Chat' })).toBeInTheDocument();
  });

  it('displays Chat History and Bookmarks section headings', () => {
    render(<Sidebar />);
    expect(screen.getByText('Chat History')).toBeInTheDocument();
    expect(screen.getByText('Bookmarks')).toBeInTheDocument();
  });

  it('shows empty state messages when no threads or bookmarks', () => {
    render(<Sidebar />);
    expect(screen.getByText('No chat history yet.')).toBeInTheDocument();
    expect(screen.getByText('No bookmarks saved.')).toBeInTheDocument();
  });
});

describe('Sidebar - New Chat Button', () => {
  it('calls startNewChat and clears the chat thread', async () => {
    const user = userEvent.setup();
    useSessionStore.setState({
      chatThread: [
        { id: '1', role: 'user' as const, content: 'test query', timestamp: Date.now() },
      ],
      cards: [],
      threads: [],
    });

    render(<Sidebar />);
    await user.click(screen.getByRole('button', { name: 'New Chat' }));

    // After clicking, startNewChat clears chatThread and saves thread summary
    const state = useSessionStore.getState();
    expect(state.chatThread).toHaveLength(0);
    // The previous thread should be saved to threads
    expect(state.threads).toHaveLength(1);
    expect(state.threads[0].firstMessage).toBe('test query');
  });
});

describe('Sidebar - ThreadList', () => {
  it('displays thread entries with truncated first message (30 chars + ellipsis)', () => {
    const longMessage = 'Show me the total revenue by region for 2024 fiscal year';
    useSessionStore.setState({
      threads: [createThread({ firstMessage: longMessage })],
    });

    render(<Sidebar />);
    // Should truncate to 30 chars + ellipsis
    const expected = longMessage.slice(0, 30) + '…';
    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it('does not add ellipsis for messages shorter than 30 chars', () => {
    useSessionStore.setState({
      threads: [createThread({ firstMessage: 'Short message' })],
    });

    render(<Sidebar />);
    expect(screen.getByText('Short message')).toBeInTheDocument();
  });

  it('displays up to 50 threads', () => {
    const threads = Array.from({ length: 55 }, (_, i) =>
      createThread({ id: `thread-${i}`, firstMessage: `Thread ${i}` }),
    );
    useSessionStore.setState({ threads });

    render(<Sidebar />);
    const list = screen.getByRole('list', { name: 'Chat history' });
    const items = within(list).getAllByRole('listitem');
    expect(items.length).toBe(50);
  });

  it('shows relative timestamps for recent threads', () => {
    useSessionStore.setState({
      threads: [createThread({ lastActivity: Date.now() - 120_000 })], // 2 min ago
    });

    render(<Sidebar />);
    expect(screen.getByText('2 minutes ago')).toBeInTheDocument();
  });
});

describe('Sidebar - BookmarkList', () => {
  it('displays bookmark names and formatted timestamps', () => {
    useSessionStore.setState({
      bookmarks: [createBookmark({ name: 'Revenue Analysis', savedAt: Date.now() - 7200_000 })],
    });

    render(<Sidebar />);
    expect(screen.getByText('Revenue Analysis')).toBeInTheDocument();
    expect(screen.getByText('2 hours ago')).toBeInTheDocument();
  });

  it('displays absolute timestamp for bookmarks older than 24h', () => {
    const oldDate = new Date(2024, 5, 15, 14, 30); // June 15, 2024, 14:30
    useSessionStore.setState({
      bookmarks: [createBookmark({ savedAt: oldDate.getTime() })],
    });

    render(<Sidebar />);
    expect(screen.getByText('2024-06-15 14:30')).toBeInTheDocument();
  });

  it('shows delete confirmation when delete button clicked', async () => {
    const user = userEvent.setup();
    useSessionStore.setState({
      bookmarks: [createBookmark({ name: 'My Bookmark' })],
    });

    render(<Sidebar />);
    const deleteBtn = screen.getByRole('button', { name: 'Delete bookmark My Bookmark' });
    await user.click(deleteBtn);

    // Confirmation dialog should appear
    const dialog = screen.getByRole('dialog', { name: 'Confirm bookmark deletion' });
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByText(/Are you sure you want to delete/)).toBeInTheDocument();
    expect(within(dialog).getByText('Delete Bookmark')).toBeInTheDocument();
  });

  it('deletes bookmark when confirmed', async () => {
    const user = userEvent.setup();
    const bookmarkId = 'bm-1';
    useSessionStore.setState({
      bookmarks: [createBookmark({ id: bookmarkId, name: 'Delete Me' })],
    });

    render(<Sidebar />);
    await user.click(screen.getByRole('button', { name: 'Delete bookmark Delete Me' }));
    await user.click(screen.getByRole('button', { name: 'Delete' }));

    // Bookmark should be removed
    const state = useSessionStore.getState();
    expect(state.bookmarks).toHaveLength(0);
  });

  it('cancels bookmark deletion', async () => {
    const user = userEvent.setup();
    useSessionStore.setState({
      bookmarks: [createBookmark({ name: 'Keep Me' })],
    });

    render(<Sidebar />);
    await user.click(screen.getByRole('button', { name: 'Delete bookmark Keep Me' }));
    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    // Dialog should be gone, bookmark still exists
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    const state = useSessionStore.getState();
    expect(state.bookmarks).toHaveLength(1);
  });

  it('displays up to 50 bookmarks', () => {
    const bookmarks = Array.from({ length: 55 }, (_, i) =>
      createBookmark({ id: `bm-${i}`, name: `Bookmark ${i}` }),
    );
    useSessionStore.setState({ bookmarks });

    render(<Sidebar />);
    const list = screen.getByRole('list', { name: 'Bookmarks' });
    const items = within(list).getAllByRole('listitem');
    expect(items.length).toBe(50);
  });
});
