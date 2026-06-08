/**
 * Sidebar component with NewChatButton, ThreadList, and BookmarkList.
 *
 * - Displays up to 50 thread history entries (most recent first)
 * - Displays bookmarks with formatted timestamps (relative <24h, absolute otherwise)
 * - Bookmark delete with confirmation prompt
 * - Independent scroll for threads and bookmarks sections
 * - On narrow screens (<1024px), collapses to a top bar with hamburger toggle
 *
 * Requirements: 1.2, 1.5, 1.6, 8.2, 8.5
 */

import { useState } from 'react';
import { useSessionStore } from '../store/sessionStore';
import { formatTimestamp } from '../utils/formatters';
import type { ThreadSummary, Bookmark } from '../types';

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function NewChatButton() {
  const startNewChat = useSessionStore((s) => s.startNewChat);

  return (
    <button
      type="button"
      onClick={startNewChat}
      className="w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:bg-blue-500 dark:hover:bg-blue-600"
      aria-label="New Chat"
    >
      + New Chat
    </button>
  );
}

function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + '…';
}

function ThreadItem({ thread }: { thread: ThreadSummary }) {
  return (
    <li className="rounded-md px-3 py-2 text-sm hover:bg-gray-200 dark:hover:bg-gray-700 cursor-pointer">
      <p className="truncate font-medium text-gray-800 dark:text-gray-200">
        {truncate(thread.firstMessage, 30)}
      </p>
      <p className="text-xs text-gray-500 dark:text-gray-400">
        {formatTimestamp(thread.lastActivity)}
      </p>
    </li>
  );
}

function ThreadList({ threads }: { threads: ThreadSummary[] }) {
  if (threads.length === 0) {
    return (
      <p className="px-3 py-2 text-xs text-gray-400 dark:text-gray-500">
        No chat history yet.
      </p>
    );
  }

  return (
    <ul className="space-y-1" role="list" aria-label="Chat history">
      {threads.slice(0, 50).map((thread) => (
        <ThreadItem key={thread.id} thread={thread} />
      ))}
    </ul>
  );
}

function BookmarkItem({
  bookmark,
  onDelete,
  onLoad,
}: {
  bookmark: Bookmark;
  onDelete: (id: string) => void;
  onLoad: (id: string) => void;
}) {
  return (
    <li className="group flex items-center justify-between rounded-md px-3 py-2 text-sm hover:bg-gray-200 dark:hover:bg-gray-700">
      <button
        type="button"
        onClick={() => onLoad(bookmark.id)}
        className="flex-1 min-w-0 text-left cursor-pointer"
        aria-label={`Load bookmark ${bookmark.name}`}
      >
        <p className="truncate font-medium text-gray-800 dark:text-gray-200">
          {bookmark.name}
        </p>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {formatTimestamp(bookmark.savedAt)}
        </p>
      </button>
      <button
        type="button"
        onClick={() => onDelete(bookmark.id)}
        className="ml-2 hidden rounded p-1 text-gray-400 hover:bg-red-100 hover:text-red-600 group-hover:block dark:hover:bg-red-900 dark:hover:text-red-400"
        aria-label={`Delete bookmark ${bookmark.name}`}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-4 w-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
          />
        </svg>
      </button>
    </li>
  );
}

