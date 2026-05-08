import { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  listSessions,
  createSession,
  getMessages,
  sendMessage,
  getApiError,
  type RepoStatus,
  type SessionListItem,
  type Message,
  type Citation,
} from '../api';

// ── Types ─────────────────────────────────────────────────────────────────────

// We augment the Message type locally to carry optional citations (only present
// for assistant messages created in this session — not loaded from history).
interface ChatMessage extends Message {
  citations?: Citation[];
  isOptimistic?: boolean; // user messages added before the API responds
}

// ── Citation block ────────────────────────────────────────────────────────────

function CitationBlock({ citation, index }: { citation: Citation; index: number }) {
  const [open, setOpen] = useState(false);
  const hasName = citation.name.trim() !== '';

  return (
    <div className="citation">
      <button className="citation-toggle" onClick={() => setOpen((o) => !o)}>
        <svg
          className={`citation-chevron ${open ? 'open' : ''}`}
          viewBox="0 0 16 16"
          fill="currentColor"
          width="12"
          height="12"
        >
          <path d="M6.22 3.22a.75.75 0 011.06 0l4.25 4.25a.75.75 0 010 1.06l-4.25 4.25a.75.75 0 01-1.06-1.06L9.94 8 6.22 4.28a.75.75 0 010-1.06z" />
        </svg>
        <span className="citation-num">#{index + 1}</span>
        <code className="citation-path">{citation.file_path}</code>
        <span className="citation-lines">
          L{citation.start_line}–{citation.end_line}
        </span>
        {hasName && (
          <span className="citation-badge">{citation.chunk_type}: {citation.name}</span>
        )}
      </button>
      {open && (
        <pre className="citation-code">{citation.snippet}</pre>
      )}
    </div>
  );
}

