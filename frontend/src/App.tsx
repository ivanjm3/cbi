/**
 * App shell with professional BI layout.
 *
 * Layout: Sidebar (260px/48px) | MainContent (fluid) | TraceabilityPanel (360px, hidden)
 * MainContent contains: ChatThread + FooterBar + ChatInput stacked vertically.
 *
 * Connects sidebar collapse and traceability panel visibility to zustand store.
 * No horizontal overflow on viewports 1024px–2560px.
 * Light theme with Inter font, 14px base size.
 *
 * Requirements: 1.1, 1.3, 1.4, 1.7
 */

import { useSessionStore } from './store/sessionStore';
import { Sidebar } from './components/Sidebar';
import { ChatThread } from './components/ChatThread';
import { FooterBar } from './components/FooterBar';
import { ChatInput } from './components/ChatInput';
import { TraceabilityPanel } from './components/TraceabilityPanel';

function App() {
  const traceabilityPanelVisible = useSessionStore(
    (s) => s.traceabilityPanelVisible,
  );

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-bg-primary">
      {/* Sidebar (left) — collapses between 260px and 48px */}
      <Sidebar />

      {/* Main content (fluid center) */}
      <main className="flex flex-1 min-w-0 flex-col min-h-0">
        {/* Chat thread — takes up all available space */}
        <ChatThread />

        {/* Footer bar — traceability toggle */}
        <FooterBar />

        {/* Chat input — fixed at bottom */}
        <ChatInput />
      </main>

      {/* Traceability Panel (right) — 360px, hidden by default */}
      {traceabilityPanelVisible && <TraceabilityPanel />}
    </div>
  );
}

export default App;
