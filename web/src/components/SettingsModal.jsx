import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Save, Key, Globe, Cpu, Github, Settings as SettingsIcon, MessageSquare, Send } from 'lucide-react';
import axios from 'axios';

export const SettingsModal = ({ isOpen, onClose, onSave }) => {
    const [config, setConfig] = useState({
        OPENAI_API_KEY: '',
        ANTHROPIC_API_KEY: '',
        GOOGLE_API_KEY: '',
        GEMINI_API_KEY: '',
        GITHUB_TOKEN: '',
        TELEGRAM_BOT_TOKEN: '',
        GOKU_MODEL: 'default',
        OLLAMA_BASE_URL: 'http://localhost:11434',
        WHATSAPP_CONNECTED: false
    });
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (isOpen) {
            fetchConfig();
        }
    }, [isOpen]);

    const fetchConfig = async () => {
        try {
            const host = window.location.hostname;
            const resp = await axios.get(`http://${host}:8000/config`);
            setConfig(resp.data);
        } catch (err) {
            console.error('Failed to fetch config', err);
        }
    };

    const handleSave = async () => {
        setLoading(true);
        try {
            const host = window.location.hostname;
            await axios.post(`http://${host}:8000/config`, config);
            onSave?.();
            onClose();
        } catch (err) {
            alert('Save failed: ' + err.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <AnimatePresence>
            {isOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        onClick={onClose}
                        className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm"
                    />

                    <motion.div
                        initial={{ opacity: 0, scale: 0.9, y: 20 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.9, y: 20 }}
                        className="w-full max-w-xl bg-slate-900 border border-slate-800 rounded-3xl shadow-2xl overflow-hidden relative z-10"
                    >
                        <div className="px-8 py-6 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
                            <div className="flex items-center space-x-3">
                                <SettingsIcon className="w-5 h-5 text-sky-400" />
                                <h2 className="text-xl font-bold tracking-tight">Goku Configuration</h2>
                            </div>
                            <button
                                onClick={onClose}
                                className="p-2 hover:bg-slate-800 rounded-xl text-slate-500 hover:text-slate-200 transition-colors"
                            >
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        <div className="px-8 py-8 space-y-6 max-h-[60vh] overflow-y-auto">
                            <div className="space-y-4">
                                <label className="flex items-center space-x-2 text-xs font-bold text-slate-500 uppercase tracking-widest">
                                    <Key className="w-3 h-3" />
                                    <span>AI Provider Keys</span>
                                </label>

                                <div className="grid gap-4">
                                    <div className="space-y-1.5">
                                        <span className="text-[11px] text-slate-400">OpenAI API Key</span>
                                        <input
                                            type="password"
                                            value={config.OPENAI_API_KEY}
                                            onChange={(e) => setConfig({ ...config, OPENAI_API_KEY: e.target.value })}
                                            className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-sm focus:border-sky-500/50 outline-none transition-colors"
                                            placeholder="sk-..."
                                        />
                                    </div>
                                    <div className="space-y-1.5">
                                        <span className="text-[11px] text-slate-400">GitHub Marketplace Token</span>
                                        <input
                                            type="password"
                                            value={config.GITHUB_TOKEN}
                                            onChange={(e) => setConfig({ ...config, GITHUB_TOKEN: e.target.value })}
                                            className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-sm focus:border-sky-500/50 outline-none transition-colors"
                                            placeholder="ghp_..."
                                        />
                                    </div>
                                    <div className="space-y-1.5">
                                        <span className="text-[11px] text-slate-400">Telegram Bot Token</span>
                                        <div className="flex space-x-2">
                                            <input
                                                type="password"
                                                value={config.TELEGRAM_BOT_TOKEN}
                                                onChange={(e) => setConfig({ ...config, TELEGRAM_BOT_TOKEN: e.target.value })}
                                                className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-sm focus:border-sky-500/50 outline-none transition-colors"
                                                placeholder="123456:ABC-..."
                                            />
                                            <div className="flex items-center px-3 bg-slate-800 rounded-xl border border-slate-700">
                                                <Send className="w-3.5 h-3.5 text-sky-400 mr-2" />
                                                <span className="text-[10px] font-bold text-sky-400 uppercase">Active</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div className="space-y-4 pt-4 border-t border-slate-800/50">
                                <label className="flex items-center space-x-2 text-xs font-bold text-slate-500 uppercase tracking-widest">
                                    <MessageSquare className="w-3 h-3" />
                                    <span>Communication Channels</span>
                                </label>
                                <div className="space-y-3">
                                    <div className="flex flex-col space-y-3 p-4 bg-slate-950 border border-slate-800 rounded-2xl">
                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center space-x-3">
                                                <div className="w-8 h-8 rounded-lg bg-green-500/10 flex items-center justify-center">
                                                    <MessageSquare className="w-4 h-4 text-green-500" />
                                                </div>
                                                <div>
                                                    <p className="text-sm font-bold text-slate-200">WhatsApp Integration</p>
                                                    <p className="text-[10px] text-slate-500">QR-code based linking</p>
                                                </div>
                                            </div>
                                            <div className={`px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-tighter ${config.WHATSAPP_CONNECTED ? 'bg-green-500/20 text-green-400' : 'bg-amber-500/20 text-amber-400'}`}>
                                                {config.WHATSAPP_CONNECTED ? '● Connected' : '○ Not Linked'}
                                            </div>
                                        </div>
                                        
                                        {config.WHATSAPP_CONNECTED && (
                                            <div className="pt-3 border-t border-slate-800 space-y-4">
                                                <div className="space-y-1.5">
                                                    <span className="text-[11px] text-slate-400">DM Policy</span>
                                                    <select 
                                                        value={config.WHATSAPP_DM_POLICY || 'allowlist'}
                                                        onChange={(e) => setConfig({...config, WHATSAPP_DM_POLICY: e.target.value})}
                                                        className="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-2 text-sm focus:border-sky-500/50 outline-none"
                                                    >
                                                        <option value="allowlist">Allowlist Only</option>
                                                        <option value="open">Open (Everyone)</option>
                                                        <option value="disabled">Disabled</option>
                                                    </select>
                                                </div>
                                                
                                                {config.WHATSAPP_DM_POLICY === 'allowlist' && (
                                                    <div className="space-y-1.5">
                                                        <span className="text-[11px] text-slate-400">Allow From (Comma separated numbers)</span>
                                                        <input 
                                                            type="text"
                                                            value={config.WHATSAPP_ALLOW_FROM || ''}
                                                            onChange={(e) => setConfig({...config, WHATSAPP_ALLOW_FROM: e.target.value})}
                                                            className="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-2 text-sm focus:border-sky-500/50 outline-none"
                                                            placeholder="+233201234567, ..."
                                                        />
                                                    </div>
                                                )}

                                                <div className="space-y-1.5">
                                                    <span className="text-[11px] text-slate-400">Group Policy</span>
                                                    <select 
                                                        value={config.WHATSAPP_GROUP_POLICY || 'mentions'}
                                                        onChange={(e) => setConfig({...config, WHATSAPP_GROUP_POLICY: e.target.value})}
                                                        className="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-2 text-sm focus:border-sky-500/50 outline-none"
                                                    >
                                                        <option value="mentions">Mentions Only</option>
                                                        <option value="open">Open (All)</option>
                                                        <option value="disabled">Disabled</option>
                                                    </select>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>

                            <div className="space-y-4 pt-4 border-t border-slate-800/50">
                                <label className="flex items-center space-x-2 text-xs font-bold text-slate-500 uppercase tracking-widest">
                                    <Cpu className="w-3 h-3" />
                                    <span>Model Engine</span>
                                </label>
                                <div className="space-y-1.5">
                                    <span className="text-[11px] text-slate-400">Preferred Model Override</span>
                                    <input
                                        type="text"
                                        value={config.GOKU_MODEL}
                                        onChange={(e) => setConfig({ ...config, GOKU_MODEL: e.target.value })}
                                        className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-sm focus:border-sky-500/50 outline-none transition-colors"
                                        placeholder="default (e.g. github/gpt-4o)"
                                    />
                                </div>
                                <div className="space-y-1.5">
                                    <span className="text-[11px] text-slate-400">Owner Phone Number (E.164)</span>
                                    <input
                                        type="text"
                                        value={config.GOKU_OWNER_NUMBER || ''}
                                        onChange={(e) => setConfig({ ...config, GOKU_OWNER_NUMBER: e.target.value })}
                                        className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-sm focus:border-sky-500/50 outline-none transition-colors"
                                        placeholder="+23320XXXXXXX"
                                    />
                                </div>
                            </div>

                            <div className="space-y-4 pt-4 border-t border-slate-800/50">
                                <label className="flex items-center space-x-2 text-xs font-bold text-slate-500 uppercase tracking-widest">
                                    <Globe className="w-3 h-3" />
                                    <span>Local Infrastructure</span>
                                </label>
                                <div className="space-y-1.5">
                                    <span className="text-[11px] text-slate-400">Ollama Base URL</span>
                                    <input
                                        type="text"
                                        value={config.OLLAMA_BASE_URL}
                                        onChange={(e) => setConfig({ ...config, OLLAMA_BASE_URL: e.target.value })}
                                        className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-sm focus:border-sky-500/50 outline-none transition-colors"
                                    />
                                </div>
                            </div>
                        </div>

                        <div className="px-8 py-6 border-t border-slate-800 bg-slate-900/50 flex items-center justify-end space-x-4">
                            <button
                                onClick={onClose}
                                className="px-5 py-2 text-sm font-bold text-slate-500 hover:text-slate-200 transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleSave}
                                disabled={loading}
                                className="px-6 py-2 bg-sky-500 text-slate-950 rounded-xl text-sm font-bold flex items-center space-x-2 hover:bg-sky-400 transition-all active:scale-95 shadow-lg shadow-sky-500/20 disabled:opacity-50"
                            >
                                {loading ? <div className="w-4 h-4 border-2 border-slate-950 border-t-transparent rounded-full animate-spin" /> : <Save className="w-4 h-4" />}
                                <span>{loading ? 'Saving...' : 'Save Configuration'}</span>
                            </button>
                        </div>
                    </motion.div>
                </div>
            )}
        </AnimatePresence>
    );
};
