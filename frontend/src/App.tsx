import { Sidebar } from './components/Sidebar';
import Canvas from './components/Canvas';
import { StatsPanel } from './components/StatsPanel';
import { ChatBar } from './components/ChatBar';

/**
 * App shell with three-panel layout + fixed-bottom ChatBar:
 * - Sidebar: 260px fixed, left
 * - Canvas: fluid center, expands when StatsPanel is collapsed
 * - StatsPanel: 300px collapsible, right (manages its own collapse via zustand)
 * - ChatBar: fixed to bottom, overlays across full width
 *
 * ChatBar submit → store.submitQuery → API → addCard → Canvas render
 * Card click/focus → activeCardId → StatsPanel update
 * Sidebar thread selection and bookmark load → store → Canvas + StatsPanel
 * Session restores from localStorage on app load via zustand persist middleware
 *
 * Uses Tailwind flex layout. No horizontal overflow from 1024px to 2560px.
 * Requirements: 1.1, 1.5, 1.6, 1.8, 2.2, 2.6, 2.7, 2.8, 7.1, 9.2, 9.7, 10.8
 */
function App() {
  return (
    <div
      className="h-screen w-screen flex overflow-hidden"
      data-testid="app-shell"
    >
      <Sidebar />
      <Canvas />
      <StatsPanel />
      <ChatBar />
    </div>
  );
}

export default App;
