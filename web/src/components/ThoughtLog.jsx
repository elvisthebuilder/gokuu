import React, { useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, Terminal } from 'lucide-react';
import { ToolCard } from './ToolCard';

export const ThoughtLog = ({ thoughts, currentThought }) => {
    const scrollRef = useRef(null);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [thoughts]);

    return (
        <div className="flex-1 flex flex-col space-y-4">
            <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                    <Sparkles className="w-3 h-3 text-sky-400 animate-pulse" />
                    <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Intelligence Logs</span>
                </div>
            </div>

            <div
                ref={scrollRef}
                className="space-y-4 pr-2"
            >
                <AnimatePresence initial={false}>
                    {thoughts.map((item, idx) => (
                        <div key={idx}>
                            {item.type === 'thought' && (
                                <motion.div
                                    initial={{ opacity: 0, x: 10 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    className="flex items-start space-x-3 group"
                                >
                                    <div className="mt-1.5 w-1 h-1 rounded-full bg-slate-700 group-last:bg-sky-500 transition-colors" />
                                    <p className="text-xs text-slate-400 leading-relaxed font-mono italic">
                                        {item.content}
                                    </p>
                                </motion.div>
                            )}

                            {(item.type === 'tool_call' || item.type === 'tool_result') && (
                                <ToolCard
                                    name={item.name}
                                    args={item.args}
                                    result={item.result}
                                    status={item.type === 'tool_result' ? 'success' : 'pending'}
                                />
                            )}
                        </div>
                    ))}

                    {currentThought && (
                        <motion.div
                            animate={{ opacity: [0.4, 1, 0.4] }}
                            transition={{ repeat: Infinity, duration: 2 }}
                            className="flex items-center space-x-3"
                        >
                            <div className="w-1 h-1 rounded-full bg-sky-500 shadow-[0_0_8px_rgba(56,189,248,0.5)]" />
                            <p className="text-[10px] text-sky-400 font-bold uppercase tracking-widest">
                                Processing Insight...
                            </p>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>

            {thoughts.length === 0 && !currentThought && (
                <div className="flex-1 flex flex-col items-center justify-center border border-dashed border-slate-800 rounded-2xl p-6 text-center">
                    <Terminal className="w-8 h-8 text-slate-800 mb-2" />
                    <p className="text-[10px] text-slate-700 font-bold uppercase tracking-widest leading-loose">
                        Neural Bridges Idle<br />Waiting for Directive
                    </p>
                </div>
            )}
        </div>
    );
};
