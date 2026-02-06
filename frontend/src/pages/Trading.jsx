import { useState } from 'react'
import { motion } from 'framer-motion'
import { 
  Play, 
  Square, 
  Settings2, 
  AlertTriangle,
  TrendingUp,
  Shield,
  Zap,
  Brain
} from 'lucide-react'
import { tradingApi } from '../utils/api'
import { useWebSocket } from '../context/WebSocketContext'
import { STRATEGIES, RISK_LEVELS, TRADING_PAIRS } from '../utils/constants'

export default function Trading() {
  const { tradingStatus, realtimePrices } = useWebSocket()
  const [selectedStrategy, setSelectedStrategy] = useState('ai_composite')
  const [riskLevel, setRiskLevel] = useState('moderate')
  const [maxPositions, setMaxPositions] = useState(5)
  const [selectedPairs, setSelectedPairs] = useState(['BTC/USDT', 'ETH/USDT'])
  const [loading, setLoading] = useState(false)
  const [showConfirmation, setShowConfirmation] = useState(false)

  const isActive = tradingStatus.status === 'active'

  const handleStartTrading = async () => {
    if (riskLevel === 'high_risk' && !showConfirmation) {
      setShowConfirmation(true)
      return
    }

    setLoading(true)
    try {
      await tradingApi.startTrading({
        strategy: selectedStrategy,
        risk_level: riskLevel,
        max_positions: maxPositions,
        pairs: selectedPairs
      })
    } catch (error) {
      console.error('Failed to start trading:', error)
    } finally {
      setLoading(false)
      setShowConfirmation(false)
    }
  }

  const handleStopTrading = async () => {
    setLoading(true)
    try {
      await tradingApi.stopTrading(false)
    } catch (error) {
      console.error('Failed to stop trading:', error)
    } finally {
      setLoading(false)
    }
  }

  const togglePair = (pair) => {
    setSelectedPairs(prev => 
      prev.includes(pair)
        ? prev.filter(p => p !== pair)
        : [...prev, pair]
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display text-plasma-cyan">Trading Terminal</h1>
          <p className="text-gray-500 font-mono text-sm mt-1">Configure and control automated trading</p>
        </div>
        <div className={`flex items-center space-x-2 px-4 py-2 rounded-xl ${
          isActive ? 'bg-neon-green/20 text-neon-green' : 'bg-gray-500/20 text-gray-400'
        }`}>
          <span className={`w-2 h-2 rounded-full ${isActive ? 'bg-neon-green animate-pulse' : 'bg-gray-500'}`} />
          <span className="font-mono text-sm">{isActive ? 'TRADING ACTIVE' : 'IDLE'}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Strategy Selection */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="lg:col-span-2 glass rounded-xl p-6 border border-plasma-cyan/20"
        >
          <h3 className="font-display text-plasma-cyan mb-4 flex items-center">
            <Brain size={20} className="mr-2" />
            Trading Strategy
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {STRATEGIES.map((strategy) => (
              <button
                key={strategy.id}
                onClick={() => setSelectedStrategy(strategy.id)}
                disabled={isActive}
                className={`p-4 rounded-xl border text-left transition-all ${
                  selectedStrategy === strategy.id
                    ? 'border-plasma-cyan bg-plasma-cyan/10'
                    : 'border-gray-800 hover:border-plasma-cyan/50 bg-deep-space'
                } ${isActive ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <div className="flex items-center justify-between mb-2">
                  <h4 className="font-mono text-white">{strategy.name}</h4>
                  <span className={`text-xs px-2 py-1 rounded ${
                    strategy.riskLevel === 'low' ? 'bg-neon-green/20 text-neon-green' :
                    strategy.riskLevel === 'medium' ? 'bg-neon-yellow/20 text-neon-yellow' :
                    'bg-neon-red/20 text-neon-red'
                  }`}>
                    {strategy.riskLevel.toUpperCase()}
                  </span>
                </div>
                <p className="text-sm text-gray-500">{strategy.description}</p>
              </button>
            ))}
          </div>
        </motion.div>

        {/* Risk Configuration */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="glass rounded-xl p-6 border border-plasma-cyan/20"
        >
          <h3 className="font-display text-plasma-cyan mb-4 flex items-center">
            <Shield size={20} className="mr-2" />
            Risk Level
          </h3>
          <div className="space-y-3">
            {RISK_LEVELS.map((level) => (
              <button
                key={level.id}
                onClick={() => setRiskLevel(level.id)}
                disabled={isActive}
                className={`w-full p-3 rounded-xl border text-left transition-all flex items-center justify-between ${
                  riskLevel === level.id
                    ? 'border-plasma-cyan bg-plasma-cyan/10'
                    : 'border-gray-800 hover:border-plasma-cyan/50 bg-deep-space'
                } ${isActive ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <div>
                  <p className="font-mono text-white">{level.name}</p>
                  <p className="text-xs text-gray-500">Max drawdown: {level.maxDrawdown}%</p>
                </div>
                {riskLevel === level.id && (
                  <div className="w-3 h-3 rounded-full bg-plasma-cyan" />
                )}
              </button>
            ))}
          </div>

          <div className="mt-6">
            <label className="block text-sm font-mono text-gray-400 mb-2">
              Max Positions: {maxPositions}
            </label>
            <input
              type="range"
              min="1"
              max="20"
              value={maxPositions}
              onChange={(e) => setMaxPositions(parseInt(e.target.value))}
              disabled={isActive}
              className="w-full h-2 bg-deep-space rounded-lg appearance-none cursor-pointer accent-plasma-cyan disabled:opacity-50"
            />
          </div>
        </motion.div>
      </div>

      {/* Trading Pairs */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="glass rounded-xl p-6 border border-plasma-cyan/20"
      >
        <h3 className="font-display text-plasma-cyan mb-4 flex items-center">
          <TrendingUp size={20} className="mr-2" />
          Trading Pairs
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {TRADING_PAIRS.map((pair) => (
            <button
              key={pair.symbol}
              onClick={() => togglePair(pair.symbol)}
              disabled={isActive}
              className={`p-4 rounded-xl border transition-all ${
                selectedPairs.includes(pair.symbol)
                  ? 'border-plasma-cyan bg-plasma-cyan/10'
                  : 'border-gray-800 hover:border-plasma-cyan/50 bg-deep-space'
              } ${isActive ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <div className="flex items-center space-x-3">
                <span className="text-2xl">{pair.icon}</span>
                <div className="text-left">
                  <p className="font-mono text-white text-sm">{pair.symbol}</p>
                  <p className="text-xs text-gray-500">{pair.name}</p>
                </div>
              </div>
            </button>
          ))}
        </div>
      </motion.div>

      {/* Control Panel */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="glass rounded-xl p-6 border border-plasma-cyan/20"
      >
        <div className="flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center space-x-4">
            <Zap size={24} className="text-plasma-cyan" />
            <div>
              <p className="font-mono text-white">
                {isActive 
                  ? `Trading ${tradingStatus.strategy || selectedStrategy} on ${selectedPairs.length} pairs`
                  : 'Ready to start trading'
                }
              </p>
              <p className="text-sm text-gray-500">
                {isActive 
                  ? `Risk level: ${tradingStatus.risk_level || riskLevel}`
                  : `Selected: ${STRATEGIES.find(s => s.id === selectedStrategy)?.name}`
                }
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-4">
            {isActive ? (
              <button
                onClick={handleStopTrading}
                disabled={loading}
                className="flex items-center space-x-2 px-6 py-3 rounded-xl bg-neon-red/20 text-neon-red border border-neon-red/30 hover:bg-neon-red/30 transition-colors disabled:opacity-50"
              >
                <Square size={20} />
                <span className="font-mono">{loading ? 'STOPPING...' : 'STOP TRADING'}</span>
              </button>
            ) : (
              <button
                onClick={handleStartTrading}
                disabled={loading || selectedPairs.length === 0}
                className="flex items-center space-x-2 px-6 py-3 rounded-xl bg-gradient-to-r from-plasma-cyan to-plasma-purple text-void hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Play size={20} />
                <span className="font-mono">{loading ? 'STARTING...' : 'START TRADING'}</span>
              </button>
            )}
          </div>
        </div>
      </motion.div>

      {/* High Risk Confirmation Modal */}
      {showConfirmation && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-void/80 backdrop-blur-sm">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="glass rounded-xl p-6 max-w-md border border-neon-red/30"
          >
            <div className="flex items-center space-x-3 mb-4">
              <AlertTriangle size={24} className="text-neon-red" />
              <h3 className="font-display text-neon-red">High Risk Warning</h3>
            </div>
            <p className="text-gray-300 font-mono text-sm mb-6">
              You are about to start trading with HIGH RISK settings. 
              Maximum drawdown is set to 30%. This could result in significant losses.
              Are you sure you want to proceed?
            </p>
            <div className="flex justify-end space-x-4">
              <button
                onClick={() => setShowConfirmation(false)}
                className="px-4 py-2 rounded-lg border border-gray-700 text-gray-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleStartTrading}
                className="px-4 py-2 rounded-lg bg-neon-red/20 text-neon-red border border-neon-red/30 hover:bg-neon-red/30 transition-colors"
              >
                Confirm & Start
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  )
}
