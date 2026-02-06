import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Send, Bot, Loader2, Zap } from 'lucide-react'
import { Sparkles, HelpCircle, TrendingUp, Shield, Wallet, Settings } from 'lucide-react'
import { aiApi } from '../utils/api'

// Configuration constants
const HOLOGRAM_DISPLAY_DURATION = 5000 // ms to show hologram bubble
const SCAN_LINE_COUNT = 20 // Number of scan lines for hologram effect

// Hologram effect component
function HologramEffect() {
  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden rounded-2xl">
      {/* Scan lines - using CSS gradient for performance */}
      <div 
        className="absolute inset-0 opacity-10"
        style={{
          background: 'repeating-linear-gradient(0deg, transparent, transparent 7px, rgba(0, 255, 255, 0.3) 8px)'
        }}
      />
      {/* Glitch effect overlay */}
      <div className="absolute inset-0 bg-gradient-to-b from-plasma-cyan/5 via-transparent to-plasma-purple/5 animate-pulse" />
      {/* Corner accents */}
      <div className="absolute top-0 left-0 w-8 h-8 border-l-2 border-t-2 border-plasma-cyan/50" />
      <div className="absolute top-0 right-0 w-8 h-8 border-r-2 border-t-2 border-plasma-cyan/50" />
      <div className="absolute bottom-0 left-0 w-8 h-8 border-l-2 border-b-2 border-plasma-purple/50" />
      <div className="absolute bottom-0 right-0 w-8 h-8 border-r-2 border-b-2 border-plasma-purple/50" />
    </div>
  )
}

// Floating hologram chat bubble above assistant
function HologramChatBubble({ lastMessage, isVisible }) {
  if (!isVisible || !lastMessage) return null
  
  return (
    <motion.div
      initial={{ opacity: 0, y: 20, scale: 0.9 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -20, scale: 0.9 }}
      className="absolute -top-32 right-4 left-4 z-60"
    >
      <div className="relative">
        {/* Hologram glow effect */}
        <div className="absolute inset-0 bg-plasma-cyan/20 blur-xl rounded-xl" />
        
        {/* Main hologram bubble */}
        <div className="relative bg-void/90 backdrop-blur-md border border-plasma-cyan/40 rounded-xl p-4 shadow-[0_0_30px_rgba(0,255,255,0.3)]">
          {/* Hologram scan lines - using CSS for performance */}
          <div className="absolute inset-0 overflow-hidden rounded-xl pointer-events-none">
            <div 
              className="absolute inset-0 opacity-20"
              style={{
                background: 'repeating-linear-gradient(0deg, transparent, transparent 5px, rgba(0, 255, 255, 0.2) 6px)'
              }}
            />
          </div>
          
          {/* Content */}
          <div className="relative">
            <div className="flex items-center space-x-2 mb-2">
              <Zap size={14} className="text-plasma-cyan animate-pulse" />
              <span className="text-xs font-display text-plasma-cyan tracking-wider">VEL AI RESPONSE</span>
            </div>
            <p className="text-sm font-mono text-gray-300 line-clamp-3">
              {lastMessage.length > 150 ? lastMessage.substring(0, 150) + '...' : lastMessage}
            </p>
          </div>
          
          {/* Hologram pointer */}
          <div className="absolute -bottom-2 right-8 w-4 h-4 bg-void/90 border-r border-b border-plasma-cyan/40 transform rotate-45" />
        </div>
      </div>
    </motion.div>
  )
}

