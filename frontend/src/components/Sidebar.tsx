/**
 * Collapsible Sidebar component with dropdown sections.
 *
 * Expanded (260px): collapse toggle, "New Chat" button, dropdown-collapsible
 * chat history (up to 50 entries, most recent first), dropdown-collapsible
 * "Saved Prompts" section, and "Schedulability" disabled placeholder.
 *
 * Collapsed (48px icon rail): icons only for New Chat, History, Saved Prompts,
 * and Schedulability.
 *
 * Dark sidebar background (bg-sidebar: #1e293b) with light text (text-inverse).
 * Animate between states with CSS transitions.
 * Sections are collapsible dropdowns with chevron indicators.
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

function ChevronDownIcon({ open }: { open: boolean }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className={`h-4 w-4 transition-transform duration-200 ${open ? 'rotate-0' : '-rotate-90'}`}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
    </svg>
  );
}

/**
 * Collapsible dropdown section for sidebar items.
 */
function DropdownSection({
  icon,
  label,
  open,
  onToggle,
  children,
  disabled = false,
  disabledMessage,
}: {
  icon: React.ReactNode;
  label: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
  disabled?: boolean;
  disabledMessage?: string;
}) {
  const [showTooltip, setShowTooltip] = useState(false);

  if (disabled) {
    return (
      <div className="px-2 py-1">
        <button
          type="button"
          className="flex w-full items-center gap-2 rounded px-3 py-2 text-text-inverse/30 opacity-50 cursor-not-allowed"
          aria-label={label}
          onClick={() => setShowTooltip(true)}
          onMouseEnter={() => setShowTooltip(true)}
          onMouseLeave={() => setShowTooltip(false)}
        >
          {icon}
          <span className="flex-1 text-left text-sm">{label}</span>
        </button>
        {showTooltip && disabledMessage && (
          <p className="mx-3 mt-1 rounded bg-white/10 px-2 py-1 text-xs text-text-inverse/70">
            {disabledMessage}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="px-2 py-1">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-2 rounded px-3 py-2 text-text-inverse/70 hover:bg-white/10 hover:text-text-inverse transition-colors"
        aria-expanded={open}
        aria-label={`${open ? 'Collapse' : 'Expand'} ${label}`}
      >
        {icon}
        <span className="flex-1 text-left text-xs font-semibold uppercase tracking-wider">
          {label}
        </span>
        <ChevronDownIcon open={open} />
      </button>
      <div
        className={`overflow-hidden transition-all duration-200 ${
          open ? 'max-h-[400px] opacity-100' : 'max-h-0 opacity-0'
        }`}
      >
        {children}
      </div>
    </div>
  );
}

function DeleteIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 3H5a2 2 0 00-2 2v4m16-6h-4a2 2 0 00-2 2v4M9 3a2 2 0 012-2h2a2 2 0 012 2m0 0v4m0-6v4m0 10v2a2 2 0 01-2 2H7a2 2 0 01-2-2v-2m16 0V7a2 2 0 00-2-2h-4a2 2 0 00-2 2v10a2 2 0 002 2h4a2 2 0 002-2z" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ThreadHistoryItem({ thread, deleteMode, isSelected, onToggleSelect }: { thread: ThreadSummary; deleteMode: boolean; isSelected: boolean; onToggleSelect: (id: string) => void }) {
  const loadChatThread = useSessionStore((s) => s.loadChatThread);
  const deleteChatThread = useSessionStore((s) => s.deleteChatThread);
  const renameChatThread = useSessionStore((s) => s.renameChatThread);
  const [menuOpen, setMenuOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState(thread.firstMessage);

  const handleRename = () => {
    if (renameValue.trim()) {
      renameChatThread(thread.id, renameValue.trim());
    }
    setRenaming(false);
    setMenuOpen(false);
  };

  if (deleteMode) {
    return (
      <li className="flex items-center gap-2 rounded px-3 py-2 text-sm hover:bg-white/10 transition-colors duration-100">
        <input
          type="checkbox"
          checked={isSelected}
          onChange={() => onToggleSelect(thread.id)}
          className="h-4 w-4 cursor-pointer accent-accent-primary"
          aria-label={`Select ${thread.firstMessage}`}
        />
        <label
          onClick={() => onToggleSelect(thread.id)}
          className="flex-1 cursor-pointer text-text-inverse"
        >
          <p className="truncate font-medium text-sm pr-6">
            {thread.firstMessage.length > 35
              ? thread.firstMessage.slice(0, 35) + '…'
              : thread.firstMessage}
          </p>
          <p className="text-xs text-text-inverse/60 mt-0.5">
            {formatTimestamp(thread.lastActivity)}
          </p>
        </label>
      </li>
    );
  }

  return (
    <li className="group relative rounded px-3 py-2 text-sm hover:bg-white/10 cursor-pointer transition-colors duration-100">
      {renaming ? (
        <input
          type="text"
          value={renameValue}
          onChange={(e) => setRenameValue(e.target.value)}
          onBlur={handleRename}
          onKeyDown={(e) => { if (e.key === 'Enter') handleRename(); if (e.key === 'Escape') { setRenaming(false); setMenuOpen(false); } }}
          autoFocus
          className="w-full rounded bg-white/10 px-1 py-0.5 text-sm text-text-inverse outline-none ring-1 ring-white/30"
          maxLength={100}
        />
      ) : (
        <div onClick={() => loadChatThread(thread.id)} role="button" tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter') loadChatThread(thread.id); }}>
          <p className="truncate text-text-inverse font-medium text-sm pr-6">
            {thread.firstMessage.length > 35
              ? thread.firstMessage.slice(0, 35) + '…'
              : thread.firstMessage}
          </p>
          <p className="text-xs text-text-inverse/60 mt-0.5">
            {formatTimestamp(thread.lastActivity)}
          </p>
        </div>
      )}

      {/* Three-dot menu */}
      {!renaming && (
        <div className="absolute right-2 top-2 hidden group-hover:block">
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setMenuOpen(!menuOpen); }}
            className="rounded p-1 text-text-inverse/50 hover:bg-white/10 hover:text-text-inverse"
            aria-label="Thread options"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
              <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
            </svg>
          </button>
          {menuOpen && (
            <div className="absolute right-0 top-6 z-50 w-32 rounded-md bg-bg-sidebar border border-white/20 py-1 shadow-lg">
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); setRenaming(true); setRenameValue(thread.firstMessage); setMenuOpen(false); }}
                className="w-full px-3 py-1.5 text-left text-xs text-text-inverse/80 hover:bg-white/10"
              >
                Rename
              </button>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); deleteChatThread(thread.id); setMenuOpen(false); }}
                className="w-full px-3 py-1.5 text-left text-xs text-red-400 hover:bg-white/10"
              >
                Delete
              </button>
            </div>
          )}
        </div>
      )}
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
        aria-label={`Load saved chat: ${prompt.name}`}
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
        aria-label={`Delete saved chat: ${prompt.name}`}
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
  const deleteChatThreads = useSessionStore((s) => s.deleteChatThreads);
  const clearAllChatHistory = useSessionStore((s) => s.clearAllChatHistory);

  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [pendingLoadId, setPendingLoadId] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(true);
  const [savedPromptsOpen, setSavedPromptsOpen] = useState(true);
  const [deleteMode, setDeleteMode] = useState(false);
  const [selectedForDelete, setSelectedForDelete] = useState<Set<string>>(new Set());
  const [showBulkDeleteConfirm, setShowBulkDeleteConfirm] = useState(false);

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

        {/* Delete Chats */}
        <button
          type="button"
          onClick={() => setDeleteMode(true)}
          className="rounded p-2 text-text-inverse/70 hover:bg-white/10 hover:text-text-inverse transition-colors"
          aria-label="Delete chats"
          title="Delete Chats"
        >
          <TrashIcon />
        </button>
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
        <div className="flex flex-1 min-h-0 flex-col overflow-y-auto">
          {/* Chat History — Dropdown */}
          <DropdownSection
            icon={<HistoryIcon />}
            label="Chat History"
            open={historyOpen}
            onToggle={() => setHistoryOpen(!historyOpen)}
          >
            <div className="px-1 pb-2">
              {chatHistory.length === 0 ? (
                <p className="px-3 py-2 text-xs text-text-inverse/40">
                  No chat history yet.
                </p>
              ) : (
                <ul className="space-y-0.5" role="list" aria-label="Chat history list">
                  {chatHistory.slice(0, 50).map((thread) => (
                    <ThreadHistoryItem
                      key={thread.id}
                      thread={thread}
                      deleteMode={deleteMode}
                      isSelected={selectedForDelete.has(thread.id)}
                      onToggleSelect={(id) => {
                        const newSelected = new Set(selectedForDelete);
                        if (newSelected.has(id)) {
                          newSelected.delete(id);
                        } else {
                          newSelected.add(id);
                        }
                        setSelectedForDelete(newSelected);
                      }}
                    />
                  ))}
                </ul>
              )}
            </div>
          </DropdownSection>

          {/* Saved Chats — Dropdown */}
          <DropdownSection
            icon={<SavedPromptsIcon />}
            label="Saved Prompts"
            open={savedPromptsOpen}
            onToggle={() => setSavedPromptsOpen(!savedPromptsOpen)}
          >
            <div className="px-1 pb-2">
              {savedPrompts.length === 0 ? (
                <p className="px-3 py-2 text-xs text-text-inverse/40">
                  No saved chats.
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
          </DropdownSection>

          {/* Schedulability (disabled placeholder) — Dropdown */}
          <DropdownSection
            icon={<ScheduleIcon />}
            label="Scheduled Reports"
            open={false}
            onToggle={() => {}}
            disabled={true}
            disabledMessage="Coming soon — schedule recurring queries and reports"
          >
            <div />
          </DropdownSection>
        </div>

        {/* Footer: Delete Button */}
        {!deleteMode && (
          <div className="border-t border-white/10 px-2 py-2">
            <button
              type="button"
              onClick={() => setDeleteMode(true)}
              className="flex w-full items-center justify-center gap-2 rounded-md bg-red-600/20 px-3 py-2 text-sm font-medium text-red-400 hover:bg-red-600/30 transition-colors"
              aria-label="Delete chats"
            >
              <TrashIcon />
              <span>Delete Chats</span>
            </button>
          </div>
        )}

        {/* Footer: Delete Mode Controls */}
        {deleteMode && (
          <div className="border-t border-white/10 px-2 py-2 space-y-2">
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={selectedForDelete.size === chatHistory.length && chatHistory.length > 0}
                onChange={(e) => {
                  if (e.target.checked) {
                    setSelectedForDelete(new Set(chatHistory.map((h) => h.id)));
                  } else {
                    setSelectedForDelete(new Set());
                  }
                }}
                className="h-4 w-4 cursor-pointer accent-accent-primary"
                aria-label="Select all chats"
                disabled={chatHistory.length === 0}
              />
              <label className="flex-1 text-xs text-text-inverse/70 cursor-pointer">
                Select All ({selectedForDelete.size} of {chatHistory.length})
              </label>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => {
                  setDeleteMode(false);
                  setSelectedForDelete(new Set());
                }}
                className="flex-1 rounded-md px-3 py-2 text-xs font-medium text-text-inverse/70 hover:bg-white/10 transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  if (selectedForDelete.size > 0) {
                    setShowBulkDeleteConfirm(true);
                  }
                }}
                disabled={selectedForDelete.size === 0}
                className="flex-1 rounded-md bg-red-600 px-3 py-2 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Delete ({selectedForDelete.size})
              </button>
            </div>
          </div>
        )}
      </aside>

      {/* Delete Confirmation Modal */}
      {pendingDeleteId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          role="dialog"
          aria-modal="true"
          aria-label="Confirm saved chat deletion"
        >
          <div className="mx-4 w-full max-w-sm rounded-lg bg-bg-secondary p-6 shadow-panel">
            <h3 className="text-sm font-semibold text-text-primary">
              Delete Saved Chat
            </h3>
            <p className="mt-2 text-sm text-text-secondary">
              Are you sure you want to delete{' '}
              <span className="font-medium">
                &ldquo;{pendingPrompt?.name ?? 'this chat'}&rdquo;
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
          aria-label="Confirm loading saved chat"
        >
          <div className="mx-4 w-full max-w-sm rounded-lg bg-bg-secondary p-6 shadow-panel">
            <h3 className="text-sm font-semibold text-text-primary">
              Load Saved Chat
            </h3>
            <p className="mt-2 text-sm text-text-secondary">
              You have unsaved changes in your current session. Loading{' '}
              <span className="font-medium">
                &ldquo;{pendingLoadPrompt?.name ?? 'this chat'}&rdquo;
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

      {/* Bulk Delete Confirmation Modal */}
      {showBulkDeleteConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          role="dialog"
          aria-modal="true"
          aria-label="Confirm bulk delete chats"
        >
          <div className="mx-4 w-full max-w-sm rounded-lg bg-bg-secondary p-6 shadow-panel">
            <h3 className="text-sm font-semibold text-text-primary">
              Delete Selected Chats
            </h3>
            <p className="mt-2 text-sm text-text-secondary">
              Are you sure you want to delete <span className="font-medium">{selectedForDelete.size} chat{selectedForDelete.size !== 1 ? 's' : ''}</span>?
              This action cannot be undone.
            </p>
            <div className="mt-4 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => {
                  setShowBulkDeleteConfirm(false);
                }}
                className="rounded-md px-3 py-2 text-sm font-medium text-text-secondary hover:bg-bg-input"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  deleteChatThreads(Array.from(selectedForDelete));
                  setDeleteMode(false);
                  setSelectedForDelete(new Set());
                  setShowBulkDeleteConfirm(false);
                }}
                className="rounded-md bg-status-error px-3 py-2 text-sm font-medium text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-status-error"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
