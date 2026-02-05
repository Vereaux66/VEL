#!/usr/bin/env node
/**
 * ANVEL Trading System — Server Entry Point
 * ==========================================
 * Delegates to webapp/anvel_server.js.
 * This file exists so that `npm start` (which runs `node server.js`)
 * works from the repository root.
 */

require("./webapp/anvel_server.js");
