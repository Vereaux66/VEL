import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { 
  TrendingUp, 
  TrendingDown, 
  Activity, 
  PieChart,
  DollarSign,
  Percent,
  BarChart3,
  ArrowUpRight,
  ArrowDownRight
} from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts'
import { dashboardApi } from '../utils/api'
import { useWebSocket } from '../context/WebSocketContext'
import { formatCurrency, formatPercentage, formatDateTime, CHART_COLORS } from '../utils/constants'

export default function Dashboard() {
  const { portfolioData, realtimePrices, tradingStatus } = useWebSocket()
  const [dashboardData, setDashboardData] = useState(null)
  const [performanceData, setPerformanceData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [timeframe, setTimeframe] = useState('30d')

  useEffect(() => {
    loadDashboard()
  }, [timeframe])

  const loadDashboard = async () => {
    try {
      const [dashboard, performance] = await Promise.all([
        dashboardApi.getData(),
        dashboardApi.getPerformance(timeframe)
      ])
      setDashboardData(dashboard)
      setPerformanceData(performance.daily)
    } catch (error) {
      console.error('Failed to load dashboard:', error)
    } finally {
      setLoading(false)
    }
  }

  const metrics = dashboardData?.metrics || {
    totalPnl: 12500,
    winRate: 0.67,
    sharpeRatio: 1.85,
    maxDrawdown: -0.08,
    totalTrades: 156,
    activePositions: 4
  }

  const portfolio = dashboardData?.portfolio || [
    { asset: 'BTC', quantity: 0.5, avgPrice: 42000, currentPrice: 45000, pnl: 0.071 },
    { asset: 'ETH', quantity: 5, avgPrice: 2300, currentPrice: 2500, pnl: 0.087 },
    { asset: 'SOL', quantity: 100, avgPrice: 95, currentPrice: 110, pnl: 0.158 },
    { asset: 'USDT', quantity: 10000, avgPrice: 1, currentPrice: 1, pnl: 0 }
  ]

  const trades = dashboardData?.trades || [
    { id: 1, timestamp: new Date(), pair: 'BTC/USDT', side: 'BUY', price: 44500, quantity: 0.1, total: 4450, pnl: 225, status: 'completed' },
    { id: 2, timestamp: new Date(), pair: 'ETH/USDT', side: 'SELL', price: 2480, quantity: 2, total: 4960, pnl: 180, status: 'completed' },
    { id: 3, timestamp: new Date(), pair: 'SOL/USDT', side: 'BUY', price: 108, quantity: 50, total: 5400, pnl: -75, status: 'completed' }
  ]

  // Mock performance data if not loaded
  const chartData = performanceData || [
    { date: '2024-01-01', profits: 1200, losses: 400, trades: 15, avgPnl: 53 },
    { date: '2024-01-02', profits: 800, losses: 600, trades: 12, avgPnl: 17 },
    { date: '2024-01-03', profits: 1500, losses: 300, trades: 18, avgPnl: 67 },
    { date: '2024-01-04', profits: 900, losses: 450, trades: 14, avgPnl: 32 },
    { date: '2024-01-05', profits: 1100, losses: 200, trades: 16, avgPnl: 56 },
    { date: '2024-01-06', profits: 1800, losses: 350, trades: 20, avgPnl: 73 },
    { date: '2024-01-07', profits: 600, losses: 800, trades: 10, avgPnl: -20 }
  ]

  const StatCard = ({ icon: Icon, label, value, change, color }) => (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-xl p-6 border border-plasma-cyan/20 hover:border-plasma-cyan/40 transition-colors"
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="text-gray-400 text-sm font-mono mb-1">{label}</p>
          <p className={`text-2xl font-display ${color || 'text-plasma-cyan'}`}>{value}</p>
          {change !== undefined && (
            <div className={`flex items-center mt-2 text-sm ${change >= 0 ? 'text-neon-green' : 'text-neon-red'}`}>
              {change >= 0 ? <ArrowUpRight size={16} /> : <ArrowDownRight size={16} />}
              <span className="font-mono">{formatPercentage(change)}</span>
            </div>
          )}
        </div>
        <div className={`p-3 rounded-xl ${color === 'text-neon-green' ? 'bg-neon-green/10' : color === 'text-neon-red' ? 'bg-neon-red/10' : 'bg-plasma-cyan/10'}`}>
          <Icon size={24} className={color || 'text-plasma-cyan'} />
        </div>
      </div>
    </motion.div>
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display text-plasma-cyan">Dashboard</h1>
          <p className="text-gray-500 font-mono text-sm mt-1">Real-time portfolio overview</p>
        </div>
        <div className="flex items-center space-x-2">
          {['24h', '7d', '30d', '1y'].map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={`px-4 py-2 rounded-lg font-mono text-sm transition-all ${
                timeframe === tf
                  ? 'bg-plasma-cyan/20 text-plasma-cyan'
                  : 'text-gray-400 hover:text-plasma-cyan hover:bg-plasma-cyan/10'
              }`}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={DollarSign}
          label="Total P&L"
          value={formatCurrency(metrics.totalPnl)}
          change={0.125}
          color={metrics.totalPnl >= 0 ? 'text-neon-green' : 'text-neon-red'}
        />
        <StatCard
          icon={Percent}
          label="Win Rate"
          value={`${(metrics.winRate * 100).toFixed(1)}%`}
          change={0.05}
          color="text-plasma-cyan"
        />
        <StatCard
          icon={BarChart3}
          label="Sharpe Ratio"
          value={metrics.sharpeRatio.toFixed(2)}
          color="text-plasma-purple"
        />
        <StatCard
          icon={Activity}
          label="Active Positions"
          value={metrics.activePositions}
          color="text-neon-yellow"
        />
      </div>

      {/* Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* P&L Chart */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="glass rounded-xl p-6 border border-plasma-cyan/20"
        >
          <h3 className="font-display text-plasma-cyan mb-4">Performance</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="profitGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={CHART_COLORS.profit} stopOpacity={0.3}/>
                    <stop offset="95%" stopColor={CHART_COLORS.profit} stopOpacity={0}/>
                  </linearGradient>
                  <linearGradient id="lossGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={CHART_COLORS.loss} stopOpacity={0.3}/>
                    <stop offset="95%" stopColor={CHART_COLORS.loss} stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                <XAxis dataKey="date" stroke="#666" tick={{ fill: '#666', fontSize: 12 }} />
                <YAxis stroke="#666" tick={{ fill: '#666', fontSize: 12 }} />
                <Tooltip
                  contentStyle={{ background: '#0a0a0f', border: '1px solid #00ffff33', borderRadius: 8 }}
                  labelStyle={{ color: '#00ffff' }}
                />
                <Area type="monotone" dataKey="profits" stroke={CHART_COLORS.profit} fill="url(#profitGradient)" />
                <Area type="monotone" dataKey="losses" stroke={CHART_COLORS.loss} fill="url(#lossGradient)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </motion.div>

        {/* Portfolio Allocation */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="glass rounded-xl p-6 border border-plasma-cyan/20"
        >
          <h3 className="font-display text-plasma-cyan mb-4">Portfolio</h3>
          <div className="space-y-4">
            {portfolio.map((asset, index) => (
              <div key={asset.asset} className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-full bg-gradient-to-br from-plasma-cyan to-plasma-purple flex items-center justify-center font-display text-void text-sm">
                    {asset.asset.charAt(0)}
                  </div>
                  <div>
                    <p className="font-mono text-white">{asset.asset}</p>
                    <p className="text-xs text-gray-500">{asset.quantity} units</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="font-mono text-white">{formatCurrency(asset.currentPrice * asset.quantity)}</p>
                  <p className={`text-xs ${asset.pnl >= 0 ? 'text-neon-green' : 'text-neon-red'}`}>
                    {formatPercentage(asset.pnl)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      </div>

      {/* Recent Trades */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="glass rounded-xl p-6 border border-plasma-cyan/20"
      >
        <h3 className="font-display text-plasma-cyan mb-4">Recent Trades</h3>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-gray-500 text-sm font-mono border-b border-gray-800">
                <th className="pb-3">Time</th>
                <th className="pb-3">Pair</th>
                <th className="pb-3">Side</th>
                <th className="pb-3">Price</th>
                <th className="pb-3">Quantity</th>
                <th className="pb-3">Total</th>
                <th className="pb-3">P&L</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade) => (
                <tr key={trade.id} className="border-b border-gray-800/50 hover:bg-plasma-cyan/5 transition-colors">
                  <td className="py-3 font-mono text-sm text-gray-400">
                    {formatDateTime(trade.timestamp)}
                  </td>
                  <td className="py-3 font-mono text-white">{trade.pair}</td>
                  <td className="py-3">
                    <span className={`px-2 py-1 rounded text-xs font-mono ${
                      trade.side === 'BUY' ? 'bg-neon-green/20 text-neon-green' : 'bg-neon-red/20 text-neon-red'
                    }`}>
                      {trade.side}
                    </span>
                  </td>
                  <td className="py-3 font-mono text-gray-300">{formatCurrency(trade.price)}</td>
                  <td className="py-3 font-mono text-gray-300">{trade.quantity}</td>
                  <td className="py-3 font-mono text-gray-300">{formatCurrency(trade.total)}</td>
                  <td className={`py-3 font-mono ${trade.pnl >= 0 ? 'text-neon-green' : 'text-neon-red'}`}>
                    {trade.pnl >= 0 ? '+' : ''}{formatCurrency(trade.pnl)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </motion.div>
    </div>
  )
}
