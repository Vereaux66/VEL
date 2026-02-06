// Trading pairs
export const TRADING_PAIRS = [
  { symbol: 'BTC/USDT', name: 'Bitcoin', icon: '₿' },
  { symbol: 'ETH/USDT', name: 'Ethereum', icon: 'Ξ' },
  { symbol: 'BNB/USDT', name: 'Binance Coin', icon: 'B' },
  { symbol: 'SOL/USDT', name: 'Solana', icon: 'S' },
  { symbol: 'XRP/USDT', name: 'Ripple', icon: 'X' },
  { symbol: 'ADA/USDT', name: 'Cardano', icon: 'A' },
  { symbol: 'DOGE/USDT', name: 'Dogecoin', icon: 'D' },
  { symbol: 'AVAX/USDT', name: 'Avalanche', icon: 'Λ' }
]

// Trading strategies
export const STRATEGIES = [
  {
    id: 'ai_composite',
    name: 'AI Composite',
    description: 'Multi-model AI ensemble for optimal trade selection',
    riskLevel: 'medium'
  },
  {
    id: 'momentum',
    name: 'Momentum',
    description: 'Trend-following strategy using price momentum',
    riskLevel: 'high'
  },
  {
    id: 'mean_reversion',
    name: 'Mean Reversion',
    description: 'Profit from price returning to average',
    riskLevel: 'medium'
  },
  {
    id: 'arbitrage',
    name: 'Arbitrage',
    description: 'Cross-exchange price difference exploitation',
    riskLevel: 'low'
  },
  {
    id: 'scalping',
    name: 'Scalping',
    description: 'High-frequency small profit trades',
    riskLevel: 'high'
  }
]

// Risk levels
export const RISK_LEVELS = [
  { id: 'conservative', name: 'Conservative', maxDrawdown: 5, color: 'neon-green' },
  { id: 'moderate', name: 'Moderate', maxDrawdown: 10, color: 'plasma-cyan' },
  { id: 'aggressive', name: 'Aggressive', maxDrawdown: 20, color: 'neon-orange' },
  { id: 'high_risk', name: 'High Risk', maxDrawdown: 30, color: 'neon-red' }
]

// Subscription tiers
export const SUBSCRIPTION_TIERS = [
  {
    id: 'starter',
    name: 'Starter',
    price: 0,
    features: ['Basic trading', '3 strategies', 'Daily reports', 'Community support']
  },
  {
    id: 'pro',
    name: 'Pro',
    price: 49,
    features: ['All strategies', 'Real-time signals', 'Priority support', 'AI assistant']
  },
  {
    id: 'elite',
    name: 'Elite',
    price: 199,
    features: ['Custom strategies', 'Dedicated account manager', 'API access', 'White-label']
  }
]

// Chart colors
export const CHART_COLORS = {
  profit: '#00ff41',
  loss: '#ff073a',
  primary: '#00ffff',
  secondary: '#bf00ff',
  neutral: '#666'
}

// Crypto symbols for matrix rain - 100 popular cryptocurrency ticker symbols
export const CRYPTO_SYMBOLS = [
  // Top 20
  'BTC', 'ETH', 'BNB', 'XRP', 'ADA', 'SOL', 'DOGE', 'DOT', 'AVAX', 'SHIB',
  'MATIC', 'LTC', 'TRX', 'LINK', 'ATOM', 'UNI', 'XMR', 'ETC', 'XLM', 'BCH',
  // 21-40
  'ALGO', 'NEAR', 'VET', 'ICP', 'FIL', 'HBAR', 'APE', 'SAND', 'MANA', 'AXS',
  'AAVE', 'EGLD', 'THETA', 'EOS', 'XTZ', 'FLOW', 'CHZ', 'CAKE', 'KCS', 'ZEC',
  // 41-60
  'MKR', 'SNX', 'COMP', 'ENJ', 'BAT', 'LRC', 'DASH', 'NEO', 'WAVES', 'ZIL',
  'QTUM', 'ICX', 'BTT', 'ONE', 'HOT', 'IOTA', 'ONT', 'CELO', 'KSM', 'RUNE',
  // 61-80
  'CRV', 'YFI', 'SUSHI', 'GRT', '1INCH', 'KAVA', 'ANKR', 'AR', 'STORJ', 'REN',
  'SKL', 'BAND', 'OCEAN', 'AUDIO', 'RAY', 'SRM', 'FTM', 'LUNA', 'GALA', 'IMX',
  // 81-100
  'LDO', 'APT', 'OP', 'ARB', 'SUI', 'SEI', 'TIA', 'INJ', 'PYTH', 'JTO',
  'WIF', 'BONK', 'PEPE', 'FLOKI', 'ORDI', 'BLUR', 'STX', 'MINA', 'CFX', 'FET'
]

// Format number as currency
export function formatCurrency(value, decimals = 2) {
  if (value == null || isNaN(value)) return '$0.00'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  }).format(Number(value))
}

// Format percentage
export function formatPercentage(value, decimals = 2) {
  const formatted = (value * 100).toFixed(decimals)
  const prefix = value >= 0 ? '+' : ''
  return `${prefix}${formatted}%`
}

// Format large numbers
export function formatNumber(value) {
  if (value == null || isNaN(value)) return '0'
  const num = Math.abs(Number(value))
  const sign = value < 0 ? '-' : ''
  if (num >= 1e9) return sign + (num / 1e9).toFixed(2) + 'B'
  if (num >= 1e6) return sign + (num / 1e6).toFixed(2) + 'M'
  if (num >= 1e3) return sign + (num / 1e3).toFixed(2) + 'K'
  return sign + num.toFixed(2)
}

// Format date/time
export function formatDateTime(date) {
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  }).format(new Date(date))
}
