import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Zap, Search, Box, ChevronRight, Terminal } from 'lucide-react';

export const SkillsView = () => {
    const [skills, setSkills] = useState([]);
    const [search, setSearch] = useState('');
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        fetchSkills();
    }, []);

    const fetchSkills = async () => {
        try {
            const host = window.location.hostname;
            const res = await fetch(`http://${host}:8000/skills`);
            const data = await res.json();
            setSkills(data);
            setIsLoading(false);
        } catch (err) {
            console.error('Failed to fetch skills:', err);
            setIsLoading(false);
        }
    };

    const filteredSkills = skills.filter(s => 
        s.name.toLowerCase().includes(search.toLowerCase()) || 
        s.description.toLowerCase().includes(search.toLowerCase())
    );

    return (
        <div className="flex-1 p-8 overflow-y-auto chat-scroll bg-slate-950/20">
            <div className="max-w-6xl mx-auto">
                <header className="mb-12">
                    <h1 className="text-4xl font-black tracking-tighter italic bg-gradient-to-r from-white to-slate-500 bg-clip-text text-transparent mb-2">
                        SKILL ARCHITECTURE
                    </h1>
                    <p className="text-slate-500 text-[10px] font-bold uppercase tracking-[0.4em] mb-8">Active Neural Capabilities & Toolsets</p>
                    
                    <div className="relative max-w-md group">
                        <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-600 group-focus-within:text-sky-500 transition-colors" />
                        <input 
                            type="text"
                            placeholder="Query Capability Matrix..."
                            className="w-full bg-slate-900/50 border border-slate-800 rounded-2xl pl-12 pr-6 py-4 text-xs font-bold tracking-widest uppercase focus:outline-none focus:border-sky-500/50 transition-all placeholder-slate-700"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                        />
                    </div>
                </header>

                {isLoading ? (
                    <div className="flex items-center justify-center py-20">
                        <div className="w-8 h-8 border-4 border-sky-500/20 border-t-sky-500 rounded-full animate-spin" />
                    </div>
                ) : (
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        {filteredSkills.map((skill, idx) => (
                            <motion.div 
                                key={skill.name}
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: idx * 0.03 }}
                                className="group glass-panel p-5 rounded-2xl border border-slate-800/50 hover:border-sky-500/30 hover:bg-slate-900/40 transition-all flex flex-col"
                            >
                                <div className="flex items-start justify-between mb-3">
                                    <div className="flex items-center space-x-3">
                                        <div className="w-8 h-8 rounded-lg bg-sky-500/10 flex items-center justify-center group-hover:bg-sky-500/20 transition-colors">
                                            <Zap className="w-4 h-4 text-sky-400" />
                                        </div>
                                        <h3 className="font-mono text-sm font-bold text-slate-200">{skill.name}</h3>
                                    </div>
                                    <div className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-[8px] font-bold text-slate-500 uppercase tracking-widest">
                                        Active
                                    </div>
                                </div>
                                <p className="text-slate-500 text-[11px] leading-relaxed mb-4 flex-1">
                                    {skill.description}
                                </p>
                                <div className="pt-4 border-t border-slate-800/50 flex items-center justify-between">
                                    <div className="flex items-center space-x-4">
                                        <div className="flex items-center space-x-1">
                                            <Box className="w-3 h-3 text-slate-600" />
                                            <span className="text-[9px] font-bold text-slate-600 uppercase tracking-tighter">
                                                {Object.keys(skill.parameters.properties || {}).length} Params
                                            </span>
                                        </div>
                                    </div>
                                    <button className="text-[9px] font-bold uppercase tracking-widest text-sky-500/60 group-hover:text-sky-500 transition-colors flex items-center italic">
                                        View Args <ChevronRight className="w-3 h-3 ml-1" />
                                    </button>
                                </div>
                            </motion.div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};
