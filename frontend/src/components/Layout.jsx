import { Outlet, NavLink, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import { 
  LayoutDashboard, 
  TrendingUp, 
  Wallet, 
  Settings, 
  LogOut,
  Bot,
  Activity,
  Bell
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useWebSocket } from '../context/WebSocketContext'
import AIAssistant from './AIAssistant'
import { useState } from 'react'

const navItems = [
  { path: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { path: '/trading', icon: TrendingUp, label: 'Trading' },
  { path: '/wallet', icon: Wallet, label: 'Wallet' },
  { path: '/settings', icon: Settings, label: 'Settings' }
]

export default function Layout() {
  const { logout, user } = useAuth()
  const { connected, notifications, tradingStatus } = useWebSocket()
  const location = useLocation()
  const [showAI, setShowAI] = useState(false)
  const [showNotifications, setShowNotifications] = useState(false)

  return (
    <div className="min-h-screen bg-void cyber-grid">
      {/* Top Navigation Bar */}
      <nav className="fixed top-0 left-0 right-0 z-50 glass border-b border-plasma-cyan/20">
        <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
          {/* Logo */}
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-plasma-cyan to-plasma-purple flex items-center justify-center">
              <span className="font-display font-bold text-void">V</span>
            </div>
            <span className="font-display text-xl text-plasma-cyan tracking-wider">VEL</span>
          </div>

          {/* Navigation Links */}
          <div className="hidden md:flex items-center space-x-1">
            {navItems.map(({ path, icon: Icon, label }) => (
              <NavLink
                key={path}
                to={path}
                className={({ isActive }) =>
                  `flex items-center space-x-2 px-4 py-2 rounded-lg transition-all duration-300 ${
                    isActive
                      ? 'bg-plasma-cyan/20 text-plasma-cyan shadow-glow-cyan'
                      : 'text-gray-400 hover:text-plasma-cyan hover:bg-plasma-cyan/10'
                  }`
                }
              >
                <Icon size={18} />
                <span className="font-mono text-sm">{label}</span>
              </NavLink>
            ))}
          </div>

          {/* Right Side Actions */}
          <div className="flex items-center space-x-4">
            {/* Connection Status */}
            <div className="flex items-center space-x-2">
              <Activity 
                size={16} 
                className={connected ? 'text-neon-green animate-pulse' : 'text-neon-red'} 
              />
              <span className={`text-xs font-mono ${connected ? 'text-neon-green' : 'text-neon-red'}`}>
                {connected ? 'LIVE' : 'OFFLINE'}
              </span>
            </div>

            {/* Trading Status */}
            <div className={`px-3 py-1 rounded-full text-xs font-mono ${
              tradingStatus.status === 'active' 
                ? 'bg-neon-green/20 text-neon-green' 
                : 'bg-gray-500/20 text-gray-400'
            }`}>
              {tradingStatus.status === 'active' ? 'TRADING' : 'IDLE'}
            </div>

            {/* Notifications */}
            <button 
              onClick={() => setShowNotifications(!showNotifications)}
              className="relative p-2 rounded-lg hover:bg-plasma-cyan/10 transition-colors"
            >
              <Bell size={20} className="text-gray-400 hover:text-plasma-cyan" />
              {notifications.length > 0 && (
                <span className="absolute top-1 right-1 w-2 h-2 bg-neon-red rounded-full" />
              )}
            </button>

            {/* AI Assistant Toggle */}
            <button
              onClick={() => setShowAI(!showAI)}
              className={`p-2 rounded-lg transition-all duration-300 ${
                showAI 
                  ? 'bg-plasma-purple/20 text-plasma-purple shadow-glow-purple' 
                  : 'hover:bg-plasma-cyan/10 text-gray-400 hover:text-plasma-cyan'
              }`}
            >
              <Bot size={20} />
            </button>

            {/* Logout */}
            <button
              onClick={logout}
              className="p-2 rounded-lg hover:bg-neon-red/10 text-gray-400 hover:text-neon-red transition-colors"
            >
              <LogOut size={20} />
            </button>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="pt-20 pb-8 px-4 max-w-7xl mx-auto">
        <motion.div
          key={location.pathname}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -20 }}
          transition={{ duration: 0.3 }}
        >
          <Outlet />
        </motion.div>
      </main>

      {/* AI Assistant Sidebar */}
      <AIAssistant isOpen={showAI} onClose={() => setShowAI(false)} />

      {/* Notifications Panel */}
      {showNotifications && (
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          className="fixed top-20 right-4 w-80 glass rounded-xl p-4 z-50 max-h-96 overflow-y-auto"
        >
          <h3 className="font-display text-plasma-cyan mb-4">Notifications</h3>
          {notifications.length === 0 ? (
            <p className="text-gray-500 text-sm">No notifications</p>
          ) : (
            <div className="space-y-2">
              {notifications.slice(0, 10).map((notif) => (
                <div 
                  key={notif.id}
                  className={`p-2 rounded-lg text-xs font-mono ${
                    notif.type === 'trade' ? 'bg-plasma-cyan/10 text-plasma-cyan' :
                    notif.type === 'error' ? 'bg-neon-red/10 text-neon-red' :
                    'bg-gray-500/10 text-gray-400'
                  }`}
                >
                  {notif.message}
                </div>
              ))}
            </div>
          )}
        </motion.div>
      )}

      {/* Mobile Navigation */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 glass border-t border-plasma-cyan/20 px-4 py-2">
        <div className="flex justify-around">
          {navItems.map(({ path, icon: Icon, label }) => (
            <NavLink
              key={path}
              to={path}
              className={({ isActive }) =>
                `flex flex-col items-center p-2 rounded-lg transition-colors ${
                  isActive ? 'text-plasma-cyan' : 'text-gray-500'
                }`
              }
            >
              <Icon size={20} />
              <span className="text-xs mt-1">{label}</span>
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  )
}
