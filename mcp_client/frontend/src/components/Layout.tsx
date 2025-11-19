import React, { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { MessageSquare, Settings, Plus, Menu, X } from 'lucide-react';
import { cn } from '../lib/utils';
import { mcpApi } from '../lib/api';
import type { ChatSession } from '../types';
import { SettingsModal } from './SettingsModal';

interface LayoutProps {
    children: React.ReactNode;
}

export function Layout({ children }: LayoutProps) {
    const [sessions, setSessions] = useState<ChatSession[]>([]);
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);
    const [isSettingsOpen, setIsSettingsOpen] = useState(false);
    const location = useLocation();
    const navigate = useNavigate();

    useEffect(() => {
        loadSessions();
    }, []);

    const loadSessions = async () => {
        try {
            const data = await mcpApi.getSessions();
            setSessions(data);
        } catch (error) {
            console.error('Failed to load sessions:', error);
        }
    };

    const handleNewChat = async () => {
        try {
            const { session_id } = await mcpApi.createSession();
            await loadSessions();
            navigate(`/chat/${session_id}`);
        } catch (error) {
            console.error('Failed to create session:', error);
        }
    };

    return (
        <div className="flex h-screen bg-background text-foreground overflow-hidden">
            <SettingsModal isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />

            {/* Mobile Sidebar Toggle */}
            <button
                className="md:hidden fixed top-4 left-4 z-50 p-2 bg-card border rounded-md shadow-sm"
                onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            >
                {isSidebarOpen ? <X size={20} /> : <Menu size={20} />}
            </button>

            {/* Sidebar */}
            <aside
                className={cn(
                    "fixed inset-y-0 left-0 z-40 w-64 bg-card border-r transform transition-transform duration-200 ease-in-out md:relative md:translate-x-0",
                    !isSidebarOpen && "-translate-x-full"
                )}
            >
                <div className="flex flex-col h-full">
                    <div className="p-4 border-b flex items-center justify-between">
                        <h1 className="font-bold text-xl tracking-tight">MCP Client</h1>
                        <button
                            onClick={() => setIsSettingsOpen(true)}
                            className="p-2 hover:bg-accent rounded-md transition-colors"
                            title="Settings"
                        >
                            <Settings size={20} />
                        </button>
                    </div>

                    <div className="p-4">
                        <button
                            onClick={handleNewChat}
                            className="w-full flex items-center justify-center gap-2 bg-primary text-primary-foreground py-2 px-4 rounded-md hover:bg-primary/90 transition-colors font-medium shadow-sm"
                        >
                            <Plus size={18} />
                            New Chat
                        </button>
                    </div>

                    <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1">
                        <div className="px-2 py-1 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                            Recent Chats
                        </div>
                        {sessions.map((session) => (
                            <Link
                                key={session.id}
                                to={`/chat/${session.id}`}
                                className={cn(
                                    "flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors group",
                                    location.pathname === `/chat/${session.id}`
                                        ? "bg-accent text-accent-foreground font-medium"
                                        : "hover:bg-accent/50 text-muted-foreground hover:text-foreground"
                                )}
                            >
                                <MessageSquare size={16} />
                                <span className="truncate flex-1">
                                    {new Date(session.created_at).toLocaleString()}
                                </span>
                                <span className="text-xs opacity-50 group-hover:opacity-100">
                                    {session.message_count}
                                </span>
                            </Link>
                        ))}
                    </div>

                    <div className="p-4 border-t text-xs text-muted-foreground text-center">
                        v2.0.0 • Production Ready
                    </div>
                </div>
            </aside>

            {/* Main Content */}
            <main className="flex-1 flex flex-col h-full overflow-hidden relative w-full">
                {children}
            </main>
        </div>
    );
}
