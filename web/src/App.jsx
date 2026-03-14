import React, { useState, useEffect, useRef } from 'react';
import { Sidebar } from './components/Sidebar';
import { ChatArea } from './components/ChatArea';
import { ThoughtLog } from './components/ThoughtLog';
import { SettingsModal } from './components/SettingsModal';
import { PersonaView } from './components/PersonaView';
import { SkillsView } from './components/SkillsView';
import { Terminal, Cpu, Settings as SettingsIcon, MessageSquare } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

function App() {
  const [messages, setMessages] = useState([]);
  const [thoughts, setThoughts] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [currentThought, setCurrentThought] = useState('');
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(400);
  const [isDragging, setIsDragging] = useState(false);
  const [activeTab, setActiveTab] = useState('chat');
  const [sessionId, setSessionId] = useState(() => `web_${Date.now()}`);
  const [sessions, setSessions] = useState([]);
  const socketRef = useRef(null);
  const mainRef = useRef(null);
  const thoughtBufferRef = useRef('');

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isDragging) return;
      if (mainRef.current) {
        // Calculate new width: total window width minus mouse X cord
        const newWidth = window.innerWidth - e.clientX;
        // Keep it within sensible limits (200px to 800px or 80vw)
        const constrainedWidth = Math.max(200, Math.min(newWidth, window.innerWidth * 0.8));
        setSidebarWidth(constrainedWidth);
      }
    };

    const handleMouseUp = () => {
      setIsDragging(false);
    };

    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none'; // Prevent text selection while dragging
    } else {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'default';
      document.body.style.userSelect = 'auto';
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging]);

  useEffect(() => {
    connectWebSocket();
    fetchSessions();
    return () => socketRef.current?.close();
  }, []);

  const fetchSessions = async () => {
    try {
      const res = await fetch('http://localhost:8000/sessions');
      const data = await res.json();
      setSessions(data);
    } catch (err) {
      console.error('Failed to fetch sessions:', err);
    }
  };

  const loadSession = async (id) => {
    try {
      setSessionId(id);
      setIsSending(true);
      const res = await fetch(`http://localhost:8000/sessions/${id}`);
      const data = await res.json();
      setMessages(data.map(m => ({ role: m.role, content: m.content })));
      setThoughts([]); // Clear thoughts when switching
      setActiveTab('chat'); // Switch back to chat view
      setIsSending(false);
    } catch (err) {
      console.error('Failed to load session:', err);
      setIsSending(false);
    }
  };

  const startNewChat = () => {
    const newId = `web_${Date.now()}`;
    setSessionId(newId);
    setMessages([]);
    setThoughts([]);
    setActiveTab('chat'); // Ensure we are in chat view
    fetchSessions(); // Refresh list to include current if it was saved
  };

  const deleteSession = async (id) => {
    try {
      await fetch(`http://localhost:8000/sessions/${id}`, { method: 'DELETE' });
      fetchSessions();
      if (sessionId === id) {
        startNewChat();
      }
    } catch (err) {
      console.error('Failed to delete session:', err);
    }
  };

  const connectWebSocket = () => {
    const ws = new WebSocket('ws://localhost:8000/ws/chat');

    ws.onopen = () => {
      setIsConnected(true);
      console.log('Goku Backend Connected');
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'thought') {
        thoughtBufferRef.current = data.content;
        setCurrentThought(data.content);
      } else if (data.type === 'tool_call') {
        if (thoughtBufferRef.current) {
          setThoughts(prev => [...prev, { type: 'thought', content: thoughtBufferRef.current }, { type: 'tool_call', name: data.name, args: data.args }]);
          thoughtBufferRef.current = '';
          setCurrentThought('');
        } else {
          setThoughts(prev => [...prev, { type: 'tool_call', name: data.name, args: data.args }]);
        }
      } else if (data.type === 'tool_result') {
        setThoughts(prev => [...prev, { type: 'tool_result', name: data.name, result: data.content }]);
      } else if (data.type === 'message' || (data.type === 'content' && data.role === 'agent')) {
        if (thoughtBufferRef.current) {
          setThoughts(prev => [...prev, { type: 'thought', content: thoughtBufferRef.current }]);
          thoughtBufferRef.current = '';
        }
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
      socketRef.current.send(JSON.stringify({ 
        type: 'message', 
        content: text,
        session_id: sessionId
      }));
      // Refresh session list after a slight delay to capture New Conversation title update
      setTimeout(fetchSessions, 1000);
    }
  };

  return (
    <div className="flex h-screen w-screen bg-slate-950 text-slate-50 overflow-hidden font-sans">
      {/* Sidebar Navigation */}
      <Sidebar 
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onSettingsClick={() => setIsSettingsOpen(true)} 
        onNewChat={startNewChat}
        sessions={sessions}
        currentSessionId={sessionId}
        onSessionSelect={loadSession}
        onDeleteSession={deleteSession}
      />      {/* Main Cockpit Layout */}
      <main ref={mainRef} className="flex-1 flex overflow-hidden">
        <AnimatePresence mode="wait">
          {activeTab === 'chat' && (
            <motion.div 
              key="chat"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="flex-1 flex overflow-hidden"
            >
              {/* Chat Zone (Flexible Width) */}
              <section className="flex-1 min-w-0 flex flex-col bg-slate-950/50 backdrop-blur-sm relative border-r border-slate-800/30">
                <div className="h-14 border-b border-slate-800/50 flex items-center px-6 justify-between bg-slate-900/20">
                  <div className="flex items-center space-x-3">
                    <div className="flex space-x-1">
                      <div className="w-3 h-3 rounded-full bg-red-500/20 border border-red-500/40" />
                      <div className="w-3 h-3 rounded-full bg-yellow-500/20 border border-yellow-500/40" />
                      <div className="w-3 h-3 rounded-full bg-green-500/20 border border-green-500/40" />
                    </div>
                    <span className="text-sm font-medium text-slate-400">Terminal v2.5 // MISSION_CONTROL</span>
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

              {/* Resizer Handle */}
              <div 
                className={`w-1 cursor-col-resize hover:bg-sky-500/50 transition-colors z-10 ${isDragging ? 'bg-sky-500/50' : 'bg-slate-800/50'}`}
                onMouseDown={(e) => {
                  e.preventDefault();
                  setIsDragging(true);
                }}
              />

              {/* Intelligence Pane (Fixed/Resizable Width) */}
              <aside 
                style={{ width: sidebarWidth }}
                className="flex-shrink-0 flex flex-col bg-slate-900/30 backdrop-blur-md min-w-0 relative"
              >
                {/* Overlay to block pointer events (fixed while dragging) */}
                {isDragging && <div className="absolute inset-0 z-50 bg-transparent" />}
                <div className="h-14 border-b border-slate-800/50 flex items-center px-6 bg-slate-900/40">
                  <Cpu className="w-4 h-4 text-sky-400 mr-2" />
                  <span className="text-sm font-bold text-sky-400 uppercase tracking-widest">Intelligence Logs</span>
                </div>
                <div className="flex-1 flex flex-col min-h-0">
                  <ThoughtLog thoughts={thoughts} currentThought={currentThought} />
                </div>
              </aside>
            </motion.div>
          )}

          {activeTab === 'personas' && (
            <motion.div 
              key="personas"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="flex-1 overflow-hidden flex flex-col"
            >
              <PersonaView />
            </motion.div>
          )}

          {activeTab === 'skills' && (
            <motion.div 
              key="skills"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="flex-1 overflow-hidden flex flex-col"
            >
              <SkillsView />
            </motion.div>
          )}

          {activeTab === 'activity' && (
              <motion.div key="activity" className="flex-1 flex items-center justify-center text-slate-700 font-bold uppercase tracking-[0.5em] italic">
                  Node Telemetry Stream Active
              </motion.div>
          )}
        </AnimatePresence>
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
