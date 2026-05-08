import { useState, useEffect, useRef, useCallback } from 'react';
import {
  ingestRepository,
  listRepositories,
  getRepoStatus,
  listSessions,
  createSession,
  getApiError,
  type RepoStatus,
  type SessionListItem,
} from '../api';

// ── GitHub URL validation ─────────────────────────────────────────────────────

function parseGithubUrl(url: string): { owner: string; repo: string } | null {
  try {
    const u = new URL(url.trim());
    if (u.hostname !== 'github.com') return null;
    const parts = u.pathname.replace(/^\//, '').replace(/\/$/, '').split('/');
    if (parts.length < 2 || !parts[0] || !parts[1]) return null;
    return { owner: parts[0], repo: parts[1] };
  } catch {
    return null;
  }
}

// ── Status helpers ────────────────────────────────────────────────────────────

const TERMINAL = new Set(['COMPLETED', 'FAILED']);

// ── Pipeline stages ───────────────────────────────────────────────────────────

type StageState = 'idle' | 'active' | 'done' | 'failed';

function getStageStates(status: string): [StageState, StageState, StageState] {
  switch (status) {
    case 'CLONING':    return ['active', 'idle',   'idle'];
    case 'PROCESSING': return ['done',   'active',  'idle'];
    case 'COMPLETED':  return ['done',   'done',    'done'];
    case 'FAILED':     return ['failed', 'failed',  'failed'];
    default:           return ['active', 'idle',    'idle']; // PENDING
  }
}

function PipelineStep({ state, label }: { state: StageState; label: string }) {
  return (
    <div className={`pipeline-step pipeline-step--${state}`}>
      <div className="pipeline-step-icon">
        {state === 'done' && (
          <svg viewBox="0 0 16 16" fill="currentColor" width="12" height="12">
            <path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 011.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z" />
          </svg>
        )}
        {state === 'active' && <span className="spinner-dot" />}
        {state === 'failed' && (
          <svg viewBox="0 0 16 16" fill="currentColor" width="12" height="12">
            <path d="M3.72 3.72a.75.75 0 011.06 0L8 6.94l3.22-3.22a.75.75 0 111.06 1.06L9.06 8l3.22 3.22a.75.75 0 11-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 01-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 010-1.06z" />
          </svg>
        )}
      </div>
      <span className="pipeline-step-label">{label}</span>
    </div>
  );
}

function PipelineStages({
  status,
  processed,
  total,
}: {
  status: string;
  processed: number;
  total: number;
}) {
  const [s1, s2, s3] = getStageStates(status);
  const pct = total > 0 ? Math.round((processed / total) * 100) : 0;

  return (
    <div className="pipeline">
      <div className="pipeline-track">
        <PipelineStep state={s1} label="Clone" />
        <div className={`pipeline-line ${s1 === 'done' ? 'pipeline-line--done' : ''}`} />
        <PipelineStep state={s2} label="Parse & Chunk" />
        <div className={`pipeline-line ${s2 === 'done' ? 'pipeline-line--done' : ''}`} />
        <PipelineStep state={s3} label="Ready" />
      </div>

      {status === 'PROCESSING' && (
        <div className="pipeline-progress">
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${pct}%` }} />
          </div>
          <div className="pipeline-progress-meta">
            <span>{processed} / {total} files indexed</span>
            <span className="pipeline-s3-note">
              <svg viewBox="0 0 16 16" fill="currentColor" width="10" height="10">
                <path d="M8 0a8 8 0 100 16A8 8 0 008 0zm1 11.5a.75.75 0 01-1.5 0v-4a.75.75 0 011.5 0v4zm-.75-7a1 1 0 110-2 1 1 0 010 2z" />
              </svg>
              S3 upload running in background
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function RepoCard({
  repo,
  onNewChat,
  onOpenSession,
  sessions,
  loadingSessions,
  creatingSession,
}: {
  repo: RepoStatus;
  onNewChat: () => void;
  onOpenSession: (id: string) => void;
  sessions: SessionListItem[];
  loadingSessions: boolean;
  creatingSession: boolean;
}) {
  const repoName = repo.name ?? repo.github_url.split('/').pop() ?? 'Repository';
  const owner = repo.owner ?? '';

  return (
    <div className="repo-card">
      {/* Header: identity + status pill */}
      <div className="repo-card-header">
        <div className="repo-identity">
          <svg className="repo-icon" viewBox="0 0 16 16" fill="currentColor">
            <path d="M2 2.5A2.5 2.5 0 014.5 0h8.75a.75.75 0 01.75.75v12.5a.75.75 0 01-.75.75h-2.5a.75.75 0 110-1.5h1.75v-2h-8a1 1 0 00-.714 1.7.75.75 0 01-1.072 1.05A2.495 2.495 0 012 11.5v-9zm10.5-1V9h-8c-.356 0-.694.074-1 .208V2.5a1 1 0 011-1h8zM5 12.25v3.25a.25.25 0 00.4.2l1.45-1.087a.25.25 0 01.3 0L8.6 15.7a.25.25 0 00.4-.2v-3.25a.25.25 0 00-.25-.25h-3.5a.25.25 0 00-.25.25z" />
          </svg>
          <div>
            <p className="repo-owner">{owner}</p>
            <h2 className="repo-name">{repoName}</h2>
          </div>
        </div>
        {repo.status === 'COMPLETED' && (
          <p className="repo-files">{repo.total_files} files indexed</p>
        )}
      </div>

      {/* Pipeline stages strip */}
      <PipelineStages
        status={repo.status}
        processed={repo.processed_files}
        total={repo.total_files}
      />

      {/* Sessions body — only when ready */}
      {repo.status === 'COMPLETED' && (
        <div className="repo-card-body">
          <div className="sessions-header">
            <h3>Chat sessions</h3>
            <button
              className="btn-primary btn-sm"
              onClick={onNewChat}
              disabled={creatingSession}
            >
              {creatingSession ? (
                <>
                  <span className="btn-spinner" />
                  Creating…
                </>
              ) : (
                <>
                  <svg viewBox="0 0 16 16" fill="currentColor" width="14" height="14">
                    <path d="M7.75 2a.75.75 0 01.75.75V7h4.25a.75.75 0 010 1.5H8.5v4.25a.75.75 0 01-1.5 0V8.5H2.75a.75.75 0 010-1.5H7V2.75A.75.75 0 017.75 2z" />
                  </svg>
                  New chat
                </>
              )}
            </button>
          </div>

          {loadingSessions ? (
            <div className="sessions-loading">
              <span className="spinner-ring" />
              <span>Loading sessions…</span>
            </div>
          ) : sessions.length === 0 ? (
            <div className="sessions-empty">
              <p>No sessions yet. Start a new chat to explore this repository.</p>
            </div>
          ) : (
            <ul className="sessions-list">
              {sessions.map((s) => (
                <li key={s.id}>
                  <button
                    className="session-item"
                    onClick={() => onOpenSession(s.id)}
                  >
                    <svg viewBox="0 0 16 16" fill="currentColor" width="14" height="14" className="session-icon">
                      <path d="M1 2.75C1 1.784 1.784 1 2.75 1h10.5c.966 0 1.75.784 1.75 1.75v7.5A1.75 1.75 0 0113.25 12H9.06l-2.573 2.573A1.457 1.457 0 014 13.543V12H2.75A1.75 1.75 0 011 10.25v-7.5z" />
                    </svg>
                    <span className="session-title">
                      {s.title ?? 'Untitled session'}
                    </span>
                    <span className="session-date">
                      {new Date(s.created_at).toLocaleDateString()}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {repo.status === 'FAILED' && (
        <div className="repo-card-body">
          <p className="error-text">
            Ingestion failed. Re-submitting the same URL will retry automatically.
          </p>
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface HomeProps {
  initialRepo?: RepoStatus;
  onOpenChat: (repo: RepoStatus, sessionId: string) => void;
}

export default function Home({ initialRepo, onOpenChat }: HomeProps) {
  const [url, setUrl] = useState(initialRepo?.github_url ?? '');
  const [urlError, setUrlError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  const [repos, setRepos] = useState<RepoStatus[]>(initialRepo ? [initialRepo] : []);
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [loadingData, setLoadingData] = useState(false);
  const [creatingSessionFor, setCreatingSessionFor] = useState<string | null>(null);

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Polling & Data Fetching ─────────────────────────────────────────────

  const fetchAllData = useCallback(async () => {
    try {
      const [fetchedRepos, fetchedSessions] = await Promise.all([
        listRepositories(),
        listSessions(),
      ]);
      setRepos(fetchedRepos);
      setSessions(fetchedSessions);
    } catch (e) {
      console.error('Failed to fetch data', e);
    }
  }, []);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const startPolling = useCallback(() => {
    stopPolling();
    pollingRef.current = setInterval(async () => {
      try {
        const fetchedRepos = await listRepositories();
        setRepos(fetchedRepos);

        // If all repos are in terminal state, we can stop polling
        const allTerminal = fetchedRepos.every((r) => TERMINAL.has(r.status));
        if (allTerminal) {
          stopPolling();
          // Fetch sessions one last time in case new ones were created
          const fetchedSessions = await listSessions();
          setSessions(fetchedSessions);
        }
      } catch {
        // silently retry next tick
      }
    }, 2500);
  }, [stopPolling]);

  useEffect(() => {
    setLoadingData(true);
    fetchAllData().finally(() => setLoadingData(false));
  }, [fetchAllData]);

  useEffect(() => {
    const hasNonTerminal = repos.some((r) => !TERMINAL.has(r.status));
    if (hasNonTerminal && !pollingRef.current) {
      startPolling();
    } else if (!hasNonTerminal && pollingRef.current) {
      stopPolling();
    }
  }, [repos, startPolling, stopPolling]);

  useEffect(() => {
    return stopPolling;
  }, [stopPolling]);

  // ── Handlers ─────────────────────────────────────────────────────────────

  const handleSubmit = async (e: { preventDefault(): void }) => {
    e.preventDefault();
    setUrlError('');
    setSubmitError('');

    const parsed = parseGithubUrl(url);
    if (!parsed) {
      setUrlError('Enter a valid GitHub URL, e.g. https://github.com/owner/repo');
      return;
    }

    setSubmitting(true);

    try {
      await ingestRepository(url.trim());
      await fetchAllData();
      startPolling();
      setUrl('');
    } catch (e) {
      setSubmitError(getApiError(e));
    } finally {
      setSubmitting(false);
    }
  };

  const handleNewChat = async (repo: RepoStatus) => {
    setCreatingSessionFor(repo.repo_id);
    try {
      const session = await createSession(repo.repo_id);
      setSessions((prev) => [
        {
          id: session.session_id,
          repo_id: session.repo_id,
          title: null,
          created_at: session.created_at,
        },
        ...prev,
      ]);
      onOpenChat(repo, session.session_id);
    } catch (e) {
      setSubmitError(getApiError(e));
    } finally {
      setCreatingSessionFor(null);
    }
  };

  const handleOpenSession = (repo: RepoStatus, sessionId: string) => {
    onOpenChat(repo, sessionId);
  };

  // ── Render ───────────────────────────────────────────────────────────────

  const isPolling = repos.some((r) => !TERMINAL.has(r.status));

  return (
    <div className="home">
      {/* ── Nav ── */}
      <nav className="home-nav">
        <div className="brand">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="22" height="22">
            <polyline points="16 18 22 12 16 6" />
            <polyline points="8 6 2 12 8 18" />
          </svg>
          <span>Repo Intelligence</span>
        </div>
      </nav>

      {/* ── Hero ── */}
      <main className="home-main">
        <header className="hero">
          <h1 className="hero-title">Ask anything about any GitHub repo</h1>
          <p className="hero-sub">
            Paste a public repository URL to index its codebase, then chat with it
            using natural language.
          </p>
        </header>

        {/* ── URL input form ── */}
        <form className="url-form" onSubmit={handleSubmit}>
          <div className={`url-input-wrap ${urlError ? 'has-error' : ''}`}>
            <svg className="url-icon" viewBox="0 0 16 16" fill="currentColor">
              <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.012 8.012 0 0016 8c0-4.42-3.58-8-8-8z" />
            </svg>
            <input
              type="text"
              className="url-input"
              placeholder="https://github.com/owner/repository"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                setUrlError('');
              }}
              disabled={submitting}
              spellCheck={false}
            />
            <button
              type="submit"
              className="btn-primary"
              disabled={submitting || !url.trim()}
            >
              {submitting ? (
                <>
                  <span className="btn-spinner" />
                  Submitting…
                </>
              ) : (
                'Analyze'
              )}
            </button>
          </div>
          {urlError && <p className="field-error">{urlError}</p>}
          {submitError && <p className="field-error">{submitError}</p>}
        </form>

        {/* ── Repo list ── */}
        <div className="repo-list">
          {loadingData && repos.length === 0 ? (
            <div className="repo-card skeleton-card">
              <div className="skeleton-line w-40" />
              <div className="skeleton-line w-64 mt-2" />
            </div>
          ) : (
            repos.map((repo) => (
              <RepoCard
                key={repo.repo_id}
                repo={repo}
                onNewChat={() => handleNewChat(repo)}
                onOpenSession={(sessionId) => handleOpenSession(repo, sessionId)}
                sessions={sessions.filter((s) => s.repo_id === repo.repo_id)}
                loadingSessions={loadingData}
                creatingSession={creatingSessionFor === repo.repo_id}
              />
            ))
          )}
        </div>
      </main>
    </div>
  );
}
