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

// Crypto symbols for matrix rain
export const CRYPTO_SYMBOLS = ['₿', 'Ξ', '◈', '₳', '◎', 'Ð', '₮', '◐', '⟠', '◉']

// Format number as currency
export function formatCurrency(value, decimals = 2) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  }).format(value)
}

// Format percentage
export function formatPercentage(value, decimals = 2) {
  const formatted = (value * 100).toFixed(decimals)
  const prefix = value >= 0 ? '+' : ''
  return `${prefix}${formatted}%`
}

// Format large numbers
export function formatNumber(value) {
  if (value >= 1e9) return (value / 1e9).toFixed(2) + 'B'
  if (value >= 1e6) return (value / 1e6).toFixed(2) + 'M'
  if (value >= 1e3) return (value / 1e3).toFixed(2) + 'K'
  return value.toFixed(2)
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
