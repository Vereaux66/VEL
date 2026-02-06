import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { io } from 'socket.io-client'
import { useAuth } from './AuthContext'

const WebSocketContext = createContext(null)

export function WebSocketProvider({ children }) {
  const { token, isAuthenticated } = useAuth()
  const [socket, setSocket] = useState(null)
  const [connected, setConnected] = useState(false)
  const [portfolioData, setPortfolioData] = useState(null)
  const [tradingStatus, setTradingStatus] = useState({ status: 'inactive' })
  const [realtimePrices, setRealtimePrices] = useState({})
  const [notifications, setNotifications] = useState([])

  useEffect(() => {
    if (isAuthenticated && token) {
      // Connect to WebSocket server
      const newSocket = io(window.location.origin, {
        auth: { token },
        transports: ['websocket'],
        reconnection: true,
        reconnectionAttempts: 5,
        reconnectionDelay: 1000
      })

      newSocket.on('connect', () => {
        console.log('WebSocket connected')
        setConnected(true)
      })

      newSocket.on('disconnect', () => {
        console.log('WebSocket disconnected')
        setConnected(false)
      })

      newSocket.on('connected', (data) => {
        console.log('Server confirmed connection:', data)
      })

      // Real-time portfolio updates
      newSocket.on('portfolio_update', (data) => {
        setPortfolioData(data.data)
      })

      // Trading status updates
      newSocket.on('trading_status', (data) => {
        setTradingStatus(data)
      })

      // Real-time price updates
      newSocket.on('price_update', (data) => {
        setRealtimePrices(prev => ({
          ...prev,
          [data.symbol]: data.price
        }))
      })

      // Trade notifications
      newSocket.on('trade_executed', (data) => {
        setNotifications(prev => [
          {
            id: Date.now(),
            type: 'trade',
            message: `${data.side} ${data.quantity} ${data.pair} @ ${data.price}`,
            timestamp: new Date()
          },
          ...prev.slice(0, 49) // Keep last 50
        ])
      })

      // Alert notifications
      newSocket.on('alert', (data) => {
        setNotifications(prev => [
          {
            id: Date.now(),
            type: data.severity || 'info',
            message: data.message,
            timestamp: new Date()
          },
          ...prev.slice(0, 49)
        ])
      })

      setSocket(newSocket)

      return () => {
        newSocket.disconnect()
      }
    }
  }, [isAuthenticated, token])

  const subscribeToPairs = useCallback((pairs) => {
    if (socket && connected) {
      socket.emit('subscribe_trades', { pairs })
    }
  }, [socket, connected])

  const clearNotifications = useCallback(() => {
    setNotifications([])
  }, [])

  const value = {
    socket,
    connected,
    portfolioData,
    tradingStatus,
    realtimePrices,
    notifications,
    subscribeToPairs,
    clearNotifications
  }

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  )
}

export function useWebSocket() {
  const context = useContext(WebSocketContext)
  if (!context) {
    throw new Error('useWebSocket must be used within WebSocketProvider')
  }
  return context
}
