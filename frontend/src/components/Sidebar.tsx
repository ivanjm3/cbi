import { useState, useEffect, useCallback } from 'react';
import { useSessionStore } from '../store/sessionStore';
import { formatTimestamp } from '../utils/formatters';
import type { Bookmark, ThreadSummary } from '../types';

/**
 * NewChatButton: Starts a new chat session.
 */
function NewChatButton() {
  const startNewChat = useSessionStore((s) => s.startNewChat);

  return (
    <button
      onClick={startNewChat}
      className="w-full px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors text-sm font-medium"
      aria-label="Start new chat"
    >
      + New Chat
    </button>
  );
}

/**
 * ThreadItem: A single thread history entry.
 */
function ThreadItem({ thread }: { thread: ThreadSummary }) {
  const loadBookmark = useSessionStore((s) => s.loadBookmark);

  return (
    <li
      className="px-3 py-2 rounded-md hover:bg-gray-100 cursor-pointer text-sm truncate"
      title={thread.firstMessage}
      onClick={() => loadBookmark(thread.id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          loadBookmark(thread.id);
        }
      }}
    >
      <span className="text-gray-800 block truncate">{thread.firstMessage}</span>
      <span className="text-gray-500 text-xs">
        {formatTimestamp(new Date(thread.lastActivity))}
      </span>
    </li>
  );
}

/**
 * ThreadList: Displays up to 50 thread history entries, most recent first.
 */
function ThreadList() {
  const threads = useSessionStore((s) => s.threads);

  if (threads.length === 0) {
    return (
      <div className="px-3 py-2 text-xs text-gray-400 italic">
        No chat history yet
      </div>
    );
  }

  // Threads are already stored most-recent-first; limit to 50
  const displayThreads = threads.slice(0, 50);

  return (
    <ul className="space-y-1" aria-label="Chat thread history">
      {displayThreads.map((thread) => (
        <ThreadItem key={thread.id} thread={thread} />
      ))}
    </ul>
  );
}

/**
 * SaveSessionButton: Prompts user for a name and saves the current session as a bookmark.
 * Handles localStorage quota exceeded errors.
 * Requirements: 8.1, 8.6
 */
