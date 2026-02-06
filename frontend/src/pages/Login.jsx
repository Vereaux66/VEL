import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Lock, User, Key, AlertCircle, Eye, EyeOff } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import MatrixRain from '../components/MatrixRain'

export default function Login() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [showTotp, setShowTotp] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [doorsOpen, setDoorsOpen] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    const result = await login(username, password, showTotp ? totpCode : null)

    if (result.success) {
      // Trigger door opening animation
      setDoorsOpen(true)
    } else {
      setError(result.error)
      // Check if 2FA is required
      if (result.error?.includes('2FA')) {
        setShowTotp(true)
      }
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-void relative overflow-hidden">
      {/* Matrix Rain Background */}
      <MatrixRain />

      {/* Blast Doors */}
      <AnimatePresence>
        {!doorsOpen && (
          <>
            {/* Left Door */}
            <motion.div
              initial={{ x: 0 }}
              animate={doorsOpen ? { x: '-100%' } : { x: 0 }}
              exit={{ x: '-100%' }}
              transition={{ duration: 1.5, ease: [0.4, 0, 0.2, 1] }}
              className="fixed inset-y-0 left-0 w-1/2 bg-deep-space z-40"
            >
              <div className="absolute inset-0 flex items-center justify-end pr-8">
                <div className="space-y-4">
                  {[...Array(8)].map((_, i) => (
                    <div
                      key={i}
                      className="w-64 h-2 bg-gradient-to-r from-plasma-cyan/20 to-transparent rounded-full"
                      style={{ animationDelay: `${i * 0.1}s` }}
                    />
                  ))}
                </div>
              </div>
              <div className="absolute bottom-8 left-8 font-display text-xs text-plasma-cyan/50 tracking-widest">
                BLAST DOOR A-1
              </div>
              {/* Hydraulic Lines */}
              <div className="absolute right-0 top-0 bottom-0 w-4 bg-gradient-to-l from-plasma-cyan/10 to-transparent" />
            </motion.div>

            {/* Right Door */}
            <motion.div
              initial={{ x: 0 }}
              animate={doorsOpen ? { x: '100%' } : { x: 0 }}
              exit={{ x: '100%' }}
              transition={{ duration: 1.5, ease: [0.4, 0, 0.2, 1] }}
              className="fixed inset-y-0 right-0 w-1/2 bg-deep-space z-40"
            >
              <div className="absolute inset-0 flex items-center justify-start pl-8">
                <div className="space-y-4">
                  {[...Array(8)].map((_, i) => (
                    <div
                      key={i}
                      className="w-64 h-2 bg-gradient-to-l from-plasma-cyan/20 to-transparent rounded-full"
                      style={{ animationDelay: `${i * 0.1}s` }}
                    />
                  ))}
                </div>
              </div>
              <div className="absolute bottom-8 right-8 font-display text-xs text-plasma-cyan/50 tracking-widest">
                BLAST DOOR A-2
              </div>
              {/* Hydraulic Lines */}
              <div className="absolute left-0 top-0 bottom-0 w-4 bg-gradient-to-r from-plasma-cyan/10 to-transparent" />
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Login Form */}
      <div className="relative z-30 min-h-screen flex items-center justify-center p-4">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.2 }}
          className="w-full max-w-md"
        >
          {/* Logo */}
          <div className="text-center mb-8">
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: 'spring', delay: 0.3 }}
              className="inline-block"
            >
              <div className="w-20 h-20 mx-auto rounded-2xl bg-gradient-to-br from-plasma-cyan via-plasma-purple to-plasma-magenta p-[2px]">
                <div className="w-full h-full bg-void rounded-2xl flex items-center justify-center">
                  <span className="font-display text-4xl font-bold text-plasma-cyan text-glow-cyan">V</span>
                </div>
              </div>
            </motion.div>
            <h1 className="mt-4 font-display text-3xl text-plasma-cyan tracking-wider text-glow-cyan">
              VEL
            </h1>
            <p className="mt-2 text-gray-500 font-mono text-sm">
              Decentralized Autonomous Trading
            </p>
          </div>

          {/* Form Card */}
          <motion.div
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.4 }}
            className="glass rounded-2xl p-8 border border-plasma-cyan/20"
          >
            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Username */}
              <div>
                <label className="block text-sm font-mono text-gray-400 mb-2">
                  Username
                </label>
                <div className="relative">
                  <User className="absolute left-4 top-1/2 -translate-y-1/2 text-plasma-cyan/50" size={18} />
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className="w-full bg-deep-space border border-plasma-cyan/30 rounded-xl pl-12 pr-4 py-3 font-mono text-white placeholder-gray-600 focus:outline-none focus:border-plasma-cyan focus:shadow-glow-cyan transition-all"
                    placeholder="Enter username"
                    required
                  />
                </div>
              </div>

              {/* Password */}
              <div>
                <label className="block text-sm font-mono text-gray-400 mb-2">
                  Password
                </label>
                <div className="relative">
                  <Lock className="absolute left-4 top-1/2 -translate-y-1/2 text-plasma-cyan/50" size={18} />
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full bg-deep-space border border-plasma-cyan/30 rounded-xl pl-12 pr-12 py-3 font-mono text-white placeholder-gray-600 focus:outline-none focus:border-plasma-cyan focus:shadow-glow-cyan transition-all"
                    placeholder="Enter password"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 hover:text-plasma-cyan"
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>

              {/* 2FA Code */}
              <AnimatePresence>
                {showTotp && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                  >
                    <label className="block text-sm font-mono text-gray-400 mb-2">
                      2FA Code
                    </label>
                    <div className="relative">
                      <Key className="absolute left-4 top-1/2 -translate-y-1/2 text-plasma-purple/50" size={18} />
                      <input
                        type="text"
                        value={totpCode}
                        onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                        className="w-full bg-deep-space border border-plasma-purple/30 rounded-xl pl-12 pr-4 py-3 font-mono text-white placeholder-gray-600 focus:outline-none focus:border-plasma-purple focus:shadow-glow-purple transition-all tracking-[0.5em] text-center"
                        placeholder="000000"
                        maxLength={6}
                      />
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Error Message */}
              <AnimatePresence>
                {error && (
                  <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    className="flex items-center space-x-2 text-neon-red text-sm font-mono bg-neon-red/10 rounded-xl p-3"
                  >
                    <AlertCircle size={18} />
                    <span>{error}</span>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={loading}
                className="w-full py-4 rounded-xl bg-gradient-to-r from-plasma-cyan to-plasma-purple font-display text-void text-lg tracking-wider hover:opacity-90 transition-all disabled:opacity-50 disabled:cursor-not-allowed relative overflow-hidden group"
              >
                <span className="relative z-10">
                  {loading ? 'AUTHENTICATING...' : 'ACCESS SYSTEM'}
                </span>
                <div className="absolute inset-0 bg-gradient-to-r from-plasma-purple to-plasma-cyan opacity-0 group-hover:opacity-100 transition-opacity" />
              </button>
            </form>

            {/* Footer */}
            <div className="mt-6 text-center">
              <p className="text-xs text-gray-600 font-mono">
                Secure encrypted connection • AES-256-GCM
              </p>
            </div>
          </motion.div>

          {/* Warning Banner */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.6 }}
            className="mt-6 p-4 rounded-xl border border-neon-red/30 bg-neon-red/5"
          >
            <p className="text-xs text-neon-red/80 font-mono text-center">
              ⚠️ AUTHORIZED PERSONNEL ONLY • All access attempts are logged
            </p>
          </motion.div>
        </motion.div>
      </div>
    </div>
  )
}
