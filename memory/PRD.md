# Hyperliquid Trading Bot - PRD

## Original Problem Statement
User has a Hyperliquid trading bot. Requested:
1. Test it live, make sure it's running smooth
2. Simulate 1,000 trades on current logic and report where it fails
3. Explain how to deploy with pm2 on a VPS already running a Polymarket bot
4. Update README to be 100% up to date and easy to run on a VPS

## Architecture
- **Language:** Python 3.9+
- **Core:** Single-file trading bot (`hyperliquid_trading_bot.py`)
- **Modules:** TA Engine, Macro Monitor, Geo Risk, Risk Manager, Executor, Bot Orchestrator
- **Deployment:** pm2 with `ecosystem.config.js`
- **Tests:** 31 tests (23 unit + 4 integration + 4 live data)

## What's Been Implemented (Jan 2026)
- [x] Ran all 31 existing tests - all passing
- [x] Built 1,000 trade simulator (`simulate_1000_trades.py`)
- [x] Identified 12 bugs (5 critical, 6 high, 2 medium)
- [x] Created pm2 deployment config (`ecosystem.config.js`)
- [x] Created proper `.env.example`
- [x] Created proper `requirements.txt` (old file had spaces in filename)
- [x] Fixed test file paths (were pointing to `/tmp/cc-agent/...`)
- [x] Updated `.gitignore`
- [x] Rewrote README.md with accurate status, simulation results, pm2 guide
- [x] Integrated hyperliquid-python-sdk (EIP-712 signing, real candle fetching)
- [x] Fixed all 5 critical bugs (price feed, SDK auth, entry price, SHORT TP, POST for account state)
- [x] Fixed high bugs (structure detection, funding rate logic, close_position)
- [x] Added per-symbol TA engines
- [x] Added unified account spot+perps balance detection for testnet
- [x] Confirmed live testnet connection - sees $996.53 USDC in spot

## Simulation Results

### v1 (Original system - confirmation counting + absolute S/R stops)
- 2,061 trades, 0.3% win rate, 95% timeouts, +$2.10 PnL
- Trades almost never resolved - SL/TP too wide

### v2 (Upgraded - weighted scoring + ATR stops + EMA trend filter)
- 5,409 trades, 34.9% win rate, 1.3% timeouts, -$6.10 PnL (-0.61%)
- Profit factor: 0.90 (close to breakeven)
- Max drawdown: 0.81%
- Trades actually resolve now. Win rate needs ~37.5% to break even at current R:R.
- Strong trend signals (EMA spread > 0.3%) had 71% win rate

## Prioritized Backlog

### P0 - Critical (Bot Cannot Trade Without These)
1. Integrate live price data feed (Hyperliquid REST API for candles)
2. Replace HMAC signing with EIP-712 (use `hyperliquid-python-sdk`)
3. Fix hardcoded `entry_price = 100.0` in `_execute_trade_signal()`
4. Fix `calculate_take_profit()` for SHORT direction
5. Fix `get_account_state()` to use POST instead of GET

### P1 - High (Logic Errors Affecting Trade Quality)
6. Lower confirmation threshold from 3 to 2 for high-confidence signals
7. Fix `higher_low` structure detection (uses `max()` instead of `min()`)
8. Fix funding rate logic inversion
9. Implement `close_position()` 
10. Uncomment and wire up SL/TP order placement
11. Replace placeholder macro data with real sources (CoinGecko funding rates at minimum)

### P2 - Medium (Nice to Have)
12. Implement divergence detection or remove dead code
13. Add WebSocket integration for real-time data
14. Add Telegram/Discord alerts for trade notifications
15. Add trade history persistence (SQLite or MongoDB)
16. Add backtesting mode with historical data

## Next Tasks
1. User to provide testnet API keys as secrets
2. Fix P0 critical bugs (price feed, SDK, entry price, TP direction)
3. Re-run 1,000 trade simulation to validate fixes
4. Test on Hyperliquid testnet with real API calls
5. Deploy to VPS with pm2
