export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        'void': '#000000',
        'deep-space': '#0a0a0f',
        'plasma': {
          cyan: '#00ffff',
          blue: '#00bfff',
          purple: '#bf00ff',
          magenta: '#ff00bf'
        },
        'neon': {
          green: '#00ff41',
          yellow: '#ffff00',
          orange: '#ff8c00',
          red: '#ff073a'
        },
        'crypto': {
          btc: '#f7931a',
          eth: '#627eea',
          usdt: '#26a17b',
          usdc: '#2775ca',
          bnb: '#f3ba2f'
        }
      },
      fontFamily: {
        'display': ['Orbitron', 'monospace'],
        'mono': ['JetBrains Mono', 'monospace']
      },
      boxShadow: {
        'glow-cyan': '0 0 20px rgba(0,255,255,0.5)',
        'glow-purple': '0 0 20px rgba(191,0,255,0.5)',
        'glow-green': '0 0 20px rgba(0,255,65,0.5)',
        'glow-red': '0 0 20px rgba(255,7,58,0.5)'
      },
      animation: {
        'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
        'matrix-rain': 'matrix-rain 20s linear infinite',
        'door-open': 'door-open 1.5s ease-out forwards'
      },
      keyframes: {
        'pulse-glow': {
          '0%, 100%': { opacity: 1 },
          '50%': { opacity: 0.5 }
        },
        'matrix-rain': {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100vh)' }
        },
        'door-open': {
          '0%': { transform: 'translateX(0)' },
          '100%': { transform: 'translateX(-100%)' }
        }
      }
    }
  },
  plugins: []
}
