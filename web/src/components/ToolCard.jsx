import React from 'react';
import { motion } from 'framer-motion';
import { Box, CheckCircle, AlertCircle, Terminal as TerminalIcon } from 'lucide-react';

export const ToolCard = ({ name, args, result, status = 'success' }) => {
    return (
        <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="glass-panel rounded-2xl overflow-hidden"
        >
            <div className="bg-slate-900/40 px-4 py-2 border-b border-slate-800/50 flex items-center justify-between">
                <div className="flex items-center space-x-2">
                    <Box className="w-3 h-3 text-sky-400" />
                    <span className="text-[10px] font-bold text-slate-200 uppercase tracking-widest">{name}</span>
                </div>
                {status === 'success' ? (
                    <CheckCircle className="w-3 h-3 text-emerald-500" />
                ) : (
                    <AlertCircle className="w-3 h-3 text-red-500" />
                )}
            </div>

            <div className="p-4 space-y-3">
                {args && (
                    <div className="space-y-1">
                        <span className="text-[9px] font-bold text-slate-600 uppercase tracking-widest">Arguments</span>
                        <pre className="text-[10px] bg-black/40 p-2 rounded-lg border border-slate-800/50 text-sky-500/80 font-mono overflow-x-auto">
                            {JSON.stringify(args, null, 2)}
                        </pre>
                    </div>
                )}

                {result && (
                    <div className="space-y-1">
                        <span className="text-[9px] font-bold text-slate-600 uppercase tracking-widest">Result</span>
                        <div className="bg-black/40 p-3 rounded-lg border border-slate-800/50">
                            <pre className="text-[11px] text-slate-300 font-mono leading-relaxed whitespace-pre-wrap overflow-x-auto">
                                {typeof result === 'string' ? result : JSON.stringify(result, null, 2)}
                            </pre>
                        </div>
                    </div>
                )}
            </div>
        </motion.div>
    );
};
