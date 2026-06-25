import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { DndProvider } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';
import './index.css';
import App from './App';
import { ScheduledReportsListPage } from './components/ScheduledReportsListPage';
import { ScheduledReportDetailPage } from './components/ScheduledReportDetailPage';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Router>
      <DndProvider backend={HTML5Backend}>
        <Routes>
          {/* Main chat interface */}
          <Route path="/" element={<App />} />

          {/* Scheduled Reports routes */}
          <Route path="/scheduled-reports" element={<ScheduledReportsListPage />} />
          <Route path="/scheduled-reports/new" element={<ScheduledReportDetailPage />} />
          <Route path="/scheduled-reports/:reportId" element={<ScheduledReportDetailPage />} />
        </Routes>
      </DndProvider>
    </Router>
  </StrictMode>,
);
