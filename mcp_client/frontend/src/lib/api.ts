import axios from 'axios';
import type { ServerConfig, ServerResponse, Tool, ChatSession, Message, ChatResponse } from '../types';

const api = axios.create({
  baseURL: 'http://localhost:8000',
  headers: {
    'Content-Type': 'application/json',
  },
});

export const mcpApi = {
  // Servers
  getServers: () => api.get<ServerResponse[]>('/servers').then(res => res.data),
  addServers: (configs: ServerConfig[]) => api.post<ServerResponse[]>('/servers/add', configs).then(res => res.data),
  removeServer: (name: string) => api.delete(`/servers/${name}`).then(res => res.data),

  // Tools
  getTools: () => api.get<Tool[]>('/tools').then(res => res.data),

  // Sessions
  createSession: () => api.post<{ session_id: string }>('/sessions').then(res => res.data),
  getSessions: () => api.get<ChatSession[]>('/sessions').then(res => res.data),
  getSessionHistory: (sessionId: string) => api.get<Message[]>(`/sessions/${sessionId}/history`).then(res => res.data),

  // Chat
  initChat: (config: { model?: string, api_key?: string, system_prompt?: string }) =>
    api.post('/chat/init', config).then(res => res.data),

  sendMessage: (sessionId: string, message: string) =>
    api.post<ChatResponse>(`/chat/${sessionId}`, { message }).then(res => res.data),

  reset: () => api.post('/reset').then(res => res.data),
};
