/**
 * MCP Client API Module
 * 
 * This module provides all API communication functions for the MCP Client frontend.
 * It handles both REST API calls (using axios) and SSE streaming connections.
 * 
 * @module api
 */

import axios from 'axios';
import type { ServerConfig, ServerResponse, Tool, ChatSession, Message, ChatResponse } from '../types';

/** Base URL for the backend API */
const API_BASE_URL = 'http://localhost:8000';

/**
 * Axios instance configured for the MCP backend API
 */
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * Callbacks for SSE streaming events
 */
export interface StreamCallbacks {
  /** Called when a new token is received */
  onToken?: (token: string) => void;
  /** Called when the LLM requests a tool call */
  onToolCall?: (toolCall: { server: string; tool: string; arguments: Record<string, unknown> }) => void;
  /** Called when a tool execution completes */
  onToolResult?: (result: { server: string; tool: string; success: boolean; result?: string }) => void;
  /** Called when the stream completes successfully */
  onDone?: (fullMessage: string) => void;
  /** Called when an error occurs */
  onError?: (error: string) => void;
  /** Called when the SSE connection is established */
  onConnected?: () => void;
}

/**
 * MCP Client API functions
 * 
 * @example
 * // Get list of connected servers
 * const servers = await mcpApi.getServers();
 * 
 * @example
 * // Stream a chat message
 * mcpApi.streamMessage(sessionId, "Hello!", {
 *   onToken: (token) => console.log(token),
 *   onDone: (msg) => console.log("Complete:", msg)
 * });
 */
