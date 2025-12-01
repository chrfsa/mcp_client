import React, { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Send, Bot, User, Terminal, Loader2 } from 'lucide-react';
import { mcpApi } from '../lib/api';
import type { Message } from '../types';
import { cn } from '../lib/utils';
import ReactMarkdown from 'react-markdown';

export function ChatInterface() {
    const { sessionId } = useParams<{ sessionId: string }>();
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (sessionId) {
            loadHistory(sessionId);
        }
    }, [sessionId]);

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    const loadHistory = async (id: string) => {
        try {
            const history = await mcpApi.getSessionHistory(id);
            setMessages(history);
        } catch (error) {
            console.error('Failed to load history:', error);
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || !sessionId || isLoading) return;

        const userMsg: Message = { role: 'user', content: input, timestamp: new Date().toISOString() };
        setMessages(prev => [...prev, userMsg]);
        setInput('');
        setIsLoading(true);

        try {
            const response = await mcpApi.sendMessage(sessionId, userMsg.content || '');

            const assistantMsg: Message = {
                role: 'assistant',
                content: response.message,
                timestamp: new Date().toISOString()
            };

            setMessages(prev => [...prev, assistantMsg]);

            if (response.tool_calls_count > 0) {
                loadHistory(sessionId);
            }

        } catch (error) {
            console.error('Failed to send message:', error);
            setMessages(prev => [...prev, {
                role: 'assistant',
                content: 'Error: Failed to get response from server.',
                timestamp: new Date().toISOString()
            }]);
        } finally {
            setIsLoading(false);
        }
    };

    if (!sessionId) {
        return (
            <div className="flex items-center justify-center h-full text-muted-foreground">
                Select a chat or start a new one
            </div>
        );
    }

    return (
        <div className="flex flex-col h-full max-w-4xl mx-auto w-full">
            {/* Messages Area */}
            <div className="flex-1 overflow-y-auto p-4 space-y-6">
                {messages.map((msg, idx) => (
                    <div
                        key={idx}
                        className={cn(
                            "flex gap-4 max-w-3xl mx-auto",
                            msg.role === 'user' ? "flex-row-reverse" : "flex-row"
                        )}
                    >
                        {/* Avatar */}
                        <div className={cn(
                            "w-8 h-8 rounded-full flex items-center justify-center shrink-0",
                            msg.role === 'user' ? "bg-primary text-primary-foreground" :
                                msg.role === 'assistant' ? "bg-secondary text-secondary-foreground" :
                                    "bg-muted text-muted-foreground"
                        )}>
                            {msg.role === 'user' ? <User size={16} /> :
                                msg.role === 'assistant' ? <Bot size={16} /> :
                                    <Terminal size={16} />}
                        </div>

                        {/* Content */}
                        <div className={cn(
                            "flex flex-col gap-1 min-w-0",
                            msg.role === 'user' ? "items-end" : "items-start"
                        )}>
                            <div className={cn(
                                "rounded-lg px-4 py-2 shadow-sm text-sm",
                                msg.role === 'user'
                                    ? "bg-primary text-primary-foreground"
                                    : msg.role === 'assistant'
                                        ? "bg-card border"
                                        : "bg-muted font-mono text-xs"
                            )}>
                                {msg.role === 'tool' ? (
                                    <div className="whitespace-pre-wrap break-words">
                                        <div className="font-bold mb-1 opacity-70">Tool Output ({msg.name})</div>
                                        {msg.content}
                                    </div>
                                ) : (
                                    <div className="prose prose-sm dark:prose-invert max-w-none break-words">
                                        <ReactMarkdown>{msg.content || ''}</ReactMarkdown>
                                    </div>
                                )}
                            </div>
                            <span className="text-[10px] text-muted-foreground opacity-50 px-1">
                                {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : ''}
                            </span>
                        </div>
                    </div>
                ))}

                {isLoading && (
                    <div className="flex gap-4 max-w-3xl mx-auto">
                        <div className="w-8 h-8 rounded-full bg-secondary text-secondary-foreground flex items-center justify-center shrink-0">
                            <Loader2 size={16} className="animate-spin" />
                        </div>
                        <div className="bg-card border rounded-lg px-4 py-2 shadow-sm text-sm text-muted-foreground">
                            Thinking...
                        </div>
                    </div>
                )}
                <div ref={messagesEndRef} />
            </div>

            {/* Input Area */}
            <div className="p-4 border-t bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
                <form onSubmit={handleSubmit} className="max-w-3xl mx-auto relative">
                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder="Type a message..."
                        className="w-full bg-muted/50 border rounded-full pl-4 pr-12 py-3 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                        disabled={isLoading}
                    />
                    <button
                        type="submit"
                        disabled={!input.trim() || isLoading}
                        className="absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-primary text-primary-foreground rounded-full hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                        <Send size={18} />
                    </button>
                </form>
            </div>
        </div>
    );
}
