import React, { useState } from 'react';
import { 
  Terminal, Cpu, Settings as SettingsIcon, MessageSquare, 
  Shield, Activity, ChevronLeft, ChevronRight, PlusCircle,
  History, UserCircle, Library, Zap, Trash2, Clock
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

export const Sidebar = ({ 
    onSettingsClick, 
    onNewChat, 
    onTabChange, 
    activeTab = 'chat',
    sessions = [],
    currentSessionId = '',
    onSessionSelect,
    onDeleteSession
}) => {
    const [isExpanded, setIsExpanded] = useState(false);

    const mainMenuItems = [
        { icon: MessageSquare, id: 'chat', label: 'Conversations' },
        { icon: UserCircle, id: 'personas', label: 'Personas' },
        { icon: Library, id: 'skills', label: 'Skill Library' },
        { icon: Activity, id: 'activity', label: 'Monitoring' },
    ];

    const bottomMenuItems = [
        { icon: Terminal, id: 'terminal', label: 'Terminal' },
        { icon: SettingsIcon, id: 'settings', label: 'System Config', action: onSettingsClick },
    ];

    return (
        <motion.nav 
            animate={{ width: isExpanded ? 260 : 64 }}
            className="h-full flex flex-col bg-slate-900 border-r border-slate-800 z-20 shrink-0 relative overflow-hidden"
        >
            {/* Header / Logo */}
            <div className={`p-4 mb-6 flex items-center ${isExpanded ? 'px-6' : 'justify-center'}`}>
                <div className="w-10 h-10 bg-sky-500 rounded-xl flex items-center justify-center shadow-lg shadow-sky-500/20 shrink-0">
                    <Zap className="text-slate-900 w-6 h-6" />
                </div>
                {isExpanded && (
                    <motion.span 
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        className="ml-4 font-black text-xl tracking-tighter self-center whitespace-nowrap"
                    >
                        GOKU <span className="text-sky-500 text-sm font-bold ml-1">v2.5</span>
                    </motion.span>
                )}
            </div>

            {/* New Chat Button */}
            <div className={`px-4 mb-8 ${isExpanded ? '' : 'flex justify-center'}`}>
                <button 
                    onClick={onNewChat}
                    className={`flex items-center group transition-all duration-300 ${
                        isExpanded 
                        ? 'w-full bg-sky-500 hover:bg-sky-400 text-slate-950 px-4 py-3 rounded-xl' 
                        : 'w-10 h-10 bg-slate-800 hover:bg-sky-500/20 text-sky-400 rounded-xl justify-center border border-slate-700'
                    }`}
                >
                    <PlusCircle className={`${isExpanded ? 'w-5 h-5 mr-3' : 'w-5 h-5'}`} />
                    {isExpanded && <span className="font-bold text-sm uppercase tracking-widest">New Session</span>}
                    {!isExpanded && (
                       <div className="absolute left-16 bg-slate-800 text-slate-200 text-[10px] py-1 px-3 rounded opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap uppercase tracking-[0.2em] font-bold border border-slate-700 shadow-2xl z-50">
                            New Chat
                        </div>
                    )}
                </button>
            </div>

            {/* Navigation Sections */}
            <div className="flex-1 flex flex-col px-3 space-y-2 overflow-y-auto no-scrollbar">
                {mainMenuItems.map((item) => (
                    <button
                        key={item.id}
                        onClick={() => onTabChange?.(item.id)}
                        className={`flex items-center group relative transition-all duration-200 ${
                            isExpanded ? 'px-4 py-3 rounded-xl' : 'w-10 h-10 justify-center rounded-xl mx-auto'
                        } ${activeTab === item.id ? 'bg-sky-500/10 text-sky-400' : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800'}`}
                    >
                        <item.icon className="w-5 h-5 shrink-0" />
                        {isExpanded && (
                            <motion.span 
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                className="ml-4 font-bold text-[11px] uppercase tracking-widest whitespace-nowrap"
                            >
                                {item.label}
                            </motion.span>
                        )}
                        {!isExpanded && (
                            <div className="absolute left-14 bg-slate-800 text-slate-200 text-[10px] py-1 px-3 rounded opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap uppercase tracking-[0.2em] font-bold border border-slate-700 shadow-2xl z-50">
                                {item.label}
                            </div>
                        )}
                        {activeTab === item.id && !isExpanded && (
                            <div className="absolute left-0 w-1 h-5 bg-sky-500 rounded-r-full" />
                        )}
                    </button>
                ))}
            </div>

            {/* Session History List (Visible only when expanded and in chat tab) */}
            <AnimatePresence>
                {isExpanded && activeTab === 'chat' && sessions.length > 0 && (
                    <motion.div 
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        className="px-4 mt-6 flex-1 flex flex-col min-h-0 border-t border-slate-800/50 pt-4"
                    >
                        <div className="flex items-center justify-between mb-4 px-2">
                            <span className="text-[10px] font-bold text-slate-500 uppercase tracking-[0.2em]">Recent History</span>
                            <Clock className="w-3 h-3 text-slate-600" />
                        </div>
                        <div className="flex-1 overflow-y-auto space-y-1 pr-2 chat-scroll no-scrollbar">
                            {sessions.map((session) => (
                                <div key={session.id} className="group relative">
                                    <button
                                        onClick={() => onSessionSelect?.(session.id)}
                                        className={`w-full text-left px-3 py-2 rounded-lg text-xs transition-all duration-200 flex items-center justify-between ${
                                            currentSessionId === session.id 
                                            ? 'bg-sky-500/10 text-sky-400 border border-sky-500/20' 
                                            : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                                        }`}
                                    >
                                        <span className="truncate pr-4">{session.title || 'Untitled Session'}</span>
                                    </button>
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            onDeleteSession?.(session.id);
                                        }}
                                        className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-slate-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all rounded-md hover:bg-red-500/10"
                                    >
                                        <Trash2 className="w-3 h-3" />
                                    </button>
                                </div>
                            ))}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Footer Items */}
            <div className="px-3 pb-4 space-y-2">
                {bottomMenuItems.map((item) => (
                    <button
                        key={item.id}
                        onClick={item.action || (() => onTabChange?.(item.id))}
                        className={`flex items-center group relative transition-all duration-200 ${
                            isExpanded ? 'px-4 py-3 rounded-xl' : 'w-10 h-10 justify-center rounded-xl mx-auto'
                        } ${activeTab === item.id ? 'bg-sky-500/10 text-sky-400' : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800'}`}
                    >
                        <item.icon className="w-5 h-5 shrink-0" />
                        {isExpanded && (
                            <motion.span 
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                className="ml-4 font-bold text-[11px] uppercase tracking-widest whitespace-nowrap"
                            >
                                {item.label}
                            </motion.span>
                        )}
                        {!isExpanded && (
                            <div className="absolute left-14 bg-slate-800 text-slate-200 text-[10px] py-1 px-3 rounded opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap uppercase tracking-[0.2em] font-bold border border-slate-700 shadow-2xl z-50">
                                {item.label}
                            </div>
                        )}
                    </button>
                ))}

                <button
                    onClick={() => setIsExpanded(!isExpanded)}
                    className={`w-full flex items-center justify-center p-3 text-slate-500 hover:text-sky-400 hover:bg-sky-400/5 rounded-xl transition-all`}
                >
                    {isExpanded ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                </button>
            </div>
        </motion.nav>
    );
};