function BookmarkList({
  bookmarks,
  onDelete,
  onLoad,
}: {
  bookmarks: Bookmark[];
  onDelete: (id: string) => void;
  onLoad: (id: string) => void;
}) {
  if (bookmarks.length === 0) {
    return (
      <p className="px-3 py-2 text-xs text-gray-400 dark:text-gray-500">
        No bookmarks saved.
      </p>
    );
  }

  return (
    <ul className="space-y-1" role="list" aria-label="Bookmarks">
      {bookmarks.slice(0, 50).map((bookmark) => (
        <BookmarkItem key={bookmark.id} bookmark={bookmark} onDelete={onDelete} onLoad={onLoad} />
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Sidebar Content (shared between desktop and mobile overlay)
// ---------------------------------------------------------------------------

function SidebarContent({ onClose }: { onClose?: () => void }) {
  const threads = useSessionStore((s) => s.threads);
  const bookmarks = useSessionStore((s) => s.bookmarks);
  const chatThread = useSessionStore((s) => s.chatThread);
  const deleteBookmark = useSessionStore((s) => s.deleteBookmark);
  const loadBookmark = useSessionStore((s) => s.loadBookmark);

  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [pendingLoadId, setPendingLoadId] = useState<string | null>(null);

  const handleDeleteRequest = (id: string) => {
    setPendingDeleteId(id);
  };

  const confirmDelete = () => {
    if (pendingDeleteId) {
      deleteBookmark(pendingDeleteId);
      setPendingDeleteId(null);
    }
  };

  const cancelDelete = () => {
    setPendingDeleteId(null);
  };

  // Bookmark load with unsaved-changes confirmation
  const handleLoadRequest = (id: string) => {
    // If there are unsaved changes (non-empty chat thread), prompt confirmation
    if (chatThread.length > 0) {
      setPendingLoadId(id);
    } else {
      loadBookmark(id);
    }
  };

  const confirmLoad = () => {
    if (pendingLoadId) {
      loadBookmark(pendingLoadId);
      setPendingLoadId(null);
    }
  };

  const cancelLoad = () => {
    setPendingLoadId(null);
  };

  const pendingBookmark = pendingDeleteId
    ? bookmarks.find((b) => b.id === pendingDeleteId)
    : null;

  const pendingLoadBookmark = pendingLoadId
    ? bookmarks.find((b) => b.id === pendingLoadId)
    : null;

  return (
    <>
      {/* New Chat Button */}
      <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
        <div className="flex-1">
          <NewChatButton />
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="ml-3 rounded p-1.5 text-gray-500 hover:bg-gray-200 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-200 lg:hidden"
            aria-label="Close sidebar"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-5 w-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>

      {/* Thread History */}
      <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
        <div className="flex-1 min-h-0 overflow-y-auto px-2 py-3">
          <h2 className="px-3 pb-2 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
            Chat History
          </h2>
          <ThreadList threads={threads} />
        </div>

        {/* Bookmarks */}
        <div className="flex-1 min-h-0 overflow-y-auto border-t border-gray-200 dark:border-gray-700 px-2 py-3">
          <h2 className="px-3 pb-2 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
            Bookmarks
          </h2>
          <BookmarkList bookmarks={bookmarks} onDelete={handleDeleteRequest} onLoad={handleLoadRequest} />
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {pendingDeleteId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          role="dialog"
          aria-modal="true"
          aria-label="Confirm bookmark deletion"
        >
          <div className="mx-4 w-full max-w-sm rounded-lg bg-white p-6 shadow-xl dark:bg-gray-800">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Delete Bookmark
            </h3>
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
              Are you sure you want to delete{' '}
              <span className="font-medium">
                &ldquo;{pendingBookmark?.name ?? 'this bookmark'}&rdquo;
              </span>
              ? This action cannot be undone.
            </p>
            <div className="mt-4 flex justify-end gap-3">
              <button
                type="button"
                onClick={cancelDelete}
                className="rounded-md px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDelete}
                className="rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Load Confirmation Modal (unsaved changes warning) */}
      {pendingLoadId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          role="dialog"
          aria-modal="true"
          aria-label="Confirm loading bookmark"
        >
          <div className="mx-4 w-full max-w-sm rounded-lg bg-white p-6 shadow-xl dark:bg-gray-800">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Load Bookmark
            </h3>
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
              You have unsaved changes in your current session. Loading{' '}
              <span className="font-medium">
                &ldquo;{pendingLoadBookmark?.name ?? 'this bookmark'}&rdquo;
              </span>{' '}
              will replace your current work. Continue?
            </p>
            <div className="mt-4 flex justify-end gap-3">
              <button
                type="button"
                onClick={cancelLoad}
                className="rounded-md px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmLoad}
                className="rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                Load
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Main Sidebar (exported)
// ---------------------------------------------------------------------------

export function Sidebar() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <>
      {/* Desktop Sidebar — hidden below 1024px */}
      <aside
        className="hidden lg:flex h-full w-[260px] min-w-[260px] border-r border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-900 flex-col"
        aria-label="Sidebar"
      >
        <SidebarContent />
      </aside>

      {/* Mobile Top Bar — shown below 1024px */}
      <div
        className="lg:hidden flex items-center justify-between border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 px-4 py-2 min-h-[44px]"
        aria-label="Sidebar toggle"
      >
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          className="flex items-center gap-2 rounded p-2 text-gray-700 hover:bg-gray-200 dark:text-gray-300 dark:hover:bg-gray-700 min-w-[44px] min-h-[44px] justify-center"
          aria-label="Open sidebar menu"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-5 w-5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
          <span className="text-sm font-medium">Menu</span>
        </button>
      </div>

      {/* Mobile Sidebar Overlay — shown when toggled on narrow screens */}
      {mobileOpen && (
        <div className="lg:hidden fixed inset-0 z-40 flex">
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/40"
            onClick={() => setMobileOpen(false)}
            aria-hidden="true"
          />
          {/* Sidebar panel */}
          <aside
            className="relative z-50 flex h-full w-[280px] max-w-[80vw] flex-col bg-gray-50 dark:bg-gray-900 shadow-xl"
            aria-label="Sidebar menu"
          >
            <SidebarContent onClose={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}
    </>
  );
}
