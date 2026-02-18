import React, { useState, useEffect, useRef } from 'react';
import { Sidebar } from './components/Sidebar';
import { ChatArea } from './components/ChatArea';
import { ThoughtLog } from './components/ThoughtLog';
import { SettingsModal } from './components/SettingsModal';
import { Terminal, Cpu, Settings as SettingsIcon, MessageSquare } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

function App() {
  const [messages, setMessages] = useState([]);
  const [thoughts, setThoughts] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [currentThought, setCurrentThought] = useState('');
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const socketRef = useRef(null);

  useEffect(() => {
    connectWebSocket();
    return () => socketRef.current?.close();
  }, []);

  const connectWebSocket = () => {
    const ws = new WebSocket('ws://localhost:8000/ws/chat');

    ws.onopen = () => {
      setIsConnected(true);
      console.log('Goku Backend Connected');
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'thought') {
        setThoughts(prev => [...prev, { type: 'thought', content: data.content }]);
        setCurrentThought(data.content);
      } else if (data.type === 'tool_call') {
        setThoughts(prev => [...prev, { type: 'tool_call', name: data.name, args: data.args }]);
      } else if (data.type === 'tool_result') {
        setThoughts(prev => [...prev, { type: 'tool_result', name: data.name, result: data.content }]);
      } else if (data.type === 'message' || (data.type === 'content' && data.role === 'agent')) {
        setMessages(prev => [...prev, { role: 'agent', content: data.content }]);
        setCurrentThought('');
        setIsSending(false); // Stop loading
      } else if (data.type === 'error') {
        console.error('Backend Error:', data.content);
        setMessages(prev => [...prev, { role: 'agent', content: `❌ Error: ${data.content}` }]);
        setIsSending(false); // Stop loading
      } else if (data.type === 'chunk') {
        // Handle streaming if implemented in backend
        setMessages(prev => {
          const last = prev[prev.length - 1];
          if (last && last.role === 'agent') {
            const updated = [...prev];
            updated[updated.length - 1] = { ...last, content: last.content + data.content };
            return updated;
          }
          return [...prev, { role: 'agent', content: data.content }];
        });
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      setIsSending(false);
      setTimeout(connectWebSocket, 3000);
    };

    socketRef.current = ws;
  };

  const sendMessage = (text) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      setMessages(prev => [...prev, { role: 'user', content: text }]);
      setIsSending(true); // Start loading
      socketRef.current.send(JSON.stringify({ type: 'message', content: text }));
    }
  };

  return (
    <div className="flex h-screen w-screen bg-slate-950 text-slate-50 overflow-hidden font-sans">
      {/* Sidebar Navigation */}
      <Sidebar onSettingsClick={() => setIsSettingsOpen(true)} />

      {/* Main Cockpit Layout (70/30) */}
      <main className="flex-1 flex overflow-hidden">
        {/* Chat Zone (70%) */}
        <section className="flex-[7] flex flex-col border-r border-slate-800/50 bg-slate-950/50 backdrop-blur-sm relative">
          <div className="h-14 border-b border-slate-800/50 flex items-center px-6 justify-between bg-slate-900/20">
            <div className="flex items-center space-x-3">
              <div className="flex space-x-1">
                <div className="w-3 h-3 rounded-full bg-red-500/20 border border-red-500/40" />
                <div className="w-3 h-3 rounded-full bg-yellow-500/20 border border-yellow-500/40" />
                <div className="w-3 h-3 rounded-full bg-green-500/20 border border-green-500/40" />
              </div>
              <span className="text-sm font-medium text-slate-400">Terminal v2.0 // MISSION_CONTROL</span>
            </div>
            <div className="flex items-center space-x-4">
              <div className={`flex items-center space-x-2 px-3 py-1 rounded-full border ${isConnected ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-red-500/10 border-red-500/30 text-red-400'}`}>
                <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'}`} />
                <span className="text-xs font-bold uppercase tracking-wider">{isConnected ? 'Online' : 'Offline'}</span>
              </div>
            </div>
          </div>

          <ChatArea messages={messages} onSendMessage={sendMessage} isSending={isSending} />
        </section>

        {/* Intelligence Pane (30%) */}
        <aside className="flex-[3] flex flex-col bg-slate-900/30 backdrop-blur-md">
          <div className="h-14 border-b border-slate-800/50 flex items-center px-6 bg-slate-900/40">
            <Cpu className="w-4 h-4 text-sky-400 mr-2" />
            <span className="text-sm font-bold text-sky-400 uppercase tracking-widest">Intelligence Logs</span>
          </div>

          <div className="flex-1 flex flex-col p-6 space-y-6 overflow-y-auto">
            <ThoughtLog thoughts={thoughts} currentThought={currentThought} />
          </div>
        </aside>
      </main>

      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        onSave={() => {
          // Potentially refresh something
        }}
      />
    </div>
  );
}

export default App;