export const mcpApi = {
  // ===========================================================================
  // Server Management
  // ===========================================================================

  /**
   * Get all connected MCP servers
   * @returns Promise resolving to array of server information
   */
  getServers: (): Promise<ServerResponse[]> =>
    api.get<ServerResponse[]>('/servers').then(res => res.data),

  /**
   * Add and connect to MCP servers
   * @param configs - Array of server configurations
   * @returns Promise resolving to array of connected server info
   */
  addServers: (configs: ServerConfig[]): Promise<ServerResponse[]> =>
    api.post<ServerResponse[]>('/servers/add', configs).then(res => res.data),

  /**
   * Remove and disconnect from an MCP server
   * @param name - Name of the server to remove
   * @returns Promise resolving when server is removed
   */
  removeServer: (name: string): Promise<{ message: string }> =>
    api.delete(`/servers/${name}`).then(res => res.data),

  // ===========================================================================
  // Tools
  // ===========================================================================

  /**
   * Get all available tools from all connected servers
   * @returns Promise resolving to array of tool definitions
   */
  getTools: (): Promise<Tool[]> =>
    api.get<Tool[]>('/tools').then(res => res.data),

  // ===========================================================================
  // Session Management
  // ===========================================================================

  /**
   * Create a new chat session
   * @returns Promise resolving to the new session ID
   */
  createSession: (): Promise<{ session_id: string }> =>
    api.post<{ session_id: string }>('/sessions').then(res => res.data),

  /**
   * Get all chat sessions
   * @returns Promise resolving to array of sessions
   */
  getSessions: (): Promise<ChatSession[]> =>
    api.get<ChatSession[]>('/sessions').then(res => res.data),

  /**
   * Get message history for a session
   * @param sessionId - ID of the session
   * @returns Promise resolving to array of messages
   */
  getSessionHistory: (sessionId: string): Promise<Message[]> =>
    api.get<Message[]>(`/sessions/${sessionId}/history`).then(res => res.data),

  // ===========================================================================
  // Chat (Non-streaming)
  // ===========================================================================

  /**
   * Initialize chat configuration
   * @param config - Chat configuration options
   * @deprecated Use streamMessage instead for better UX
   */
  initChat: (config: { model?: string; api_key?: string; system_prompt?: string }): Promise<unknown> =>
    api.post('/chat/init', config).then(res => res.data),

  /**
   * Send a message and wait for complete response (non-streaming)
   * @param sessionId - ID of the session
   * @param message - Message text to send
   * @returns Promise resolving to complete response
   */
  sendMessage: (sessionId: string, message: string): Promise<ChatResponse> =>
    api.post<ChatResponse>(`/chat/${sessionId}`, { message }).then(res => res.data),

  // ===========================================================================
  // Chat (Streaming via SSE)
  // ===========================================================================

  /**
   * Send a message and receive streaming response via SSE
   * 
   * This function establishes a Server-Sent Events connection to receive
   * real-time updates including:
   * - Token-by-token text streaming
   * - Tool call notifications
   * - Tool execution results
   * - Completion/error events
   * 
   * @param sessionId - ID of the chat session
   * @param message - Message text to send
   * @param callbacks - Event callbacks for handling stream events
   * @returns EventSource instance (caller should close on component unmount)
   * 
   * @example
   * const eventSource = mcpApi.streamMessage(sessionId, "What is React?", {
   *   onToken: (token) => {
   *     setContent(prev => prev + token);
   *   },
   *   onToolCall: (call) => {
   *     console.log(`Calling ${call.server}.${call.tool}`);
   *   },
   *   onDone: (fullMessage) => {
   *     console.log("Stream complete!");
   *   },
   *   onError: (error) => {
   *     console.error("Error:", error);
   *   }
   * });
   * 
   * // Don't forget to close on cleanup!
   * // eventSource.close();
   */
  streamMessage: (sessionId: string, message: string, callbacks: StreamCallbacks): EventSource => {
    const encodedMessage = encodeURIComponent(message);
    const url = `${API_BASE_URL}/chat/${sessionId}/stream?message=${encodedMessage}`;

    console.log('[SSE] Connecting to:', url);
    const eventSource = new EventSource(url);

    // Connection opened
    eventSource.onopen = () => {
      console.log('[SSE] Connection established');
      callbacks.onConnected?.();
    };

    // Handle incoming messages
    eventSource.onmessage = (event) => {
      console.log('[SSE] Received event:', event.data);

      try {
        const data = JSON.parse(event.data);

        switch (data.type) {
          case 'token':
            // Text token from LLM
            callbacks.onToken?.(data.content);
            break;

          case 'tool_call':
            // LLM is calling a tool
            console.log('[SSE] Tool call:', data.content);
            callbacks.onToolCall?.(data.content);
            break;

          case 'tool_result':
            // Tool execution completed
            console.log('[SSE] Tool result:', data.content);
            callbacks.onToolResult?.(data.content);
            break;

          case 'done':
            // Stream completed successfully
            console.log('[SSE] Stream complete');
            callbacks.onDone?.(data.content);
            eventSource.close();
            break;

          case 'error':
            // Error occurred
            console.error('[SSE] Error event:', data.content);
            callbacks.onError?.(data.content);
            eventSource.close();
            break;

          default:
            console.log('[SSE] Unknown event type:', data.type, data);
        }
      } catch (error) {
        console.error('[SSE] Failed to parse event:', error);
        console.error('[SSE] Raw data:', event.data);
      }
    };

    // Handle connection errors
    eventSource.onerror = (error) => {
      console.error('[SSE] Connection error:', error);
      console.log('[SSE] ReadyState:', eventSource.readyState);

      // ReadyState values:
      // 0 = CONNECTING (trying to reconnect)
      // 1 = OPEN (connected)
      // 2 = CLOSED (connection closed)

      if (eventSource.readyState === EventSource.CLOSED) {
        console.log('[SSE] Connection was closed by server');
      } else if (eventSource.readyState === EventSource.CONNECTING) {
        console.log('[SSE] Attempting to reconnect...');
        // EventSource auto-reconnects, but we close it to prevent loops
      } else {
        callbacks.onError?.('Connection error - please try again');
      }

      eventSource.close();
    };

    return eventSource;
  },

  // ===========================================================================
  // Utility
  // ===========================================================================

  /**
   * Reset the chat manager state
   * @deprecated May be removed in future versions
   */
  reset: (): Promise<unknown> =>
    api.post('/reset').then(res => res.data),
};
