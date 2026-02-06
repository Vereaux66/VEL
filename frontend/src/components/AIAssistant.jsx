import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Send, Bot, Loader2 } from 'lucide-react'
import { aiApi } from '../utils/api'

export default function AIAssistant({ isOpen, onClose }) {
  const [messages, setMessages] = useState([
    {
      id: 1,
      role: 'assistant',
      content: 'Hello! I\'m your VEL AI trading assistant. I can help you with market analysis, strategy recommendations, risk assessment, and portfolio insights. What would you like to know?'
    }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
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
      setMessages(prev => [...prev, {
        id: Date.now(),
        role: 'assistant',
        content: 'I apologize, but I encountered an error processing your request. Please try again.'
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
    'Analyze current market',
    'Show my portfolio risk',
    'Suggest trading strategy',
    'Recent performance summary'
  ]

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ x: '100%' }}
          animate={{ x: 0 }}
          exit={{ x: '100%' }}
          transition={{ type: 'spring', damping: 25, stiffness: 200 }}
          className="fixed right-0 top-0 bottom-0 w-96 glass border-l border-plasma-purple/30 z-50 flex flex-col"
        >
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-plasma-purple/20">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-plasma-purple to-plasma-cyan flex items-center justify-center">
                <Bot size={20} className="text-void" />
              </div>
              <div>
                <h3 className="font-display text-plasma-purple">VEL AI</h3>
                <p className="text-xs text-gray-500">Trading Assistant</p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="p-2 rounded-lg hover:bg-plasma-purple/10 text-gray-400 hover:text-plasma-purple transition-colors"
            >
              <X size={20} />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.map((msg) => (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[80%] p-3 rounded-xl ${
                    msg.role === 'user'
                      ? 'bg-plasma-cyan/20 text-plasma-cyan'
                      : 'bg-plasma-purple/10 text-gray-300'
                  }`}
                >
                  <p className="text-sm font-mono whitespace-pre-wrap">{msg.content}</p>
                </div>
              </motion.div>
            ))}
            
            {loading && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex justify-start"
              >
                <div className="bg-plasma-purple/10 p-3 rounded-xl">
                  <Loader2 size={20} className="animate-spin text-plasma-purple" />
                </div>
              </motion.div>
            )}
            
            <div ref={messagesEndRef} />
          </div>

          {/* Quick Actions */}
          <div className="p-4 border-t border-plasma-purple/20">
            <div className="flex flex-wrap gap-2 mb-4">
              {quickActions.map((action) => (
                <button
                  key={action}
                  onClick={() => setInput(action)}
                  className="text-xs px-3 py-1.5 rounded-full bg-plasma-purple/10 text-plasma-purple hover:bg-plasma-purple/20 transition-colors font-mono"
                >
                  {action}
                </button>
              ))}
            </div>

            {/* Input */}
            <div className="flex items-center space-x-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Ask anything about trading..."
                className="flex-1 bg-deep-space border border-plasma-purple/30 rounded-xl px-4 py-3 text-sm font-mono text-white placeholder-gray-500 focus:outline-none focus:border-plasma-purple focus:shadow-glow-purple transition-all"
              />
              <button
                onClick={handleSend}
                disabled={loading || !input.trim()}
                className="p-3 rounded-xl bg-gradient-to-r from-plasma-purple to-plasma-cyan text-void hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Send size={18} />
              </button>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
