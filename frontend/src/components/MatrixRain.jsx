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
    const fontSize = 14
    const columns = Math.floor(canvas.width / (fontSize + 4)) // Add spacing between columns
    
    // Initialize drops with random starting positions for variety
    const drops = Array(columns).fill(0).map(() => Math.floor(Math.random() * -50))
    
    // Pre-assign symbols to each column for consistency (changes less frequently)
    const columnSymbols = Array(columns).fill(0).map(() => 
      CRYPTO_SYMBOLS[Math.floor(Math.random() * CRYPTO_SYMBOLS.length)]
    )
    
    // Track when to change symbols (every N frames per column)
    const symbolChangeCounters = Array(columns).fill(0)

    let lastTime = 0
    const frameInterval = 45 // Slightly faster for smoother animation
    let animationId

    // Draw function using requestAnimationFrame
    const draw = (currentTime) => {
      animationId = requestAnimationFrame(draw)
      
      // Throttle for consistent frame rate
      if (currentTime - lastTime < frameInterval) return
      lastTime = currentTime

      // Slower fade for more visible trails
      ctx.fillStyle = 'rgba(0, 0, 0, 0.03)'
      ctx.fillRect(0, 0, canvas.width, canvas.height)

      // Set consistent font
      ctx.font = `bold ${fontSize}px 'JetBrains Mono', 'Consolas', monospace`
      ctx.textAlign = 'center'

      drops.forEach((drop, i) => {
        const x = i * (fontSize + 4) + fontSize / 2
        const y = drop * fontSize
        
        // Get the symbol for this column
        let symbol = columnSymbols[i]
        
        // Occasionally change the symbol (every 15-25 drops)
        symbolChangeCounters[i]++
        if (symbolChangeCounters[i] > 15 + Math.floor(Math.random() * 10)) {
          columnSymbols[i] = CRYPTO_SYMBOLS[Math.floor(Math.random() * CRYPTO_SYMBOLS.length)]
          symbol = columnSymbols[i]
          symbolChangeCounters[i] = 0
        }
        
        // Draw the leading bright character
        ctx.fillStyle = 'rgba(255, 255, 255, 0.95)'
        ctx.fillText(symbol, x, y)
        
        // Draw trailing characters with gradient fade
        for (let j = 1; j < 20; j++) {
          const trailY = y - j * fontSize
          if (trailY > 0) {
            // Cyan gradient fade
            const alpha = Math.max(0, 0.7 - j * 0.04)
            const green = Math.floor(255 - j * 5)
            ctx.fillStyle = `rgba(0, ${green}, 255, ${alpha})`
            
            // Use same symbol for trail consistency
            ctx.fillText(symbol, x, trailY)
          }
        }

        // Reset drop to top when it goes off screen
        if (y > canvas.height + fontSize * 20) {
          drops[i] = Math.floor(Math.random() * -10)
          // Change symbol when resetting
          columnSymbols[i] = CRYPTO_SYMBOLS[Math.floor(Math.random() * CRYPTO_SYMBOLS.length)]
        }
        
        // Move drop down
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
      className="fixed inset-0 z-0 opacity-40 pointer-events-none"
    />
  )
}
