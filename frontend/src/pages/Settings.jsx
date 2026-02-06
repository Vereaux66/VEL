import { useState } from 'react'
import { motion } from 'framer-motion'
import { 
  User, 
  Bell, 
  Shield, 
  Key,
  Moon,
  Sun,
  Save,
  LogOut,
  Smartphone,
  Mail,
  Globe
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'

export default function Settings() {
  const { logout } = useAuth()
  const [activeTab, setActiveTab] = useState('account')
  const [saving, setSaving] = useState(false)

  // Settings state
  const [settings, setSettings] = useState({
    // Account
    username: 'trader_001',
    email: 'trader@example.com',
    timezone: 'UTC',
    
    // Notifications
    emailNotifications: true,
    pushNotifications: true,
    tradeAlerts: true,
    priceAlerts: true,
    weeklyReports: true,
    
    // Security
    twoFactorEnabled: true,
    sessionTimeout: 30,
    
    // Display
    darkMode: true,
    compactView: false,
    showPnlPercentage: true
  })

  const handleSave = async () => {
    setSaving(true)
    // Simulate API call
    await new Promise(resolve => setTimeout(resolve, 1000))
    setSaving(false)
  }

  const updateSetting = (key, value) => {
    setSettings(prev => ({ ...prev, [key]: value }))
  }

  const ToggleSwitch = ({ checked, onChange, label, description }) => (
    <div className="flex items-center justify-between py-3">
      <div>
        <p className="font-mono text-white">{label}</p>
        {description && <p className="text-xs text-gray-500 mt-1">{description}</p>}
      </div>
      <button
        onClick={() => onChange(!checked)}
        className={`relative w-12 h-6 rounded-full transition-colors ${
          checked ? 'bg-plasma-cyan' : 'bg-gray-700'
        }`}
      >
        <span
          className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
            checked ? 'translate-x-7' : 'translate-x-1'
          }`}
        />
      </button>
    </div>
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display text-plasma-cyan">Settings</h1>
          <p className="text-gray-500 font-mono text-sm mt-1">Manage your account preferences</p>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center space-x-2 px-6 py-3 rounded-xl bg-gradient-to-r from-plasma-cyan to-plasma-purple text-void hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          <Save size={18} />
          <span className="font-mono">{saving ? 'SAVING...' : 'SAVE CHANGES'}</span>
        </button>
      </div>

      <div className="flex flex-col lg:flex-row gap-6">
        {/* Sidebar */}
        <div className="lg:w-64">
          <nav className="glass rounded-xl p-4 border border-plasma-cyan/20">
            {[
              { id: 'account', icon: User, label: 'Account' },
              { id: 'notifications', icon: Bell, label: 'Notifications' },
              { id: 'security', icon: Shield, label: 'Security' },
              { id: 'display', icon: Moon, label: 'Display' }
            ].map(({ id, icon: Icon, label }) => (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                className={`w-full flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors ${
                  activeTab === id
                    ? 'bg-plasma-cyan/20 text-plasma-cyan'
                    : 'text-gray-400 hover:text-white hover:bg-gray-800/50'
                }`}
              >
                <Icon size={18} />
                <span className="font-mono text-sm">{label}</span>
              </button>
            ))}
          </nav>
        </div>

        {/* Content */}
        <div className="flex-1">
          {activeTab === 'account' && (
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              className="glass rounded-xl p-6 border border-plasma-cyan/20"
            >
              <h3 className="font-display text-plasma-cyan mb-6 flex items-center">
                <User size={20} className="mr-2" />
                Account Settings
              </h3>
              <div className="space-y-6">
                <div>
                  <label className="block text-sm font-mono text-gray-400 mb-2">Username</label>
                  <input
                    type="text"
                    value={settings.username}
                    onChange={(e) => updateSetting('username', e.target.value)}
                    className="w-full bg-deep-space border border-gray-800 rounded-xl px-4 py-3 font-mono text-white focus:outline-none focus:border-plasma-cyan transition-colors"
                  />
                </div>
                <div>
                  <label className="block text-sm font-mono text-gray-400 mb-2">Email</label>
                  <div className="relative">
                    <Mail className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500" size={18} />
                    <input
                      type="email"
                      value={settings.email}
                      onChange={(e) => updateSetting('email', e.target.value)}
                      className="w-full bg-deep-space border border-gray-800 rounded-xl pl-12 pr-4 py-3 font-mono text-white focus:outline-none focus:border-plasma-cyan transition-colors"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-mono text-gray-400 mb-2">Timezone</label>
                  <div className="relative">
                    <Globe className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500" size={18} />
                    <select
                      value={settings.timezone}
                      onChange={(e) => updateSetting('timezone', e.target.value)}
                      className="w-full bg-deep-space border border-gray-800 rounded-xl pl-12 pr-4 py-3 font-mono text-white focus:outline-none focus:border-plasma-cyan transition-colors appearance-none"
                    >
                      <option value="UTC">UTC</option>
                      <option value="EST">Eastern Time (EST)</option>
                      <option value="PST">Pacific Time (PST)</option>
                      <option value="GMT">GMT</option>
                      <option value="CET">Central European Time (CET)</option>
                    </select>
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {activeTab === 'notifications' && (
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              className="glass rounded-xl p-6 border border-plasma-cyan/20"
            >
              <h3 className="font-display text-plasma-cyan mb-6 flex items-center">
                <Bell size={20} className="mr-2" />
                Notification Preferences
              </h3>
              <div className="divide-y divide-gray-800">
                <ToggleSwitch
                  checked={settings.emailNotifications}
                  onChange={(v) => updateSetting('emailNotifications', v)}
                  label="Email Notifications"
                  description="Receive updates via email"
                />
                <ToggleSwitch
                  checked={settings.pushNotifications}
                  onChange={(v) => updateSetting('pushNotifications', v)}
                  label="Push Notifications"
                  description="Browser push notifications"
                />
                <ToggleSwitch
                  checked={settings.tradeAlerts}
                  onChange={(v) => updateSetting('tradeAlerts', v)}
                  label="Trade Alerts"
                  description="Notifications for executed trades"
                />
                <ToggleSwitch
                  checked={settings.priceAlerts}
                  onChange={(v) => updateSetting('priceAlerts', v)}
                  label="Price Alerts"
                  description="Alert when price targets are hit"
                />
                <ToggleSwitch
                  checked={settings.weeklyReports}
                  onChange={(v) => updateSetting('weeklyReports', v)}
                  label="Weekly Reports"
                  description="Weekly performance summary"
                />
              </div>
            </motion.div>
          )}

          {activeTab === 'security' && (
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              className="glass rounded-xl p-6 border border-plasma-cyan/20"
            >
              <h3 className="font-display text-plasma-cyan mb-6 flex items-center">
                <Shield size={20} className="mr-2" />
                Security Settings
              </h3>
              <div className="space-y-6">
                <div className="p-4 rounded-xl bg-deep-space border border-gray-800">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center space-x-3">
                      <Smartphone size={24} className="text-plasma-purple" />
                      <div>
                        <p className="font-mono text-white">Two-Factor Authentication</p>
                        <p className="text-xs text-gray-500">Secure your account with 2FA</p>
                      </div>
                    </div>
                    <span className={`px-3 py-1 rounded-full text-xs font-mono ${
                      settings.twoFactorEnabled 
                        ? 'bg-neon-green/20 text-neon-green' 
                        : 'bg-neon-red/20 text-neon-red'
                    }`}>
                      {settings.twoFactorEnabled ? 'ENABLED' : 'DISABLED'}
                    </span>
                  </div>
                  <button className="w-full py-2 rounded-lg border border-plasma-purple/30 text-plasma-purple hover:bg-plasma-purple/10 transition-colors font-mono text-sm">
                    {settings.twoFactorEnabled ? 'Manage 2FA' : 'Enable 2FA'}
                  </button>
                </div>

                <div>
                  <label className="block text-sm font-mono text-gray-400 mb-2">
                    Session Timeout (minutes)
                  </label>
                  <select
                    value={settings.sessionTimeout}
                    onChange={(e) => updateSetting('sessionTimeout', parseInt(e.target.value))}
                    className="w-full bg-deep-space border border-gray-800 rounded-xl px-4 py-3 font-mono text-white focus:outline-none focus:border-plasma-cyan transition-colors appearance-none"
                  >
                    <option value={15}>15 minutes</option>
                    <option value={30}>30 minutes</option>
                    <option value={60}>1 hour</option>
                    <option value={120}>2 hours</option>
                  </select>
                </div>

                <button className="w-full py-3 rounded-xl border border-plasma-cyan/30 text-plasma-cyan hover:bg-plasma-cyan/10 transition-colors font-mono flex items-center justify-center space-x-2">
                  <Key size={18} />
                  <span>Change Password</span>
                </button>

                <button
                  onClick={logout}
                  className="w-full py-3 rounded-xl border border-neon-red/30 text-neon-red hover:bg-neon-red/10 transition-colors font-mono flex items-center justify-center space-x-2"
                >
                  <LogOut size={18} />
                  <span>Sign Out All Devices</span>
                </button>
              </div>
            </motion.div>
          )}

          {activeTab === 'display' && (
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              className="glass rounded-xl p-6 border border-plasma-cyan/20"
            >
              <h3 className="font-display text-plasma-cyan mb-6 flex items-center">
                <Moon size={20} className="mr-2" />
                Display Settings
              </h3>
              <div className="divide-y divide-gray-800">
                <ToggleSwitch
                  checked={settings.darkMode}
                  onChange={(v) => updateSetting('darkMode', v)}
                  label="Dark Mode"
                  description="Use dark theme (recommended)"
                />
                <ToggleSwitch
                  checked={settings.compactView}
                  onChange={(v) => updateSetting('compactView', v)}
                  label="Compact View"
                  description="Reduce spacing for more data"
                />
                <ToggleSwitch
                  checked={settings.showPnlPercentage}
                  onChange={(v) => updateSetting('showPnlPercentage', v)}
                  label="Show P&L Percentage"
                  description="Display percentage alongside currency"
                />
              </div>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  )
}
