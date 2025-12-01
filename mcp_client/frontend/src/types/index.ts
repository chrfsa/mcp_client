export interface ServerConfig {
    name: string;
    transport: 'stdio' | 'sse' | 'streamable_http';
    command?: string;
    args?: string[];
    env?: Record<string, string>;
    cwd?: string;
    url?: string;
    headers?: Record<string, string>;
    timeout?: number;
}

export interface ToolInfo {
    name: string;
    description?: string;
    input_schema?: any;
}

export interface ServerResponse {
    name: string;
    transport: string;
    tools_count: number;
    tools: ToolInfo[];
    connected_at: string;
}

export interface Tool {
    server_name: string;
    tool_name: string;
    full_name: string;
    description: string;
}

export interface Message {
    role: 'user' | 'assistant' | 'system' | 'tool';
    content?: string;
    tool_calls?: any[];
    tool_call_id?: string;
    name?: string;
    timestamp?: string;
}

export interface ChatSession {
    id: string;
    created_at: string;
    message_count: number;
}

export interface ChatResponse {
    message: string;
    tool_calls_count: number;
    iterations: number;
}
