/**
 * App shell with professional BI layout — full integration wiring.
 *
 * Layout: Sidebar (260px/48px) | MainContent (fluid) | TraceabilityPanel (360px, hidden)
 * MainContent contains: ChatThread + FooterBar + ChatInput stacked vertically.
 *
 * Connections:
 * - ChatInput submit → store.submitQuery → queryBackend API → append response to ChatThread
 * - FooterBar click → toggle TraceabilityPanel visibility via store
 * - Card click/focus → activeCardId → StatsPanel + TraceabilityPanel update
 * - Sidebar: thread selection, saved prompt load (with unsaved-changes warning), new chat
 * - Session restore from localStorage on app load (via zustand persist middleware)
 * - Streaming indicator shows during API calls and dismisses on response
 * - Storage error notification when localStorage persist fails
 * - Design System tokens applied consistently across all components
 *
 * No horizontal overflow on viewports 1024px–2560px.
 * Light theme with Inter font, 14px base size.
 *
 * Requirements: 1.1, 1.3, 1.4, 1.7, 2.2, 2.6, 2.7, 2.8, 3.1, 3.4, 7.1, 9.2, 10.5, 10.6, 11.5
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSessionStore } from './store/sessionStore';
import { Sidebar } from './components/Sidebar';
import { ChatThread } from './components/ChatThread';
import { FooterBar } from './components/FooterBar';
import { ChatInput } from './components/ChatInput';
import { TraceabilityPanel } from './components/TraceabilityPanel';
import { SaveSessionModal } from './components/SaveSessionModal';

/**
 * Non-blocking storage error banner.
 * Displays when localStorage persistence fails (quota exceeded, unavailable).
 * Requirement 10.5: non-blocking warning without losing in-memory state.
 */
function StorageErrorBanner() {
  const storageError = useSessionStore((s) => s.storageError);
  const clearStorageError = useSessionStore((s) => s.clearStorageError);

  if (!storageError) return null;

  return (
    <div
      role="alert"
      aria-live="polite"
      className="flex items-center gap-2 border-b border-status-warning/30 bg-amber-50 px-4 py-2 text-sm text-status-warning"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        className="h-4 w-4 flex-shrink-0"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={2}
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
        />
      </svg>
      <span className="flex-1">{storageError}</span>
      <button
        type="button"
        onClick={clearStorageError}
        className="rounded p-1 text-status-warning hover:bg-amber-100 transition-colors"
        aria-label="Dismiss storage warning"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-4 w-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

/**
 * Chat top bar with bookmark/save and schedule buttons.
 * Only visible when there's an active chat with at least one visualization.
 * Schedule button visible only when there are pinned cards.
 */
function ChatTopBar({ onBookmark }: { onBookmark: () => void }) {
  const navigate = useNavigate();
  const chatThread = useSessionStore((s) => s.chatThread);
  const cards = useSessionStore((s) => s.cards);

  // Only show when there's at least one card in the current session
  const hasCards = Object.keys(cards).length > 0;
  if (!hasCards || chatThread.length === 0) return null;

  // Get all pinned card IDs for scheduling
  const pinnedCardIds = Object.values(cards)
    .filter((card) => card.pinned)
    .map((card) => card.id);
  const hasPinnedCards = pinnedCardIds.length > 0;

  const handleScheduleChat = () => {
    // Navigate to create scheduled report with all pinned viz IDs
    const vizIds = pinnedCardIds.join(',');
    navigate(`/scheduled-reports/new?viz_ids=${encodeURIComponent(vizIds)}`);
  };

  return (
    <div className="flex items-center justify-end gap-2 px-4 py-2 border-b border-border-default bg-bg-secondary/50">
      {/* Schedule Chat button — only when pinned cards exist */}
      {hasPinnedCards && (
        <button
          type="button"
          onClick={handleScheduleChat}
          className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-text-secondary hover:bg-bg-input hover:text-accent-primary transition-colors"
          aria-label="Schedule this chat"
          title={`Schedule ${pinnedCardIds.length} pinned visualization${pinnedCardIds.length > 1 ? 's' : ''} for recurring execution`}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1.5}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span>Schedule ({pinnedCardIds.length})</span>
        </button>
      )}

      {/* Bookmark button */}
      <button
        type="button"
        onClick={onBookmark}
        className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-text-secondary hover:bg-bg-input hover:text-accent-primary transition-colors"
        aria-label="Bookmark this chat"
        title="Save this chat to Saved Prompts"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-4 w-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M17.593 3.322c1.1.128 1.907 1.077 1.907 2.185V21L12 17.25 4.5 21V5.507c0-1.108.806-2.057 1.907-2.185a48.507 48.507 0 0111.186 0z"
          />
        </svg>
        <span>Bookmark Chat</span>
      </button>
    </div>
  );
}

function App() {
  const traceabilityPanelVisible = useSessionStore(
    (s) => s.traceabilityPanelVisible,
  );
  const [showSaveModal, setShowSaveModal] = useState(false);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-bg-primary font-sans">
      {/* Sidebar (left) — collapses between 260px and 48px */}
      <Sidebar />

      {/* Main content (fluid center) */}
      <main className="relative flex flex-1 min-w-0 flex-col min-h-0">
        {/* Non-blocking storage error banner (Req 10.5) */}
        <StorageErrorBanner />

        {/* Top bar with bookmark button */}
        <ChatTopBar onBookmark={() => setShowSaveModal(true)} />

        {/* Chat thread — takes up all available space, with bottom padding for floating input */}
        <ChatThread />

        {/* Footer bar — traceability toggle (Req 3.1) */}
        <FooterBar />

        {/* Chat input — floating at bottom center (Req 2.2) */}
        {!traceabilityPanelVisible && <ChatInput />}
      </main>

      {/* Traceability Panel (right) — 360px, hidden by default (Req 3.1, 3.4) */}
      {traceabilityPanelVisible && <TraceabilityPanel />}

      {/* Save Session Modal */}
      {showSaveModal && (
        <SaveSessionModal onClose={() => setShowSaveModal(false)} />
      )}
    </div>
  );
}

export default App;
