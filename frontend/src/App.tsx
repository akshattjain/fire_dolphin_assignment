import { useState } from 'react';
import Home from './pages/Home';
import Chat from './pages/Chat';
import type { RepoStatus } from './api';
import './App.css';

// The two top-level views of the app.
// When navigating back from Chat → Home, we carry the repo so the user
// can see their already-ingested repo and sessions immediately.
export type AppView =
  | { page: 'home'; repo?: RepoStatus }
  | { page: 'chat'; repo: RepoStatus; sessionId: string };

export default function App() {
  const [view, setView] = useState<AppView>({ page: 'home' });

  return (
    <div className="app">
      {view.page === 'home' && (
        <Home
          initialRepo={view.repo}
          onOpenChat={(repo, sessionId) =>
            setView({ page: 'chat', repo, sessionId })
          }
        />
      )}
      {view.page === 'chat' && (
        <Chat
          repo={view.repo}
          initialSessionId={view.sessionId}
          onBack={(repo) => setView({ page: 'home', repo })}
        />
      )}
    </div>
  );
}
