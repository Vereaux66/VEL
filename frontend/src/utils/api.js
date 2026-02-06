// API utility for making authenticated requests

const API_BASE = ''

export const api = {
  async get(endpoint) {
    const token = localStorage.getItem('vel_token')
    return fetch(`${API_BASE}${endpoint}`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...(token && { Authorization: `Bearer ${token}` })
      }
    })
  },

  async post(endpoint, data) {
    const token = localStorage.getItem('vel_token')
    return fetch(`${API_BASE}${endpoint}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token && { Authorization: `Bearer ${token}` })
      },
      body: JSON.stringify(data)
    })
  },

  async put(endpoint, data) {
    const token = localStorage.getItem('vel_token')
    return fetch(`${API_BASE}${endpoint}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...(token && { Authorization: `Bearer ${token}` })
      },
      body: JSON.stringify(data)
    })
  },

  async delete(endpoint) {
    const token = localStorage.getItem('vel_token')
    return fetch(`${API_BASE}${endpoint}`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
        ...(token && { Authorization: `Bearer ${token}` })
      }
    })
  }
}

// Dashboard API
export const dashboardApi = {
  async getData() {
    const response = await api.get('/api/dashboard')
    if (!response.ok) throw new Error('Failed to fetch dashboard data')
    return response.json()
  },

  async getPerformance(timeframe = '30d') {
    const response = await api.get(`/api/performance/report?timeframe=${timeframe}`)
    if (!response.ok) throw new Error('Failed to fetch performance data')
    return response.json()
  }
}

// Trading API
export const tradingApi = {
  async startTrading(config) {
    const response = await api.post('/api/trading/start', config)
    if (!response.ok) throw new Error('Failed to start trading')
    return response.json()
  },

  async stopTrading(closePositions = false) {
    const response = await api.post('/api/trading/stop', { close_positions: closePositions })
    if (!response.ok) throw new Error('Failed to stop trading')
    return response.json()
  }
}

// AI Assistant API
export const aiApi = {
  async ask(question, context = '') {
    const response = await api.post('/api/ai/ask', { question, context })
    if (!response.ok) throw new Error('AI request failed')
    return response.json()
  },

  async toggle() {
    const response = await api.post('/api/ai/toggle')
    if (!response.ok) throw new Error('Failed to toggle AI')
    return response.json()
  }
}

// Simulation API
export const simulationApi = {
  async start() {
    const response = await api.post('/api/simulation/start')
    if (!response.ok) throw new Error('Failed to start simulation')
    return response.json()
  }
}
