/**
 * App shell with responsive layout.
 *
 * Desktop (≥1024px):
 * - TopBar: fixed at top, full width
 * - Below the TopBar, a horizontal flex container:
 *   - Sidebar: 260px fixed width (left)
 *   - Center column (flex-1, min-w-0): Canvas + ChatBar stacked vertically
 *   - StatsPanel: 300px collapsible (right)
 *
 * Narrow (<1024px):
 * - TopBar: fixed at top, full width
 * - Vertical stack: Sidebar (top bar/toggle) → Canvas → Stats Accordion → Chat Bar
 * - Sidebar collapses to a compact top bar with hamburger toggle
 * - Stats Panel renders as a collapsible accordion below the canvas
 * - Canvas forces single-column layout
 * - No horizontal overflow at 360px, 768px, 1023px
 *
 * Requirements: 1.1, 1.5, 1.6, 1.8, 7.1
 */

import { useSessionStore } from './store/sessionStore';
import { TopBar } from './components/TopBar';
import { Sidebar } from './components/Sidebar';
import { Canvas } from './components/Canvas';
import { ChatBar } from './components/ChatBar';
import { StatsPanel, StatsPanelAccordion } from './components/StatsPanel';

function App() {
  const statsPanelCollapsed = useSessionStore((s) => s.statsPanelCollapsed);
  const toggleStatsPanel = useSessionStore((s) => s.toggleStatsPanel);

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden">
      {/* Top Bar — fixed at top, full width */}
      <TopBar />

      {/* Main content area */}
      <div className="flex flex-1 min-h-0 overflow-hidden flex-col lg:flex-row">
        {/* Sidebar: desktop = 260px left rail; narrow = top bar with toggle */}
        <Sidebar />

        {/* Center: Canvas + (mobile accordion) + ChatBar */}
        <div className="flex flex-1 min-w-0 max-w-full flex-col min-h-0">
          <Canvas />

          {/* Mobile Stats Accordion — only visible below 1024px */}
          <StatsPanelAccordion />

          <ChatBar />
        </div>

        {/* Right: Stats Panel (300px, collapsible) — only visible ≥1024px */}
        <StatsPanel collapsed={statsPanelCollapsed} onToggle={toggleStatsPanel} />

        {/* Toggle button visible when Stats Panel is collapsed on desktop */}
        {statsPanelCollapsed && (
          <button
            type="button"
            onClick={toggleStatsPanel}
            className="hidden lg:flex items-center justify-center w-6 border-l border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200"
            aria-label="Expand stats panel"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}

export default App;
