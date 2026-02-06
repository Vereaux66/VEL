import { useState } from 'react'
import { motion } from 'framer-motion'
import { 
  Wallet as WalletIcon, 
  ArrowUpRight, 
  ArrowDownLeft,
  Copy,
  ExternalLink,
  Shield,
  Star,
  Check
} from 'lucide-react'
import { SUBSCRIPTION_TIERS, formatCurrency } from '../utils/constants'

export default function Wallet() {
  const [activeTab, setActiveTab] = useState('overview')
  const [depositAmount, setDepositAmount] = useState('')
  const [withdrawAmount, setWithdrawAmount] = useState('')
  const [copied, setCopied] = useState(false)

  // Mock wallet data
  const walletData = {
    address: '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0',
    balance: 25420.50,
    available: 20420.50,
    locked: 5000,
    tier: 'pro',
    referralCode: 'VEL-X7K9M2',
    referralEarnings: 450
  }

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const transactions = [
    { id: 1, type: 'deposit', amount: 5000, status: 'completed', date: '2024-01-15', txHash: '0x123...' },
    { id: 2, type: 'withdrawal', amount: -1000, status: 'completed', date: '2024-01-10', txHash: '0x456...' },
    { id: 3, type: 'deposit', amount: 2500, status: 'pending', date: '2024-01-08', txHash: '0x789...' },
    { id: 4, type: 'referral', amount: 150, status: 'completed', date: '2024-01-05', txHash: '' }
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display text-plasma-cyan">Wallet</h1>
          <p className="text-gray-500 font-mono text-sm mt-1">Manage your funds and subscription</p>
        </div>
      </div>

      {/* Balance Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass rounded-xl p-6 border border-plasma-cyan/20"
        >
          <p className="text-gray-400 text-sm font-mono mb-1">Total Balance</p>
          <p className="text-3xl font-display text-plasma-cyan">{formatCurrency(walletData.balance)}</p>
          <div className="flex items-center mt-2 text-xs text-gray-500 font-mono">
            <WalletIcon size={14} className="mr-1" />
            {walletData.address.slice(0, 6)}...{walletData.address.slice(-4)}
            <button
              onClick={() => copyToClipboard(walletData.address)}
              className="ml-2 text-plasma-cyan hover:text-plasma-cyan/80"
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </button>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="glass rounded-xl p-6 border border-neon-green/20"
        >
          <p className="text-gray-400 text-sm font-mono mb-1">Available</p>
          <p className="text-3xl font-display text-neon-green">{formatCurrency(walletData.available)}</p>
          <p className="text-xs text-gray-500 mt-2 font-mono">Ready to trade</p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="glass rounded-xl p-6 border border-neon-yellow/20"
        >
          <p className="text-gray-400 text-sm font-mono mb-1">In Positions</p>
          <p className="text-3xl font-display text-neon-yellow">{formatCurrency(walletData.locked)}</p>
          <p className="text-xs text-gray-500 mt-2 font-mono">Currently trading</p>
        </motion.div>
      </div>

      {/* Tabs */}
      <div className="flex space-x-4 border-b border-gray-800">
        {['overview', 'deposit', 'withdraw', 'subscription'].map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`pb-4 px-2 font-mono text-sm transition-colors relative ${
              activeTab === tab ? 'text-plasma-cyan' : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
            {activeTab === tab && (
              <motion.div
                layoutId="activeTab"
                className="absolute bottom-0 left-0 right-0 h-0.5 bg-plasma-cyan"
              />
            )}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="glass rounded-xl p-6 border border-plasma-cyan/20"
        >
          <h3 className="font-display text-plasma-cyan mb-4">Recent Transactions</h3>
          <div className="space-y-3">
            {transactions.map((tx) => (
              <div
                key={tx.id}
                className="flex items-center justify-between p-4 rounded-xl bg-deep-space border border-gray-800"
              >
                <div className="flex items-center space-x-3">
                  <div className={`p-2 rounded-lg ${
                    tx.type === 'deposit' || tx.type === 'referral' 
                      ? 'bg-neon-green/20' 
                      : 'bg-neon-red/20'
                  }`}>
                    {tx.type === 'deposit' || tx.type === 'referral' 
                      ? <ArrowDownLeft size={18} className="text-neon-green" />
                      : <ArrowUpRight size={18} className="text-neon-red" />
                    }
                  </div>
                  <div>
                    <p className="font-mono text-white capitalize">{tx.type}</p>
                    <p className="text-xs text-gray-500">{tx.date}</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className={`font-mono ${tx.amount >= 0 ? 'text-neon-green' : 'text-neon-red'}`}>
                    {tx.amount >= 0 ? '+' : ''}{formatCurrency(tx.amount)}
                  </p>
                  <p className={`text-xs ${
                    tx.status === 'completed' ? 'text-neon-green' : 'text-neon-yellow'
                  }`}>
                    {tx.status}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {activeTab === 'deposit' && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="glass rounded-xl p-6 border border-plasma-cyan/20 max-w-md"
        >
          <h3 className="font-display text-plasma-cyan mb-4">Deposit Funds</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-mono text-gray-400 mb-2">Amount (USDT)</label>
              <input
                type="number"
                value={depositAmount}
                onChange={(e) => setDepositAmount(e.target.value)}
                placeholder="0.00"
                className="w-full bg-deep-space border border-plasma-cyan/30 rounded-xl px-4 py-3 font-mono text-white placeholder-gray-600 focus:outline-none focus:border-plasma-cyan transition-all"
              />
            </div>
            <div className="flex space-x-2">
              {[100, 500, 1000, 5000].map((amount) => (
                <button
                  key={amount}
                  onClick={() => setDepositAmount(amount.toString())}
                  className="flex-1 py-2 rounded-lg border border-gray-800 text-gray-400 hover:border-plasma-cyan/50 hover:text-plasma-cyan transition-colors font-mono text-sm"
                >
                  ${amount}
                </button>
              ))}
            </div>
            <button className="w-full py-4 rounded-xl bg-gradient-to-r from-plasma-cyan to-plasma-purple text-void font-display hover:opacity-90 transition-opacity">
              DEPOSIT
            </button>
          </div>
        </motion.div>
      )}

      {activeTab === 'withdraw' && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="glass rounded-xl p-6 border border-plasma-cyan/20 max-w-md"
        >
          <h3 className="font-display text-plasma-cyan mb-4">Withdraw Funds</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-mono text-gray-400 mb-2">Amount (USDT)</label>
              <input
                type="number"
                value={withdrawAmount}
                onChange={(e) => setWithdrawAmount(e.target.value)}
                placeholder="0.00"
                max={walletData.available}
                className="w-full bg-deep-space border border-plasma-cyan/30 rounded-xl px-4 py-3 font-mono text-white placeholder-gray-600 focus:outline-none focus:border-plasma-cyan transition-all"
              />
              <p className="text-xs text-gray-500 mt-1">
                Available: {formatCurrency(walletData.available)}
              </p>
            </div>
            <button 
              onClick={() => setWithdrawAmount(walletData.available.toString())}
              className="text-plasma-cyan text-sm font-mono hover:underline"
            >
              Withdraw Max
            </button>
            <button className="w-full py-4 rounded-xl bg-gradient-to-r from-neon-red to-neon-orange text-void font-display hover:opacity-90 transition-opacity">
              WITHDRAW
            </button>
          </div>
        </motion.div>
      )}

      {activeTab === 'subscription' && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="space-y-6"
        >
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {SUBSCRIPTION_TIERS.map((tier, index) => (
              <motion.div
                key={tier.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1 }}
                className={`glass rounded-xl p-6 border ${
                  walletData.tier === tier.id 
                    ? 'border-plasma-cyan shadow-glow-cyan' 
                    : 'border-gray-800'
                }`}
              >
                {walletData.tier === tier.id && (
                  <div className="flex items-center space-x-1 text-plasma-cyan text-xs font-mono mb-4">
                    <Star size={14} />
                    <span>CURRENT PLAN</span>
                  </div>
                )}
                <h3 className="font-display text-xl text-white mb-2">{tier.name}</h3>
                <p className="text-3xl font-display text-plasma-cyan mb-4">
                  ${tier.price}<span className="text-sm text-gray-500">/mo</span>
                </p>
                <ul className="space-y-2 mb-6">
                  {tier.features.map((feature, i) => (
                    <li key={i} className="flex items-center text-sm text-gray-400 font-mono">
                      <Check size={14} className="mr-2 text-neon-green" />
                      {feature}
                    </li>
                  ))}
                </ul>
                {walletData.tier !== tier.id && (
                  <button className="w-full py-3 rounded-xl border border-plasma-cyan/30 text-plasma-cyan hover:bg-plasma-cyan/10 transition-colors font-mono">
                    {tier.price === 0 ? 'Downgrade' : 'Upgrade'}
                  </button>
                )}
              </motion.div>
            ))}
          </div>

          {/* Referral Section */}
          <div className="glass rounded-xl p-6 border border-plasma-purple/20">
            <h3 className="font-display text-plasma-purple mb-4 flex items-center">
              <Shield size={20} className="mr-2" />
              Referral Program
            </h3>
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <p className="text-gray-400 text-sm font-mono mb-2">Your Referral Code</p>
                <div className="flex items-center space-x-2">
                  <code className="px-4 py-2 bg-deep-space rounded-lg font-mono text-plasma-purple text-lg">
                    {walletData.referralCode}
                  </code>
                  <button
                    onClick={() => copyToClipboard(walletData.referralCode)}
                    className="p-2 rounded-lg bg-plasma-purple/10 text-plasma-purple hover:bg-plasma-purple/20 transition-colors"
                  >
                    <Copy size={18} />
                  </button>
                </div>
              </div>
              <div className="text-right">
                <p className="text-gray-400 text-sm font-mono">Total Earnings</p>
                <p className="text-2xl font-display text-neon-green">
                  {formatCurrency(walletData.referralEarnings)}
                </p>
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </div>
  )
}
