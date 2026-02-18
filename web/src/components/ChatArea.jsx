import React, { useState, useRef, useEffect } from 'react';
import { Send, Hash, CornerDownLeft, Loader2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export const ChatArea = ({ messages, onSendMessage, isSending }) => {
    const [input, setInput] = useState('');
    const scrollRef = useRef(null);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages]);

    const handleSend = (e) => {
        e?.preventDefault();
        if (input.trim()) {
            onSendMessage(input);
            setInput('');
        }
    };

    const MarkdownComponents = {
        p: ({ children }) => <p className="mb-4 last:mb-0 leading-relaxed">{children}</p>,
        code: ({ node, inline, className, children, ...props }) => {
            const match = /language-(\w+)/.exec(className || '');
            return !inline ? (
                <div className="my-4 rounded-lg overflow-hidden bg-slate-950/80 border border-slate-700/50">
                    <div className="flex items-center justify-between px-4 py-2 bg-slate-800/50 border-b border-slate-700/50">
                        <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider">
                            {match ? match[1] : 'code'}
                        </span>
                    </div>
                    <pre className="p-4 overflow-x-auto">
                        <code className="text-xs font-mono text-sky-300" {...props}>
                            {children}
                        </code>
                    </pre>
                </div>
            ) : (
                <code className="px-1.5 py-0.5 rounded bg-slate-800 text-sky-300 font-mono text-xs" {...props}>
                    {children}
                </code>
            );
        },
        ul: ({ children }) => <ul className="list-disc ml-6 mb-4 space-y-1">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal ml-6 mb-4 space-y-1">{children}</ol>,
        li: ({ children }) => <li className="text-sm">{children}</li>,
        h1: ({ children }) => <h1 className="text-xl font-bold mb-4 text-slate-100">{children}</h1>,
        h2: ({ children }) => <h2 className="text-lg font-bold mb-3 text-slate-100">{children}</h2>,
        h3: ({ children }) => <h3 className="text-md font-bold mb-2 text-slate-100">{children}</h3>,
        table: ({ children }) => (
            <div className="my-4 overflow-x-auto rounded-lg border border-slate-800">
                <table className="w-full text-left border-collapse">{children}</table>
            </div>
        ),
        thead: ({ children }) => <thead className="bg-slate-800/50">{children}</thead>,
        th: ({ children }) => <th className="px-4 py-2 border-b border-slate-800 font-bold text-xs uppercase tracking-wider">{children}</th>,
        td: ({ children }) => <td className="px-4 py-2 border-b border-slate-800 text-sm">{children}</td>,
        blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-sky-500/50 pl-4 py-1 my-4 italic text-slate-400 bg-sky-500/5">
                {children}
            </blockquote>
        ),
        a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noopener noreferrer" className="text-sky-400 hover:underline decoration-sky-400/30 underline-offset-4">
                {children}
            </a>
        ),
    };

    return (
        <>
            <div
                ref={scrollRef}
                className="flex-1 overflow-y-auto px-12 py-8 space-y-8 chat-scroll scroll-smooth"
            >
                <AnimatePresence initial={false}>
                    {messages.length === 0 && (
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="mt-20 flex flex-col items-center justify-center text-center space-y-4"
                        >
                            <div className="w-16 h-16 bg-sky-500/10 rounded-2xl flex items-center justify-center border border-sky-500/20">
                                <Hash className="text-sky-400 w-8 h-8" />
                            </div>
                            <div>
                                <h1 className="text-2xl font-bold tracking-tight text-slate-100">Initializing Goku Protocols</h1>
                                <p className="text-slate-400 max-w-md mt-2">The superior agent is ready. Access the OpenClaw skill ecosystem directly through this secure channel.</p>
                            </div>
                        </motion.div>
                    )}

                    {messages.map((msg, idx) => (
                        <motion.div
                            key={idx}
                            initial={{ opacity: 0, x: -10 }}
                            animate={{ opacity: 1, x: 0 }}
                            className={`flex flex-col space-y-2 ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
                        >
                            <div className="flex items-center space-x-2 text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500 mb-1">
                                <span>{msg.role === 'user' ? 'Operator' : 'Goku System'}</span>
                                <div className={`w-1 h-1 rounded-full ${msg.role === 'user' ? 'bg-indigo-500' : 'bg-sky-500'}`} />
                            </div>

                            <div className={`max-w-[85%] px-5 py-3 rounded-2xl border ${msg.role === 'user'
                                ? 'bg-indigo-500/10 border-indigo-500/20 text-indigo-50 rounded-tr-none'
                                : 'bg-slate-900/60 border-slate-800/80 text-slate-100 rounded-tl-none backdrop-blur-sm'
                                }`}>
                                <div className="text-sm prose prose-invert max-w-none">
                                    {msg.role === 'user' ? (
                                        <p className="whitespace-pre-wrap">{msg.content}</p>
                                    ) : (
                                        <ReactMarkdown
                                            remarkPlugins={[remarkGfm]}
                                            components={MarkdownComponents}
                                        >
                                            {msg.content}
                                        </ReactMarkdown>
                                    )}
                                </div>
                            </div>
                        </motion.div>
                    ))}
                </AnimatePresence>
            </div>

            {/* Embedded Input Bar */}
            <div className="px-12 py-8 bg-gradient-to-t from-slate-950 via-slate-950 to-transparent">
                <form
                    onSubmit={handleSend}
                    className="relative glass-panel rounded-2xl p-1 shadow-2xl shadow-black/50 overflow-hidden group focus-within:border-sky-500/50 transition-all duration-300"
                >
                    <div className="absolute inset-x-0 bottom-0 h-0.5 bg-gradient-to-r from-transparent via-sky-500 to-transparent opacity-0 group-focus-within:opacity-100 transition-opacity" />

                    <div className="flex items-center">
                        <input
                            type="text"
                            value={input}
                            disabled={isSending}
                            onChange={(e) => setInput(e.target.value)}
                            placeholder={isSending ? "Goku is calculating..." : "Transmit instructions..."}
                            className="flex-1 bg-transparent px-5 py-4 text-sm focus:outline-none placeholder-slate-600 text-slate-200 disabled:opacity-50"
                        />
                        <div className="flex items-center pr-4 space-x-2">
                            <div className="hidden sm:flex items-center space-x-1 px-2 py-1 rounded bg-slate-800 border border-slate-700">
                                <CornerDownLeft className="w-3 h-3 text-slate-500" />
                                <span className="text-[10px] text-slate-500 font-bold">ENTER</span>
                            </div>
                            <button
                                type="submit"
                                disabled={!input.trim() || isSending}
                                className="p-2 bg-sky-500 text-slate-950 rounded-xl hover:bg-sky-400 disabled:opacity-30 disabled:hover:bg-sky-500 transition-all active:scale-95 shadow-lg shadow-sky-500/20"
                            >
                                {isSending ? (
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                ) : (
                                    <Send className="w-4 h-4" />
                                )}
                            </button>
                        </div>
                    </div>
                </form>
                <div className="mt-4 flex justify-center space-x-6 text-[10px] font-bold text-slate-600 tracking-widest uppercase">
                    <div className="flex items-center space-x-2">
                        <div className="w-1 h-1 rounded-full bg-slate-600" />
                        <span>Secure Tunnel Active</span>
                    </div>
                    <div className="flex items-center space-x-2">
                        <div className="w-1 h-1 rounded-full bg-slate-600" />
                        <span>Encrypted Stream</span>
                    </div>
                </div>
            </div>
        </>
    );
};