function SaveSessionButton() {
  const saveBookmark = useSessionStore((s) => s.saveBookmark);
  const chatThread = useSessionStore((s) => s.chatThread);
  const [showPrompt, setShowPrompt] = useState(false);
  const [name, setName] = useState('');
  const [quotaError, setQuotaError] = useState<string | null>(null);

  // Listen for quota exceeded events from the store's storage adapter
  useEffect(() => {
    const handleQuotaExceeded = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      setQuotaError(
        detail?.message ??
          'Storage quota exceeded. Try deleting older bookmarks to free space.',
      );
    };
    window.addEventListener('storage-quota-exceeded', handleQuotaExceeded);
    return () => {
      window.removeEventListener('storage-quota-exceeded', handleQuotaExceeded);
    };
  }, []);

  const handleSave = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setQuotaError(null);
    saveBookmark(trimmed);
    setName('');
    setShowPrompt(false);
  };

  const handleCancel = () => {
    setName('');
    setShowPrompt(false);
    setQuotaError(null);
  };

  // Only enable save if there's something in the session
  const hasContent = chatThread.length > 0;

  return (
    <>
      <button
        onClick={() => setShowPrompt(true)}
        disabled={!hasContent}
        className="w-full px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 transition-colors text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
        aria-label="Save session"
        title={hasContent ? 'Save current session as bookmark' : 'No session to save'}
      >
        Save Session
      </button>

      {/* Quota exceeded warning banner */}
      {quotaError && (
        <div
          className="mt-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded-md text-xs text-amber-800"
          role="alert"
        >
          <p>{quotaError}</p>
          <button
            onClick={() => setQuotaError(null)}
            className="mt-1 text-amber-600 hover:text-amber-800 underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Save session name prompt */}
      {showPrompt && (
        <div
          className="fixed inset-0 bg-black/30 flex items-center justify-center z-50"
          role="dialog"
          aria-modal="true"
          aria-label="Save session"
        >
          <div className="bg-white rounded-lg shadow-lg p-5 max-w-sm mx-4 w-full">
            <h3 className="text-sm font-medium text-gray-800 mb-3">
              Save Session
            </h3>
            <label className="block text-xs text-gray-600 mb-1" htmlFor="bookmark-name-input">
              Session name (max 100 characters)
            </label>
            <input
              id="bookmark-name-input"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value.slice(0, 100))}
              maxLength={100}
              placeholder="My analysis session"
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSave();
                if (e.key === 'Escape') handleCancel();
              }}
            />
            <div className="text-xs text-gray-400 mt-1 text-right">
              {name.length}/100
            </div>
            <div className="flex justify-end gap-2 mt-3">
              <button
                onClick={handleCancel}
                className="px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 rounded-md"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={!name.trim()}
                className="px-3 py-1.5 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded-md disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/**
 * BookmarkItem: A single bookmark entry with delete functionality.
 * Includes unsaved-changes confirmation before loading.
 * Requirements: 8.3, 8.5
 */
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
    <li className="group flex items-center justify-between px-3 py-2 rounded-md hover:bg-gray-100 text-sm">
      <button
        className="flex-1 text-left truncate"
        onClick={() => onLoad(bookmark.id)}
        title={bookmark.name}
        aria-label={`Load bookmark: ${bookmark.name}`}
      >
        <span className="text-gray-800 block truncate">{bookmark.name}</span>
        <span className="text-gray-500 text-xs">
          {formatTimestamp(new Date(bookmark.savedAt))}
        </span>
      </button>
      <button
        onClick={() => onDelete(bookmark.id)}
        className="ml-2 text-gray-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity p-1"
        aria-label={`Delete bookmark: ${bookmark.name}`}
        title="Delete bookmark"
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

/**
 * BookmarkList: Displays bookmarks with formatted timestamps, delete confirmation,
 * and unsaved-changes confirmation on load.
 * Requirements: 8.3, 8.5
 */
function BookmarkList() {
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

  const handleLoadRequest = useCallback(
    (id: string) => {
      // If chat thread is non-empty, prompt for unsaved changes
      if (chatThread.length > 0) {
        setPendingLoadId(id);
      } else {
        loadBookmark(id);
      }
    },
    [chatThread.length, loadBookmark],
  );

  const confirmLoad = () => {
    if (pendingLoadId) {
      loadBookmark(pendingLoadId);
      setPendingLoadId(null);
    }
  };

  const cancelLoad = () => {
    setPendingLoadId(null);
  };

  if (bookmarks.length === 0) {
    return (
      <div className="px-3 py-2 text-xs text-gray-400 italic">
        No bookmarks saved
      </div>
    );
  }

  // Bookmarks are already stored most-recent-first; limit to 50
  const displayBookmarks = bookmarks.slice(0, 50);

  return (
    <div>
      <ul className="space-y-1" aria-label="Saved bookmarks">
        {displayBookmarks.map((bookmark) => (
          <BookmarkItem
            key={bookmark.id}
            bookmark={bookmark}
            onDelete={handleDeleteRequest}
            onLoad={handleLoadRequest}
          />
        ))}
      </ul>

      {/* Delete confirmation dialog */}
      {pendingDeleteId && (
        <div
          className="fixed inset-0 bg-black/30 flex items-center justify-center z-50"
          role="dialog"
          aria-modal="true"
          aria-label="Confirm bookmark deletion"
        >
          <div className="bg-white rounded-lg shadow-lg p-5 max-w-sm mx-4">
            <p className="text-sm text-gray-700 mb-4">
              Are you sure you want to delete this bookmark? This action cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={cancelDelete}
                className="px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 rounded-md"
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                className="px-3 py-1.5 text-sm text-white bg-red-600 hover:bg-red-700 rounded-md"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Unsaved changes confirmation dialog */}
      {pendingLoadId && (
        <div
          className="fixed inset-0 bg-black/30 flex items-center justify-center z-50"
          role="dialog"
          aria-modal="true"
          aria-label="Confirm loading bookmark"
        >
          <div className="bg-white rounded-lg shadow-lg p-5 max-w-sm mx-4">
            <p className="text-sm text-gray-700 mb-4">
              You have unsaved changes in your current session. Loading this bookmark will replace your current work. Continue?
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={cancelLoad}
                className="px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 rounded-md"
              >
                Cancel
              </button>
              <button
                onClick={confirmLoad}
                className="px-3 py-1.5 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded-md"
              >
                Load Bookmark
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Sidebar: Left navigation panel with new chat button, save session, thread history, and bookmarks.
 * Requirements: 1.2, 8.1, 8.2, 8.3, 8.5, 8.6
 */
export function Sidebar() {
  return (
    <aside
      className="w-[260px] min-w-[260px] h-full flex flex-col border-r border-gray-200 bg-gray-50 overflow-hidden"
      aria-label="Sidebar navigation"
    >
      {/* New Chat + Save Session Buttons */}
      <div className="p-3 border-b border-gray-200 space-y-2">
        <NewChatButton />
        <SaveSessionButton />
      </div>

      {/* Thread History */}
      <div className="flex-1 overflow-y-auto px-1 py-2">
        <h2 className="px-3 py-1 text-xs font-semibold text-gray-500 uppercase tracking-wider">
          History
        </h2>
        <ThreadList />
      </div>

      {/* Bookmarks */}
      <div className="border-t border-gray-200 overflow-y-auto max-h-[40%] px-1 py-2">
        <h2 className="px-3 py-1 text-xs font-semibold text-gray-500 uppercase tracking-wider">
          Bookmarks
        </h2>
        <BookmarkList />
      </div>
    </aside>
  );
}

export default Sidebar;
