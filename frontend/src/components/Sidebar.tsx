/**
 * Collapsible Sidebar component.
 *
 * Expanded (260px): collapse toggle, "New Chat" button, scrollable chat history
 * (up to 50 entries, most recent first), "Saved Prompts" section, and
 * "Schedulability" disabled placeholder.
 *
 * Collapsed (48px icon rail): icons only for New Chat, History, Saved Prompts,
 * and Schedulability.
 *
 * Dark sidebar background (bg-sidebar: #1e293b) with light text (text-inverse).
 * Animate between states with CSS transitions.
 *
 * Requirements: 1.2, 1.3, 1.4, 8.2, 8.3, 8.5, 12.1, 12.2, 12.3, 12.4
 */

import { useState } from 'react';
import { useSessionStore } from '../store/sessionStore';
import { formatTimestamp } from '../utils/formatters';
import type { SavedPrompt, ThreadSummary } from '../types';

// ---------------------------------------------------------------------------
// Icons (inline SVGs)
// ---------------------------------------------------------------------------

function CollapseIcon({ collapsed }: { collapsed: boolean }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className={`h-5 w-5 transition-transform duration-200 ${collapsed ? 'rotate-180' : ''}`}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={1.5}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
    </svg>
  );
}

function NewChatIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
    </svg>
  );
}

function HistoryIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function SavedPromptsIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M17.593 3.322c1.1.128 1.907 1.077 1.907 2.185V21L12 17.25 4.5 21V5.507c0-1.108.806-2.057 1.907-2.185a48.507 48.507 0 0111.186 0z" />
    </svg>
  );
}

function ScheduleIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
    </svg>
  );
}

function DeleteIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ThreadHistoryItem({ thread }: { thread: ThreadSummary }) {
  return (
    <li className="rounded px-3 py-2 text-sm hover:bg-white/10 cursor-pointer transition-colors duration-100">
      <p className="truncate text-text-inverse font-medium text-sm">
        {thread.firstMessage.length > 35
          ? thread.firstMessage.slice(0, 35) + '…'
          : thread.firstMessage}
      </p>
      <p className="text-xs text-text-inverse/60 mt-0.5">
        {formatTimestamp(thread.lastActivity)}
      </p>
    </li>
  );
}

function SavedPromptItem({
  prompt,
  onDelete,
  onLoad,
}: {
  prompt: SavedPrompt;
  onDelete: (id: string) => void;
  onLoad: (id: string) => void;
}) {
  return (
    <li className="group flex items-center justify-between rounded px-3 py-2 text-sm hover:bg-white/10 transition-colors duration-100">
      <button
        type="button"
        onClick={() => onLoad(prompt.id)}
        className="flex-1 min-w-0 text-left cursor-pointer"
        aria-label={`Load saved prompt: ${prompt.name}`}
      >
        <p className="truncate text-text-inverse font-medium text-sm">
          {prompt.name}
        </p>
        <p className="text-xs text-text-inverse/60 mt-0.5">
          {formatTimestamp(prompt.savedAt)}
        </p>
      </button>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onDelete(prompt.id);
        }}
        className="ml-2 hidden rounded p-1 text-text-inverse/40 hover:bg-white/10 hover:text-red-400 group-hover:block"
        aria-label={`Delete saved prompt: ${prompt.name}`}
      >
        <DeleteIcon />
      </button>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Main Sidebar
// ---------------------------------------------------------------------------