export default function AIAssistant({ isOpen, onClose }) {
  const [messages, setMessages] = useState([
    {
      id: 1,
      role: 'assistant',
      content: `Hello! 👋 I'm your VEL AI Trading Assistant.

I have full knowledge of the VEL platform and can help you with:
• Trading strategies and market analysis
• Risk management and portfolio insights
• Platform features and how-to guides
• Account settings and security

What would you like to know?`
    }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [showHologramBubble, setShowHologramBubble] = useState(false)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Show hologram bubble briefly when new assistant message arrives
  useEffect(() => {
    const lastMsg = messages[messages.length - 1]
    if (lastMsg?.role === 'assistant' && messages.length > 1) {
      setShowHologramBubble(true)
      const timer = setTimeout(() => setShowHologramBubble(false), HOLOGRAM_DISPLAY_DURATION)
      return () => clearTimeout(timer)
    }
  }, [messages])

  const handleSend = async () => {
    if (!input.trim() || loading) return

    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: input.trim()
    }

    setMessages(prev => [...prev, userMessage])
    setInput('')
    setLoading(true)

    try {
      const response = await aiApi.ask(input.trim())
      
      setMessages(prev => [...prev, {
        id: Date.now(),
        role: 'assistant',
        content: response.response
      }])
    } catch (error) {
      // Provide helpful offline response
      setMessages(prev => [...prev, {
        id: Date.now(),
        role: 'assistant',
        content: `I'm currently unable to connect to the server, but I can still help!

**Quick Answers:**
• **Start Trading**: Go to Trading Terminal → Select Strategy → Choose Risk Level → Click Start
• **View Portfolio**: Check the Dashboard for all your metrics
• **Deposit/Withdraw**: Use the Wallet section
• **Security**: Enable 2FA in Settings → Security

Please try your question again in a moment, or check your connection.`
      }])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const quickActions = [
    { label: 'What is VEL?', icon: HelpCircle },
    { label: 'What can you do?', icon: Sparkles },
    { label: 'Trading strategies', icon: TrendingUp },
    { label: 'Risk management', icon: Shield },
    { label: 'Wallet & funds', icon: Wallet },
    { label: 'System status', icon: Settings }
  ]

  const lastAssistantMessage = messages.filter(m => m.role === 'assistant').pop()?.content

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ x: '100%' }}
          animate={{ x: 0 }}
          exit={{ x: '100%' }}
          transition={{ type: 'spring', damping: 25, stiffness: 200 }}
          className="fixed right-0 top-0 bottom-0 w-96 z-50 flex flex-col"
        >
          {/* Hologram floating bubble */}
          <AnimatePresence>
            <HologramChatBubble 
              lastMessage={lastAssistantMessage} 
              isVisible={showHologramBubble} 
            />
          </AnimatePresence>

          {/* Main chat container with hologram effect */}
          <div className="relative flex-1 flex flex-col bg-void/95 backdrop-blur-xl border-l border-plasma-purple/30 shadow-[0_0_50px_rgba(191,0,255,0.2)]">
            {/* Hologram overlay effect */}
            <HologramEffect />

            {/* Header */}
            <div className="relative flex items-center justify-between p-4 border-b border-plasma-purple/20">
              <div className="flex items-center space-x-3">
                <div className="relative">
                  {/* Hologram ring around avatar */}
                  <div className="absolute inset-0 rounded-full border-2 border-plasma-cyan/50 animate-spin" style={{ animationDuration: '3s' }} />
                  <div className="w-12 h-12 rounded-full bg-gradient-to-br from-plasma-purple to-plasma-cyan flex items-center justify-center relative">
                    <Bot size={22} className="text-void" />
                    <span className="absolute -top-1 -right-1 w-3 h-3 bg-neon-green rounded-full animate-pulse shadow-[0_0_10px_rgba(0,255,65,0.8)]" />
                  </div>
                </div>
                <div>
                  <h3 className="font-display text-plasma-purple text-lg tracking-wide">VEL AI</h3>
                  <div className="flex items-center space-x-1">
                    <span className="w-2 h-2 bg-neon-green rounded-full animate-pulse" />
                    <p className="text-xs text-neon-green font-mono">ONLINE • READY</p>
                  </div>
                </div>
              </div>
              <button
                onClick={onClose}
                className="p-2 rounded-lg hover:bg-plasma-purple/10 text-gray-400 hover:text-plasma-purple transition-colors border border-transparent hover:border-plasma-purple/30"
              >
                <X size={20} />
              </button>
            </div>

            {/* Messages with hologram styling */}
            <div className="relative flex-1 overflow-y-auto p-4 space-y-4">
              {messages.map((msg) => (
                <motion.div
                  key={msg.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[85%] p-3 rounded-xl relative ${
                      msg.role === 'user'
                        ? 'bg-plasma-cyan/20 text-plasma-cyan border border-plasma-cyan/30'
                        : 'bg-plasma-purple/10 text-gray-300 border border-plasma-purple/20 shadow-[0_0_15px_rgba(191,0,255,0.1)]'
                    }`}
                  >
                    {msg.role === 'assistant' && (
                      <div className="absolute -left-1 -top-1 w-2 h-2 bg-plasma-purple rounded-full animate-pulse" />
                    )}
                    <p className="text-sm font-mono whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                  </div>
                </motion.div>
              ))}
              
              {loading && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="flex justify-start"
                >
                  <div className="bg-plasma-purple/10 p-3 rounded-xl flex items-center space-x-2 border border-plasma-purple/20">
                    <div className="relative">
                      <Loader2 size={18} className="animate-spin text-plasma-purple" />
                      <div className="absolute inset-0 animate-ping">
                        <Loader2 size={18} className="text-plasma-cyan opacity-50" />
                      </div>
                    </div>
                    <span className="text-xs text-gray-400 font-mono">Processing query...</span>
                  </div>
                </motion.div>
              )}
              
              <div ref={messagesEndRef} />
            </div>

            {/* Quick Actions */}
            <div className="relative p-4 border-t border-plasma-purple/20 bg-void/50">
              <p className="text-xs text-gray-500 mb-2 font-mono flex items-center">
                <Zap size={12} className="mr-1 text-plasma-cyan" />
                Quick Questions:
              </p>
              <div className="grid grid-cols-2 gap-2 mb-4">
                {quickActions.map(({ label, icon: Icon }) => (
                  <button
                    key={label}
                    onClick={() => setInput(label)}
                    className="flex items-center space-x-2 text-xs px-3 py-2 rounded-lg bg-plasma-purple/10 text-plasma-purple hover:bg-plasma-purple/20 transition-all font-mono text-left border border-transparent hover:border-plasma-purple/30 hover:shadow-[0_0_10px_rgba(191,0,255,0.2)]"
                  >
                    <Icon size={14} />
                    <span className="truncate">{label}</span>
                  </button>
                ))}
              </div>

              {/* Input with hologram effect */}
              <div className="flex items-center space-x-2">
                <div className="flex-1 relative">
                  <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyPress={handleKeyPress}
                    placeholder="Ask me anything about VEL..."
                    className="w-full bg-deep-space border border-plasma-purple/30 rounded-xl px-4 py-3 text-sm font-mono text-white placeholder-gray-500 focus:outline-none focus:border-plasma-cyan focus:shadow-[0_0_20px_rgba(0,255,255,0.3)] transition-all"
                  />
                  {input && (
                    <div className="absolute right-3 top-1/2 -translate-y-1/2">
                      <span className="text-xs text-plasma-cyan animate-pulse">●</span>
                    </div>
                  )}
                </div>
                <button
                  onClick={handleSend}
                  disabled={loading || !input.trim()}
                  className="p-3 rounded-xl bg-gradient-to-r from-plasma-purple to-plasma-cyan text-void hover:opacity-90 transition-all disabled:opacity-50 disabled:cursor-not-allowed hover:shadow-[0_0_20px_rgba(0,255,255,0.4)] active:scale-95"
                >
                  <Send size={18} />
                </button>
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
