#!/usr/bin/env node
/**
 * VEL Trading System — Server Entry Point
 * ========================================
 * Starts the VEL backend services.
 * For production AWS deployment, use the Python Flask backend directly.
 * This entry point spawns the Python web server process.
 */

const { spawn } = require('child_process');
const path = require('path');

console.log('[VEL] Starting VEL Trading Platform backend');

const pythonProcess = spawn('python3', [
  path.join(__dirname, 'anvel_web_server.py')
], {
  env: { ...process.env },
  stdio: 'inherit'
});

pythonProcess.on('error', (err) => {
  console.error('[VEL] Failed to start backend:', err.message);
  process.exit(1);
});

pythonProcess.on('close', (code) => {
  console.log(`[VEL] Backend process exited with code ${code}`);
  process.exit(code);
});

process.on('SIGTERM', () => {
  console.log('[VEL] Received SIGTERM, shutting down...');
  pythonProcess.kill('SIGTERM');
});

process.on('SIGINT', () => {
  console.log('[VEL] Received SIGINT, shutting down...');
  pythonProcess.kill('SIGINT');
});
