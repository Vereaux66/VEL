import { useEffect, useRef } from 'react'
import { CRYPTO_SYMBOLS } from '../utils/constants'

export default function MatrixRain() {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')

    // Set canvas size
    const resizeCanvas = () => {
      canvas.width = window.innerWidth
      canvas.height = window.innerHeight
    }
    resizeCanvas()
    window.addEventListener('resize', resizeCanvas)

    // Matrix rain configuration
    const fontSize = 16
    const columns = Math.floor(canvas.width / fontSize)
    const drops = Array(columns).fill(1)

    let lastTime = 0
    const frameInterval = 50 // ~20fps for matrix effect
    let animationId

    // Draw function using requestAnimationFrame
    const draw = (currentTime) => {
      animationId = requestAnimationFrame(draw)
      
      // Throttle to ~20fps for authentic matrix look
      if (currentTime - lastTime < frameInterval) return
      lastTime = currentTime

      // Fade effect
      ctx.fillStyle = 'rgba(0, 0, 0, 0.05)'
      ctx.fillRect(0, 0, canvas.width, canvas.height)

      // Cyan text
      ctx.fillStyle = '#00ffff'
      ctx.font = `${fontSize}px JetBrains Mono`

      drops.forEach((drop, i) => {
        // Random crypto symbol
        const symbol = CRYPTO_SYMBOLS[Math.floor(Math.random() * CRYPTO_SYMBOLS.length)]
        
        // Draw symbol
        const x = i * fontSize
        const y = drop * fontSize
        
        // Varying opacity based on position
        const opacity = Math.random() * 0.5 + 0.2
        ctx.fillStyle = `rgba(0, 255, 255, ${opacity})`
        ctx.fillText(symbol, x, y)

        // Reset drop to top or move down
        if (y > canvas.height && Math.random() > 0.975) {
          drops[i] = 0
        }
        drops[i]++
      })
    }

    // Start animation
    animationId = requestAnimationFrame(draw)

    return () => {
      cancelAnimationFrame(animationId)
      window.removeEventListener('resize', resizeCanvas)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 z-0 opacity-30"
    />
  )
}