export function Sidebar() {
  const sidebarCollapsed = useSessionStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useSessionStore((s) => s.toggleSidebar);
  const startNewChat = useSessionStore((s) => s.startNewChat);
  const chatHistory = useSessionStore((s) => s.chatHistory);
  const savedPrompts = useSessionStore((s) => s.savedPrompts);
  const chatThread = useSessionStore((s) => s.chatThread);
  const loadSavedPrompt = useSessionStore((s) => s.loadSavedPrompt);
  const deleteSavedPrompt = useSessionStore((s) => s.deleteSavedPrompt);

  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [pendingLoadId, setPendingLoadId] = useState<string | null>(null);
  const [schedulabilityTooltip, setSchedulabilityTooltip] = useState(false);

  // Delete confirmation
  const handleDeleteRequest = (id: string) => {
    setPendingDeleteId(id);
  };

  const confirmDelete = () => {
    if (pendingDeleteId) {
      deleteSavedPrompt(pendingDeleteId);
      setPendingDeleteId(null);
    }
  };

  const cancelDelete = () => {
    setPendingDeleteId(null);
  };

  // Load with unsaved-changes confirmation
  const handleLoadRequest = (id: string) => {
    if (chatThread.length > 0) {
      setPendingLoadId(id);
    } else {
      loadSavedPrompt(id);
    }
  };

  const confirmLoad = () => {
    if (pendingLoadId) {
      loadSavedPrompt(pendingLoadId);
      setPendingLoadId(null);
    }
  };

  const cancelLoad = () => {
    setPendingLoadId(null);
  };

  const pendingPrompt = pendingDeleteId
    ? savedPrompts.find((p) => p.id === pendingDeleteId)
    : null;

  const pendingLoadPrompt = pendingLoadId
    ? savedPrompts.find((p) => p.id === pendingLoadId)
    : null;

  // -------------------------------------------------------------------------
  // Collapsed state: 48px icon rail
  // -------------------------------------------------------------------------

  if (sidebarCollapsed) {
    return (
      <aside
        className="flex h-full w-[48px] min-w-[48px] flex-col items-center bg-bg-sidebar py-3 gap-4 shadow-sidebar transition-all duration-200"
        aria-label="Sidebar collapsed"
      >
        {/* Expand toggle */}
        <button
          type="button"
          onClick={toggleSidebar}
          className="rounded p-2 text-text-inverse/70 hover:bg-white/10 hover:text-text-inverse transition-colors"
          aria-label="Expand sidebar"
        >
          <CollapseIcon collapsed={true} />
        </button>

        {/* New Chat */}
        <button
          type="button"
          onClick={startNewChat}
          className="rounded p-2 text-text-inverse/70 hover:bg-white/10 hover:text-text-inverse transition-colors"
          aria-label="New Chat"
          title="New Chat"
        >
          <NewChatIcon />
        </button>

        {/* History */}
        <div
          className="rounded p-2 text-text-inverse/70"
          aria-label="Chat history"
          title="Chat History"
        >
          <HistoryIcon />
        </div>

        {/* Saved Prompts */}
        <div
          className="rounded p-2 text-text-inverse/70"
          aria-label="Saved prompts"
          title="Saved Prompts"
        >
          <SavedPromptsIcon />
        </div>

        {/* Schedulability (disabled) */}
        <div
          className="rounded p-2 text-text-inverse/30 opacity-50 cursor-not-allowed"
          aria-label="Scheduled Reports"
          title="Coming soon — schedule recurring queries and reports"
        >
          <ScheduleIcon />
        </div>
      </aside>
    );
  }

  // -------------------------------------------------------------------------
  // Expanded state: 260px full sidebar
  // -------------------------------------------------------------------------

  return (
    <>
      <aside
        className="flex h-full w-[260px] min-w-[260px] flex-col bg-bg-sidebar shadow-sidebar transition-all duration-200"
        aria-label="Sidebar"
      >
        {/* Header: Collapse toggle + New Chat */}
        <div className="flex items-center justify-between px-3 py-3 border-b border-white/10">
          <button
            type="button"
            onClick={startNewChat}
            className="flex items-center gap-2 rounded-md bg-accent-primary px-3 py-2 text-sm font-medium text-white hover:bg-accent-hover transition-colors"
            aria-label="New Chat"
          >
            <NewChatIcon />
            <span>New Chat</span>
          </button>
          <button
            type="button"
            onClick={toggleSidebar}
            className="rounded p-2 text-text-inverse/70 hover:bg-white/10 hover:text-text-inverse transition-colors"
            aria-label="Collapse sidebar"
          >
            <CollapseIcon collapsed={false} />
          </button>
        </div>

        {/* Scrollable content */}
        <div className="flex flex-1 min-h-0 flex-col overflow-hidden">
          {/* Chat History */}
          <div className="flex-1 min-h-0 overflow-y-auto px-2 py-3">
            <h2 className="flex items-center gap-2 px-3 pb-2 text-xs font-semibold uppercase tracking-wider text-text-inverse/50">
              <HistoryIcon />
              Chat History
            </h2>
            {chatHistory.length === 0 ? (
              <p className="px-3 py-2 text-xs text-text-inverse/40">
                No chat history yet.
              </p>
            ) : (
              <ul className="space-y-0.5" role="list" aria-label="Chat history list">
                {chatHistory.slice(0, 50).map((thread) => (
                  <ThreadHistoryItem key={thread.id} thread={thread} />
                ))}
              </ul>
            )}
          </div>

          {/* Saved Prompts */}
          <div className="flex-1 min-h-0 overflow-y-auto border-t border-white/10 px-2 py-3">
            <h2 className="flex items-center gap-2 px-3 pb-2 text-xs font-semibold uppercase tracking-wider text-text-inverse/50">
              <SavedPromptsIcon />
              Saved Prompts
            </h2>
            {savedPrompts.length === 0 ? (
              <p className="px-3 py-2 text-xs text-text-inverse/40">
                No saved prompts.
              </p>
            ) : (
              <ul className="space-y-0.5" role="list" aria-label="Saved prompts list">
                {savedPrompts.slice(0, 50).map((prompt) => (
                  <SavedPromptItem
                    key={prompt.id}
                    prompt={prompt}
                    onDelete={handleDeleteRequest}
                    onLoad={handleLoadRequest}
                  />
                ))}
              </ul>
            )}
          </div>

          {/* Schedulability (disabled placeholder) */}
          <div className="border-t border-white/10 px-2 py-3">
            <button
              type="button"
              className="flex w-full items-center gap-2 rounded px-3 py-2 text-text-inverse/30 opacity-50 cursor-not-allowed relative"
              aria-label="Scheduled Reports"
              onClick={() => setSchedulabilityTooltip(true)}
              onMouseEnter={() => setSchedulabilityTooltip(true)}
              onMouseLeave={() => setSchedulabilityTooltip(false)}
            >
              <ScheduleIcon />
              <span className="text-sm">Scheduled Reports</span>
            </button>
            {schedulabilityTooltip && (
              <p className="mx-3 mt-1 rounded bg-white/10 px-2 py-1 text-xs text-text-inverse/70">
                Coming soon — schedule recurring queries and reports
              </p>
            )}
          </div>
        </div>
      </aside>

      {/* Delete Confirmation Modal */}
      {pendingDeleteId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          role="dialog"
          aria-modal="true"
          aria-label="Confirm saved prompt deletion"
        >
          <div className="mx-4 w-full max-w-sm rounded-lg bg-bg-secondary p-6 shadow-panel">
            <h3 className="text-sm font-semibold text-text-primary">
              Delete Saved Prompt
            </h3>
            <p className="mt-2 text-sm text-text-secondary">
              Are you sure you want to delete{' '}
              <span className="font-medium">
                &ldquo;{pendingPrompt?.name ?? 'this prompt'}&rdquo;
              </span>
              ? This action cannot be undone.
            </p>
            <div className="mt-4 flex justify-end gap-3">
              <button
                type="button"
                onClick={cancelDelete}
                className="rounded-md px-3 py-2 text-sm font-medium text-text-secondary hover:bg-bg-input"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDelete}
                className="rounded-md bg-status-error px-3 py-2 text-sm font-medium text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-status-error"
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
          aria-label="Confirm loading saved prompt"
        >
          <div className="mx-4 w-full max-w-sm rounded-lg bg-bg-secondary p-6 shadow-panel">
            <h3 className="text-sm font-semibold text-text-primary">
              Load Saved Prompt
            </h3>
            <p className="mt-2 text-sm text-text-secondary">
              You have unsaved changes in your current session. Loading{' '}
              <span className="font-medium">
                &ldquo;{pendingLoadPrompt?.name ?? 'this prompt'}&rdquo;
              </span>{' '}
              will replace your current work. Continue?
            </p>
            <div className="mt-4 flex justify-end gap-3">
              <button
                type="button"
                onClick={cancelLoad}
                className="rounded-md px-3 py-2 text-sm font-medium text-text-secondary hover:bg-bg-input"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmLoad}
                className="rounded-md bg-accent-primary px-3 py-2 text-sm font-medium text-white hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-accent-primary"
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
