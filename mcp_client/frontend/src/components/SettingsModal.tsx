import React, { useEffect, useState } from 'react';
import { Trash2, Plus, Save, Server, Terminal, Globe, AlertCircle, X, ChevronDown, ChevronRight, Wrench } from 'lucide-react';
import { mcpApi } from '../lib/api';
import type { ServerConfig, ServerResponse } from '../types';

interface SettingsModalProps {
    isOpen: boolean;
    onClose: () => void;
}

export function SettingsModal({ isOpen, onClose }: SettingsModalProps) {
    const [servers, setServers] = useState<ServerResponse[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Form state
    const [newServer, setNewServer] = useState<Partial<ServerConfig>>({
        transport: 'stdio',
        name: '',
    });
    const [envVars, setEnvVars] = useState<{ key: string; value: string }[]>([]);
    const [headers, setHeaders] = useState<{ key: string; value: string }[]>([]);
    const [expandedServers, setExpandedServers] = useState<Set<string>>(new Set());

    useEffect(() => {
        if (isOpen) {
            loadServers();
        }
    }, [isOpen]);

    const loadServers = async () => {
        try {
            const data = await mcpApi.getServers();
            setServers(data);
        } catch (err) {
            console.error('Failed to load servers:', err);
            setError('Failed to load servers');
        }
    };

    const handleAddServer = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setIsLoading(true);

        try {
            // Validate
            if (!newServer.name) throw new Error('Name is required');
            if (newServer.transport === 'stdio' && (!newServer.command || !newServer.args)) {
                throw new Error('Command and args are required for stdio');
            }
            if ((newServer.transport === 'sse' || newServer.transport === 'streamable_http') && !newServer.url) {
                throw new Error('URL is required for HTTP/SSE');
            }

            // Parse args if string
            const configToAdd: ServerConfig = {
                ...newServer as ServerConfig,
                args: typeof newServer.args === 'string' ? (newServer.args as string).split(' ') : newServer.args,
                env: envVars.length > 0
                    ? envVars.reduce((acc, curr) => curr.key ? ({ ...acc, [curr.key]: curr.value }) : acc, {})
                    : undefined,
                headers: headers.length > 0
                    ? headers.reduce((acc, curr) => curr.key ? ({ ...acc, [curr.key]: curr.value }) : acc, {})
                    : undefined
            };

            await mcpApi.addServers([configToAdd]);
            await loadServers();
            setNewServer({ transport: 'stdio', name: '' }); // Reset form
            setEnvVars([]);
            setHeaders([]);
        } catch (err: any) {
            setError(err.message || 'Failed to add server');
        } finally {
            setIsLoading(false);
        }
    };

    const handleAddEnvVar = () => {
        setEnvVars([...envVars, { key: '', value: '' }]);
    };

    const handleRemoveEnvVar = (index: number) => {
        setEnvVars(envVars.filter((_, i) => i !== index));
    };

    const handleEnvVarChange = (index: number, field: 'key' | 'value', value: string) => {
        const newEnvVars = [...envVars];
        newEnvVars[index][field] = value;
        setEnvVars(newEnvVars);
    };

    const handleAddHeader = () => {
        setHeaders([...headers, { key: '', value: '' }]);
    };

    const handleRemoveHeader = (index: number) => {
        setHeaders(headers.filter((_, i) => i !== index));
    };

    const handleHeaderChange = (index: number, field: 'key' | 'value', value: string) => {
        const newHeaders = [...headers];
        newHeaders[index][field] = value;
        setHeaders(newHeaders);
    };

    const toggleServerExpansion = (serverName: string) => {
        const newExpanded = new Set(expandedServers);
        if (newExpanded.has(serverName)) {
            newExpanded.delete(serverName);
        } else {
            newExpanded.add(serverName);
        }
        setExpandedServers(newExpanded);
    };

    const handleRemoveServer = async (name: string) => {
        if (!confirm(`Are you sure you want to remove server "${name}"?`)) return;
        try {
            await mcpApi.removeServer(name);
            await loadServers();
        } catch (err) {
            console.error('Failed to remove server:', err);
            setError('Failed to remove server');
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
            <div className="bg-card border rounded-lg shadow-lg w-full max-w-3xl max-h-[90vh] flex flex-col">
                {/* Header */}
                <div className="flex items-center justify-between p-6 border-b">
                    <h2 className="text-2xl font-bold">MCP Settings</h2>
                    <button onClick={onClose} className="p-2 hover:bg-accent rounded-full transition-colors">
                        <X size={20} />
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-6 space-y-8">
                    {/* Add Server Form */}
                    <div className="bg-muted/30 border rounded-lg p-6">
                        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                            <Plus size={18} /> Add New Server
                        </h3>

                        {error && (
                            <div className="bg-destructive/10 text-destructive p-3 rounded-md mb-4 flex items-center gap-2 text-sm">
                                <AlertCircle size={16} />
                                {error}
                            </div>
                        )}

                        <form onSubmit={handleAddServer} className="space-y-4">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium mb-1">Name</label>
                                    <input
                                        type="text"
                                        value={newServer.name}
                                        onChange={e => setNewServer({ ...newServer, name: e.target.value })}
                                        className="w-full bg-background border rounded-md px-3 py-2 focus:ring-2 focus:ring-primary/50 outline-none"
                                        placeholder="e.g., weather-server"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium mb-1">Transport</label>
                                    <select
                                        value={newServer.transport}
                                        onChange={e => setNewServer({ ...newServer, transport: e.target.value as any })}
                                        className="w-full bg-background border rounded-md px-3 py-2 focus:ring-2 focus:ring-primary/50 outline-none"
                                    >
                                        <option value="stdio">STDIO (Local Process)</option>
                                        <option value="sse">SSE (Server Sent Events)</option>
                                        <option value="streamable_http">Streamable HTTP</option>
                                    </select>
                                </div>
                            </div>

                            {newServer.transport === 'stdio' ? (
                                <>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        <div>
                                            <label className="block text-sm font-medium mb-1">Command</label>
                                            <input
                                                type="text"
                                                value={newServer.command || ''}
                                                onChange={e => setNewServer({ ...newServer, command: e.target.value })}
                                                className="w-full bg-background border rounded-md px-3 py-2 focus:ring-2 focus:ring-primary/50 outline-none font-mono text-sm"
                                                placeholder="e.g., python, npx"
                                            />
                                        </div>
                                        <div>
                                            <label className="block text-sm font-medium mb-1">Arguments</label>
                                            <input
                                                type="text"
                                                value={Array.isArray(newServer.args) ? newServer.args.join(' ') : newServer.args || ''}
                                                onChange={e => setNewServer({ ...newServer, args: e.target.value.split(' ') })}
                                                className="w-full bg-background border rounded-md px-3 py-2 focus:ring-2 focus:ring-primary/50 outline-none font-mono text-sm"
                                                placeholder="e.g., script.py --flag"
                                            />
                                        </div>
                                    </div>

                                    <div className="space-y-2">
                                        <label className="block text-sm font-medium">Environment Variables</label>
                                        <div className="space-y-2">
                                            {envVars.map((env, index) => (
                                                <div key={index} className="flex gap-2">
                                                    <input
                                                        type="text"
                                                        placeholder="Key"
                                                        value={env.key}
                                                        onChange={(e) => handleEnvVarChange(index, 'key', e.target.value)}
                                                        className="flex-1 bg-background border rounded-md px-3 py-2 focus:ring-2 focus:ring-primary/50 outline-none text-sm font-mono"
                                                    />
                                                    <input
                                                        type="text"
                                                        placeholder="Value"
                                                        value={env.value}
                                                        onChange={(e) => handleEnvVarChange(index, 'value', e.target.value)}
                                                        className="flex-1 bg-background border rounded-md px-3 py-2 focus:ring-2 focus:ring-primary/50 outline-none text-sm font-mono"
                                                    />
                                                    <button
                                                        type="button"
                                                        onClick={() => handleRemoveEnvVar(index)}
                                                        className="p-2 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-md transition-colors"
                                                        title="Remove variable"
                                                    >
                                                        <Trash2 size={16} />
                                                    </button>
                                                </div>
                                            ))}
                                            <button
                                                type="button"
                                                onClick={handleAddEnvVar}
                                                className="text-sm text-primary hover:underline flex items-center gap-1"
                                            >
                                                <Plus size={14} /> Add Environment Variable
                                            </button>
                                        </div>
                                    </div>
                                </>
                            ) : (
                                <div>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                                        <div>
                                            <label className="block text-sm font-medium mb-1">URL</label>
                                            <input
                                                type="text"
                                                value={newServer.url || ''}
                                                onChange={e => setNewServer({ ...newServer, url: e.target.value })}
                                                className="w-full bg-background border rounded-md px-3 py-2 focus:ring-2 focus:ring-primary/50 outline-none"
                                                placeholder="https://api.example.com/sse"
                                            />
                                        </div>
                                        <div>
                                            <label className="block text-sm font-medium mb-1">Timeout (seconds)</label>
                                            <input
                                                type="number"
                                                value={newServer.timeout || ''}
                                                onChange={e => setNewServer({ ...newServer, timeout: e.target.value ? parseFloat(e.target.value) : undefined })}
                                                className="w-full bg-background border rounded-md px-3 py-2 focus:ring-2 focus:ring-primary/50 outline-none"
                                                placeholder="e.g., 30"
                                            />
                                        </div>
                                    </div>

                                    <div className="space-y-2">
                                        <label className="block text-sm font-medium">Headers</label>
                                        <div className="space-y-2">
                                            {headers.map((header, index) => (
                                                <div key={index} className="flex gap-2">
                                                    <input
                                                        type="text"
                                                        placeholder="Key"
                                                        value={header.key}
                                                        onChange={(e) => handleHeaderChange(index, 'key', e.target.value)}
                                                        className="flex-1 bg-background border rounded-md px-3 py-2 focus:ring-2 focus:ring-primary/50 outline-none text-sm font-mono"
                                                    />
                                                    <input
                                                        type="text"
                                                        placeholder="Value"
                                                        value={header.value}
                                                        onChange={(e) => handleHeaderChange(index, 'value', e.target.value)}
                                                        className="flex-1 bg-background border rounded-md px-3 py-2 focus:ring-2 focus:ring-primary/50 outline-none text-sm font-mono"
                                                    />
                                                    <button
                                                        type="button"
                                                        onClick={() => handleRemoveHeader(index)}
                                                        className="p-2 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-md transition-colors"
                                                        title="Remove header"
                                                    >
                                                        <Trash2 size={16} />
                                                    </button>
                                                </div>
                                            ))}
                                            <button
                                                type="button"
                                                onClick={handleAddHeader}
                                                className="text-sm text-primary hover:underline flex items-center gap-1"
                                            >
                                                <Plus size={14} /> Add Header
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            )}

                            <div className="flex justify-end pt-2">
                                <button
                                    type="submit"
                                    disabled={isLoading}
                                    className="bg-primary text-primary-foreground px-4 py-2 rounded-md hover:bg-primary/90 transition-colors flex items-center gap-2 font-medium disabled:opacity-50 text-sm"
                                >
                                    {isLoading ? 'Connecting...' : (
                                        <>
                                            <Save size={16} /> Save & Connect
                                        </>
                                    )}
                                </button>
                            </div>
                        </form>
                    </div>

                    {/* Server List */}
                    <div>
                        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                            <Server size={18} /> Connected Servers
                        </h3>

                        <div className="grid grid-cols-1 gap-3">
                            {servers.length === 0 ? (
                                <div className="text-center p-8 border border-dashed rounded-lg text-muted-foreground">
                                    No servers connected yet.
                                </div>
                            ) : (
                                servers.map(server => (
                                    <div key={server.name} className="bg-card border rounded-lg shadow-sm group hover:border-primary/50 transition-colors overflow-hidden">
                                        <div className="p-4 flex items-center justify-between">
                                            <div className="flex items-center gap-4">
                                                <div className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center text-secondary-foreground">
                                                    {server.transport === 'stdio' ? <Terminal size={20} /> : <Globe size={20} />}
                                                </div>
                                                <div>
                                                    <h3 className="font-semibold">{server.name}</h3>
                                                    <div className="text-sm text-muted-foreground flex gap-3">
                                                        <span className="uppercase text-xs font-bold bg-muted px-1.5 py-0.5 rounded">
                                                            {server.transport}
                                                        </span>
                                                        <button
                                                            onClick={() => toggleServerExpansion(server.name)}
                                                            className="hover:text-primary flex items-center gap-1 transition-colors"
                                                        >
                                                            <span>{server.tools_count} tools available</span>
                                                            {expandedServers.has(server.name) ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                                        </button>
                                                    </div>
                                                </div>
                                            </div>

                                            <button
                                                onClick={() => handleRemoveServer(server.name)}
                                                className="p-2 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-md transition-colors opacity-0 group-hover:opacity-100"
                                                title="Remove Server"
                                            >
                                                <Trash2 size={18} />
                                            </button>
                                        </div>

                                        {/* Tools List */}
                                        {expandedServers.has(server.name) && (
                                            <div className="bg-muted/30 border-t p-3 pl-16 text-sm">
                                                <h4 className="font-medium mb-2 flex items-center gap-2 text-muted-foreground">
                                                    <Wrench size={14} /> Available Tools
                                                </h4>
                                                {server.tools && server.tools.length > 0 ? (
                                                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                                        {server.tools.map((tool) => (
                                                            <div key={tool} className="bg-background border rounded px-2 py-1 font-mono text-xs text-muted-foreground">
                                                                {tool}
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <div className="text-muted-foreground italic">No tools listed</div>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                </div>

                {/* Footer */}
                <div className="p-4 border-t bg-muted/10 flex justify-end">
                    <button onClick={onClose} className="px-4 py-2 bg-secondary text-secondary-foreground rounded-md hover:bg-secondary/80 transition-colors text-sm font-medium">
                        Close
                    </button>
                </div>
            </div>
        </div>
    );
}
