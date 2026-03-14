import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { UserCircle, Edit3, Trash2, Plus, X, Save, MessageSquare } from 'lucide-react';

export const PersonaView = () => {
    const [personas, setPersonas] = useState([]);
    const [editingPersona, setEditingPersona] = useState(null);
    const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
    const [newPersona, setNewPersona] = useState({ name: '', content: '' });
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        fetchPersonas();
    }, []);

    const fetchPersonas = async () => {
        try {
            const res = await fetch('http://localhost:8000/personas');
            const names = await res.json();
            const detailed = await Promise.all(names.map(async name => {
                const r = await fetch(`http://localhost:8000/personas/${name}`);
                return await r.json();
            }));
            setPersonas(detailed);
            setIsLoading(false);
        } catch (err) {
            console.error('Failed to fetch personas:', err);
            setIsLoading(false);
        }
    };

    const handleSave = async (persona) => {
        try {
            await fetch('http://localhost:8000/personas', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(persona)
            });
            setEditingPersona(null);
            setIsCreateModalOpen(false);
            setNewPersona({ name: '', content: '' });
            fetchPersonas();
        } catch (err) {
            console.error('Failed to save persona:', err);
        }
    };

    const handleDelete = async (name) => {
        if (!confirm(`Are you sure you want to delete '${name}'?`)) return;
        try {
            await fetch(`http://localhost:8000/personas/${name}`, { method: 'DELETE' });
            fetchPersonas();
        } catch (err) {
            console.error('Failed to delete persona:', err);
        }
    };

    return (
        <div className="flex-1 p-8 overflow-y-auto chat-scroll bg-slate-950/20">
            <div className="max-w-5xl mx-auto">
                <header className="flex items-center justify-between mb-12">
                    <div>
                        <h1 className="text-4xl font-black tracking-tighter italic bg-gradient-to-r from-white to-slate-500 bg-clip-text text-transparent">
                            PERSONA ARCHIVE
                        </h1>
                        <p className="text-slate-500 text-xs font-bold uppercase tracking-[0.3em] mt-2">Neural Identity Configuration</p>
                    </div>
                    <button 
                        onClick={() => setIsCreateModalOpen(true)}
                        className="bg-sky-500 hover:bg-sky-400 text-slate-950 px-6 py-3 rounded-2xl font-bold text-xs uppercase tracking-widest flex items-center transition-all shadow-lg shadow-sky-500/20"
                    >
                        <Plus className="w-4 h-4 mr-2" />
                        Create Persona
                    </button>
                </header>

                {isLoading ? (
                    <div className="flex items-center justify-center py-20">
                        <div className="w-8 h-8 border-4 border-sky-500/20 border-t-sky-500 rounded-full animate-spin" />
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {personas.map((p) => (
                            <motion.div 
                                key={p.name}
                                layoutId={p.name}
                                className="glass-panel p-6 rounded-3xl border border-slate-800 hover:border-sky-500/30 transition-all group flex flex-col h-64"
                            >
                                <div className="flex items-start justify-between mb-4">
                                    <div className="w-12 h-12 rounded-2xl bg-sky-500/10 flex items-center justify-center group-hover:bg-sky-500/20 transition-colors">
                                        <UserCircle className="w-6 h-6 text-sky-400" />
                                    </div>
                                    <div className="flex space-x-1">
                                        <button 
                                            onClick={() => setEditingPersona(p)}
                                            className="p-2 text-slate-500 hover:text-sky-400 hover:bg-sky-400/10 rounded-xl transition-all"
                                        >
                                            <Edit3 className="w-4 h-4" />
                                        </button>
                                        <button 
                                            onClick={() => handleDelete(p.name)}
                                            className="p-2 text-slate-500 hover:text-red-400 hover:bg-red-400/10 rounded-xl transition-all"
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </div>
                                </div>
                                <h3 className="text-lg font-bold mb-2 truncate">{p.name}</h3>
                                <p className="text-slate-500 text-[11px] leading-relaxed line-clamp-4 italic flex-1">
                                    {p.content}
                                </p>
                            </motion.div>
                        ))}
                    </div>
                )}
            </div>

            {/* Modals and Overlays */}
            <AnimatePresence>
                {(editingPersona || isCreateModalOpen) && (
                    <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 backdrop-blur-md bg-slate-950/60">
                        <motion.div 
                            initial={{ opacity: 0, scale: 0.9, y: 20 }}
                            animate={{ opacity: 1, scale: 1, y: 0 }}
                            exit={{ opacity: 0, scale: 0.9, y: 20 }}
                            className="bg-slate-900 border border-slate-800 w-full max-w-2xl rounded-[2rem] shadow-2xl overflow-hidden flex flex-col max-h-[80vh]"
                        >
                            <div className="p-8 border-b border-slate-800 flex items-center justify-between">
                                <div>
                                    <h2 className="text-2xl font-black italic tracking-tighter">
                                        {editingPersona ? `EDIT: ${editingPersona.name}` : 'NEW PERSONA'}
                                    </h2>
                                    <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mt-1">Configure Behavior Core</p>
                                </div>
                                <button onClick={() => { setEditingPersona(null); setIsCreateModalOpen(false); }} className="text-slate-500 hover:text-white">
                                    <X className="w-6 h-6" />
                                </button>
                            </div>
                            
                            <div className="p-8 space-y-6 flex-1 overflow-y-auto chat-scroll">
                                {!editingPersona && (
                                    <div className="space-y-2">
                                        <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest ml-1">Identity Name</label>
                                        <input 
                                            type="text"
                                            placeholder="e.g. MasterCoder, PirateGoku..."
                                            className="w-full bg-slate-950/50 border border-slate-800 rounded-2xl px-6 py-4 text-sm focus:outline-none focus:border-sky-500/50 transition-all font-bold placeholder-slate-700"
                                            value={newPersona.name}
                                            onChange={(e) => setNewPersona({...newPersona, name: e.target.value})}
                                        />
                                    </div>
                                )}
                                <div className="space-y-2 flex-1 flex flex-col">
                                    <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest ml-1">System Prompt / Directive</label>
                                    <textarea 
                                        placeholder="Define how Goku should act, speak, and respond..."
                                        className="w-full h-64 bg-slate-950/50 border border-slate-800 rounded-2xl px-6 py-4 text-sm focus:outline-none focus:border-sky-500/50 transition-all font-mono leading-relaxed placeholder-slate-700 resize-none"
                                        value={editingPersona ? editingPersona.content : newPersona.content}
                                        onChange={(e) => {
                                            if (editingPersona) setEditingPersona({...editingPersona, content: e.target.value});
                                            else setNewPersona({...newPersona, content: e.target.value});
                                        }}
                                    />
                                </div>
                            </div>

                            <div className="p-8 bg-slate-900/50 border-t border-slate-800 flex items-center justify-end space-x-4">
                                <button 
                                    onClick={() => { setEditingPersona(null); setIsCreateModalOpen(false); }}
                                    className="px-6 py-3 rounded-2xl font-bold text-[10px] uppercase tracking-widest text-slate-400 hover:text-white transition-all"
                                >
                                    Abort
                                </button>
                                <button 
                                    onClick={() => handleSave(editingPersona || newPersona)}
                                    className="bg-sky-500 hover:bg-sky-400 text-slate-950 px-8 py-3 rounded-2xl font-bold text-[10px] uppercase tracking-widest flex items-center transition-all"
                                >
                                    <Save className="w-4 h-4 mr-2" />
                                    Synchronize Persona
                                </button>
                            </div>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>
        </div>
    );
};
