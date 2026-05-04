import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { WSProvider } from './context/WSContext';
import Sidebar from './components/Sidebar';
import Monitor from './pages/Monitor';
import Search from './pages/Search';
import Cameras from './pages/Cameras';
import Settings from './pages/Settings';
import './index.css';

// Lazy-load heavier pages
import { lazy, Suspense } from 'react';
const Events    = lazy(() => import('./pages/Events'));
const Analytics = lazy(() => import('./pages/Analytics'));
const Recording = lazy(() => import('./pages/Recording'));
const Playback  = lazy(() => import('./pages/Playback'));

function PageLoader() {
  return (
    <div className="empty-state" style={{ height: '60vh' }}>
      <div style={{
        width: 32, height: 32,
        borderRadius: '50%',
        border: '3px solid var(--border)',
        borderTopColor: 'var(--accent-blue)',
        animation: 'spin 0.7s linear infinite',
      }} />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

export default function App() {
  return (
    <WSProvider>
      <BrowserRouter>
        <div className="app-layout">
          <Sidebar />
          <main className="main-content">
            <Suspense fallback={<PageLoader />}>
              <Routes>
                <Route path="/"           element={<Monitor />} />
                <Route path="/events"     element={<Events />} />
                <Route path="/search"     element={<Search />} />
                <Route path="/playback"   element={<Playback />} />
                <Route path="/analytics"  element={<Analytics />} />
                <Route path="/cameras"    element={<Cameras />} />
                <Route path="/recording"  element={<Recording />} />
                <Route path="/settings"   element={<Settings />} />
                <Route path="*"           element={<Navigate to="/" replace />} />
              </Routes>
            </Suspense>
          </main>
        </div>
      </BrowserRouter>
    </WSProvider>
  );
}
