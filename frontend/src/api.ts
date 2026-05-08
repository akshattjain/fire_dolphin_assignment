import axios from 'axios';
import { z } from 'zod';

export const api = axios.create({ baseURL: 'http://localhost:8000/api' });

// Extract human-readable error message from axios errors.
// Backend returns { detail: string } for 4xx/5xx.
export function getApiError(e: unknown): string {
  if (axios.isAxiosError(e)) {
    const detail = e.response?.data?.detail;
    if (detail) return typeof detail === 'string' ? detail : JSON.stringify(detail);
    return e.message;
  }
  if (e instanceof Error) return e.message;
  return String(e);
}

// ── Schemas (mirror backend Pydantic models exactly) ──────────────────────────

export const HealthSchema = z.object({
  status: z.string(),
});

// POST /api/ingest/repository  → 202
export const IngestResponseSchema = z.object({
  repo_id: z.string(),
  status: z.string(),
  message: z.string(),
});

// GET /api/ingest/repository/{repo_id}/status → 200
export const RepoStatusSchema = z.object({
  repo_id: z.string(),
  github_url: z.string(),
  owner: z.string().nullable(),
  name: z.string().nullable(),
  status: z.string(),            // PENDING | CLONING | PROCESSING | COMPLETED | FAILED
  total_files: z.number().int(),
  processed_files: z.number().int(),
});

// POST /api/chats/sessions → 201  (note: field is session_id, not id)
export const CreateSessionResponseSchema = z.object({
  session_id: z.string(),
  repo_id: z.string(),
  created_at: z.string(),
});

// GET /api/chats/sessions → 200  (note: field is id, not session_id)
export const SessionListItemSchema = z.object({
  id: z.string(),
  repo_id: z.string(),
  title: z.string().nullable(),
  created_at: z.string(),
});

export const CitationSchema = z.object({
  file_path: z.string(),
  start_line: z.number().int(),
  end_line: z.number().int(),
  snippet: z.string(),
  chunk_type: z.string(),
  name: z.string(),
});

// POST /api/chats/sessions/{session_id}/messages → 200
export const SendMessageResponseSchema = z.object({
  message_id: z.string(),
  answer: z.string(),
  citations: z.array(CitationSchema),
});

// GET /api/chats/sessions/{session_id}/messages → 200
export const MessageSchema = z.object({
  id: z.string(),
  role: z.enum(['user', 'assistant']),
  content: z.string(),
  created_at: z.string(),
});

// ── Inferred types ────────────────────────────────────────────────────────────

export type Health = z.infer<typeof HealthSchema>;
export type IngestResponse = z.infer<typeof IngestResponseSchema>;
export type RepoStatus = z.infer<typeof RepoStatusSchema>;
export type CreateSessionResponse = z.infer<typeof CreateSessionResponseSchema>;
export type SessionListItem = z.infer<typeof SessionListItemSchema>;
export type Citation = z.infer<typeof CitationSchema>;
export type SendMessageResponse = z.infer<typeof SendMessageResponseSchema>;
export type Message = z.infer<typeof MessageSchema>;

// ── API functions ─────────────────────────────────────────────────────────────

export const getHealth = async (): Promise<Health> => {
  const res = await api.get('/health');
  return HealthSchema.parse(res.data);
};

export const ingestRepository = async (github_url: string): Promise<IngestResponse> => {
  const res = await api.post('/ingest/repository', { github_url });
  return IngestResponseSchema.parse(res.data);
};

export const getRepoStatus = async (repo_id: string): Promise<RepoStatus> => {
  const res = await api.get(`/ingest/repository/${repo_id}/status`);
  return RepoStatusSchema.parse(res.data);
};

export const listRepositories = async (): Promise<RepoStatus[]> => {
  const res = await api.get('/ingest/repositories');
  return z.array(RepoStatusSchema).parse(res.data);
};

export const createSession = async (repo_id: string): Promise<CreateSessionResponse> => {
  const res = await api.post('/chats/sessions', { repo_id });
  return CreateSessionResponseSchema.parse(res.data);
};

export const listSessions = async (repo_id?: string): Promise<SessionListItem[]> => {
  const res = await api.get('/chats/sessions', {
    params: repo_id ? { repo_id } : {},
  });
  return z.array(SessionListItemSchema).parse(res.data);
};

export const sendMessage = async (
  session_id: string,
  question: string,
): Promise<SendMessageResponse> => {
  const res = await api.post(`/chats/sessions/${session_id}/messages`, { question });
  return SendMessageResponseSchema.parse(res.data);
};

export const getMessages = async (session_id: string): Promise<Message[]> => {
  const res = await api.get(`/chats/sessions/${session_id}/messages`);
  return z.array(MessageSchema).parse(res.data);
};
