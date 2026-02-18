import React from 'react';
import { Terminal, Cpu, Settings as SettingsIcon, MessageSquare, Shield, Activity } from 'lucide-react';

export const Sidebar = ({ onSettingsClick }) => {
    const menuItems = [
        { icon: MessageSquare, id: 'chat', active: true },
        { icon: Terminal, id: 'terminal' },
        { icon: Activity, id: 'activity' },
        { icon: Shield, id: 'security' },
        { icon: SettingsIcon, id: 'settings', action: onSettingsClick },
    ];

    return (
        <nav className="w-16 flex flex-col items-center py-8 bg-slate-900 border-r border-slate-800 space-y-8 z-10 transition-all shrink-0">
            <div className="w-10 h-10 bg-sky-500 rounded-xl flex items-center justify-center shadow-lg shadow-sky-500/20 hover:scale-105 transition-transform cursor-pointer">
                <Terminal className="text-slate-900 w-6 h-6" />
            </div>

            <div className="flex-1 flex flex-col items-center space-y-6 pt-12">
                {menuItems.map((item) => (
                    <button
                        key={item.id}
                        onClick={item.action}
                        className={`p-3 rounded-xl transition-all group relative ${item.active ? 'bg-sky-500/10 text-sky-400' : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800'}`}
                    >
                        <item.icon className="w-5 h-5" />
                        {item.active && (
                            <div className="absolute left-0 w-1 h-6 bg-sky-500 rounded-r-full -ml-3" />
                        )}
                        <div className="absolute left-16 bg-slate-800 text-slate-200 text-xs py-1 px-2 rounded opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap uppercase tracking-widest font-bold border border-slate-700 shadow-xl z-50">
                            {item.id}
                        </div>
                    </button>
                ))}
            </div>

            <div className="w-8 h-8 rounded-full border border-slate-700 bg-slate-800 flex items-center justify-center overflow-hidden hover:border-sky-500 transition-colors cursor-pointer">
                <div className="w-full h-full bg-gradient-to-tr from-sky-500 to-indigo-600 opacity-80" />
            </div>
        </nav>
    );
};
