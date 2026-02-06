# VEL Trading Frontend

Cyberpunk-themed frontend for the VEL Decentralized Autonomous Trading System.

## Features

- 🚀 **Blast Door Login** - Animated industrial doors that open on successful authentication
- 🌧️ **Crypto Matrix Rain** - Matrix-style falling crypto symbols background
- 📊 **Real-time Dashboard** - Live portfolio tracking with charts and metrics
- 💹 **Trading Terminal** - Strategy selection and risk configuration
- 💰 **Wallet Management** - Deposits, withdrawals, and tier benefits
- ⚙️ **Settings** - Account and notification preferences

## Tech Stack

- React 18 with Vite
- Tailwind CSS for styling
- Framer Motion for animations
- Recharts for data visualization
- Socket.io for real-time updates
- Lucide React for icons

## Getting Started

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build
```

## Theme Colors

- Plasma Cyan: `#00ffff`
- Plasma Purple: `#bf00ff`
- Neon Green: `#00ff41`
- Neon Red: `#ff073a`
- Void Black: `#000000`

## Project Structure

```
src/
├── components/     # Reusable UI components
├── context/        # React contexts (Auth, WebSocket)
├── pages/          # Page components
└── utils/          # Constants and API utilities
```

## Backend Integration

The frontend connects to the VEL backend running on port 5000 for:
- REST API endpoints (`/api/*`)
- WebSocket connections for real-time updates
- AI assistant interactions

## Environment Variables

Create a `.env` file:
```
VITE_API_URL=http://localhost:5000
VITE_WS_URL=ws://localhost:5000
```