// ── Message bubble ────────────────────────────────────────────────────────────

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user';

  return (
    <div className={`message-wrap ${isUser ? 'user' : 'assistant'}`}>
      <div className="message-role-label">{isUser ? 'You' : 'Assistant'}</div>
      <div className={`message-bubble ${isUser ? 'user' : 'assistant'} ${msg.isOptimistic ? 'optimistic' : ''}`}>
        <div className="message-content">
          <ReactMarkdown>{msg.content}</ReactMarkdown>
        </div>
      </div>
      {!isUser && msg.citations && msg.citations.length > 0 && (
        <div className="citations-list">
          <p className="citations-label">
            {msg.citations.length} source{msg.citations.length !== 1 ? 's' : ''}
          </p>
          {msg.citations.map((c, i) => (
            <CitationBlock key={i} citation={c} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Typing indicator ──────────────────────────────────────────────────────────

function TypingIndicator() {
  return (
    <div className="message-wrap assistant">
      <div className="message-role-label">Assistant</div>
      <div className="message-bubble assistant typing-bubble">
        <span className="dot" />
        <span className="dot" />
        <span className="dot" />
      </div>
    </div>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────

function Sidebar({
  repo,
  sessions,
  activeId,
  onSelect,
  onNewChat,
  onBack,
  creating,
}: {
  repo: RepoStatus;
  sessions: SessionListItem[];
  activeId: string;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onBack: () => void;
  creating: boolean;
}) {
  const repoName = repo.name ?? repo.github_url.split('/').pop() ?? 'Repository';

  return (
    <aside className="sidebar">
      {/* Back */}
      <button className="sidebar-back" onClick={onBack}>
        <svg viewBox="0 0 16 16" fill="currentColor" width="14" height="14">
          <path d="M9.78 12.78a.75.75 0 01-1.06 0L4.47 8.53a.75.75 0 010-1.06l4.25-4.25a.75.75 0 011.06 1.06L6.06 8l3.72 3.72a.75.75 0 010 1.06z" />
        </svg>
        Back
      </button>

      {/* Repo info */}
      <div className="sidebar-repo">
        <p className="sidebar-repo-owner">{repo.owner ?? ''}</p>
        <p className="sidebar-repo-name">{repoName}</p>
        <p className="sidebar-repo-files">{repo.total_files} files</p>
      </div>

      <div className="sidebar-divider" />

      {/* New chat */}
      <button
        className="btn-primary btn-sm sidebar-new-chat"
        onClick={onNewChat}
        disabled={creating}
      >
        {creating ? (
          <>
            <span className="btn-spinner" />
            Creating…
          </>
        ) : (
          <>
            <svg viewBox="0 0 16 16" fill="currentColor" width="13" height="13">
              <path d="M7.75 2a.75.75 0 01.75.75V7h4.25a.75.75 0 010 1.5H8.5v4.25a.75.75 0 01-1.5 0V8.5H2.75a.75.75 0 010-1.5H7V2.75A.75.75 0 017.75 2z" />
            </svg>
            New chat
          </>
        )}
      </button>

      {/* Sessions */}
      <nav className="sidebar-sessions">
        {sessions.map((s) => (
          <button
            key={s.id}
            className={`sidebar-session ${s.id === activeId ? 'active' : ''}`}
            onClick={() => onSelect(s.id)}
          >
            <svg viewBox="0 0 16 16" fill="currentColor" width="13" height="13" className="session-icon">
              <path d="M1 2.75C1 1.784 1.784 1 2.75 1h10.5c.966 0 1.75.784 1.75 1.75v7.5A1.75 1.75 0 0113.25 12H9.06l-2.573 2.573A1.457 1.457 0 014 13.543V12H2.75A1.75 1.75 0 011 10.25v-7.5z" />
            </svg>
            <span className="sidebar-session-title">
              {s.title ?? 'New session'}
            </span>
          </button>
        ))}
      </nav>
    </aside>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface ChatProps {
  repo: RepoStatus;
  initialSessionId: string;
  onBack: (repo: RepoStatus) => void;
}

export default function Chat({ repo, initialSessionId, onBack }: ChatProps) {
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [activeSessionId, setActiveSessionId] = useState(initialSessionId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [question, setQuestion] = useState('');
  const [sendError, setSendError] = useState('');
  const [creatingSession, setCreatingSession] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // ── Scroll helpers ───────────────────────────────────────────────────────

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, sending, scrollToBottom]);

  // ── Load sessions once ───────────────────────────────────────────────────

  useEffect(() => {
    listSessions(repo.repo_id)
      .then(setSessions)
      .catch(() => {});
  }, [repo.repo_id]);

  // ── Load messages when session changes ───────────────────────────────────

  useEffect(() => {
    setMessages([]);
    setSendError('');
    setLoadingMessages(true);

    getMessages(activeSessionId)
      .then((msgs) => setMessages(msgs))
      .catch(() => {})
      .finally(() => setLoadingMessages(false));
  }, [activeSessionId]);

  // ── Auto-resize textarea ─────────────────────────────────────────────────

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`;
  }, [question]);

  // ── Send message ─────────────────────────────────────────────────────────

  const handleSend = async () => {
    const q = question.trim();
    if (!q || sending) return;

    setQuestion('');
    setSendError('');
    setSending(true);

    // Optimistic user message
    const optimisticId = `opt-${Date.now()}`;
    const optimisticMsg: ChatMessage = {
      id: optimisticId,
      role: 'user',
      content: q,
      created_at: new Date().toISOString(),
      isOptimistic: true,
    };
    setMessages((prev) => [...prev, optimisticMsg]);

    try {
      const response = await sendMessage(activeSessionId, q);

      // Replace optimistic with confirmed user message, then add assistant
      setMessages((prev) => {
        const withoutOptimistic = prev.filter((m) => m.id !== optimisticId);
        const confirmedUser: ChatMessage = {
          id: `user-${response.message_id}`,
          role: 'user',
          content: q,
          created_at: new Date().toISOString(),
        };
        const assistantMsg: ChatMessage = {
          id: response.message_id,
          role: 'assistant',
          content: response.answer,
          created_at: new Date().toISOString(),
          citations: response.citations,
        };
        return [...withoutOptimistic, confirmedUser, assistantMsg];
      });

      // Update session title in sidebar if it was the first message
      setSessions((prev) =>
        prev.map((s) =>
          s.id === activeSessionId && !s.title
            ? { ...s, title: q.slice(0, 80) }
            : s,
        ),
      );
    } catch (e) {
      // Remove optimistic message and show error
      setMessages((prev) => prev.filter((m) => m.id !== optimisticId));
      setSendError(getApiError(e));
    } finally {
      setSending(false);
      textareaRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ── Create new session ───────────────────────────────────────────────────

  const handleNewChat = async () => {
    setCreatingSession(true);
    try {
      const session = await createSession(repo.repo_id);
      const newItem: SessionListItem = {
        id: session.session_id,
        repo_id: session.repo_id,
        title: null,
        created_at: session.created_at,
      };
      setSessions((prev) => [newItem, ...prev]);
      setActiveSessionId(session.session_id);
    } catch {
      // silently ignore
    } finally {
      setCreatingSession(false);
    }
  };

  // ── Render ───────────────────────────────────────────────────────────────

  const isEmpty = !loadingMessages && messages.length === 0;

  return (
    <div className="chat-layout">
      <Sidebar
        repo={repo}
        sessions={sessions}
        activeId={activeSessionId}
        onSelect={setActiveSessionId}
        onNewChat={handleNewChat}
        onBack={() => onBack(repo)}
        creating={creatingSession}
      />

      <div className="chat-main">
        {/* ── Messages area ── */}
        <div className="messages-area">
          {loadingMessages && (
            <div className="messages-loading">
              <span className="spinner-ring" />
            </div>
          )}

          {isEmpty && (
            <div className="messages-empty">
              <div className="empty-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" width="40" height="40">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 01.865-.501 48.172 48.172 0 003.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" />
                </svg>
              </div>
              <h3>Ask anything about this codebase</h3>
              <p>Try "How does authentication work?" or "What does the main entry point do?"</p>
            </div>
          )}

          {messages.map((msg) => (
            <MessageBubble key={msg.id} msg={msg} />
          ))}

          {sending && <TypingIndicator />}

          <div ref={bottomRef} />
        </div>

        {/* ── Input area ── */}
        <div className="chat-input-area">
          {sendError && (
            <div className="send-error">
              <svg viewBox="0 0 16 16" fill="currentColor" width="14" height="14">
                <path d="M8 1.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM0 8a8 8 0 1116 0A8 8 0 010 8zm7.25-3.25a.75.75 0 011.5 0v3.5a.75.75 0 01-1.5 0v-3.5zm.75 7a.75.75 0 100-1.5.75.75 0 000 1.5z" />
              </svg>
              {sendError}
            </div>
          )}
          <div className="chat-input-box">
            <textarea
              ref={textareaRef}
              className="chat-textarea"
              placeholder="Ask a question about this codebase… (Enter to send, Shift+Enter for newline)"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={sending}
              rows={1}
            />
            <button
              className="send-btn"
              onClick={handleSend}
              disabled={sending || !question.trim()}
              aria-label="Send"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="18" height="18">
                <line x1="12" y1="19" x2="12" y2="5"></line>
                <polyline points="5 12 12 5 19 12"></polyline>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
