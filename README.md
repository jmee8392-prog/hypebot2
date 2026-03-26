# Hyperliquid High-Confirmation Trading Bot

Automated trading system for Hyperliquid perpetuals. Combines multi-timeframe technical analysis with macro liquidity monitoring.

---

## Current Status

**Version:** 1.1.0  
**Last Updated:** January 2026  
**Tests:** 31/31 passing (unit + integration + live data)  
**Testnet:** Connected and running live on Hyperliquid testnet

### What Works

- Multi-confirmation TA engine (RSI, MACD, Bollinger Bands, structure breaks, order flow)
- **Live price data from Hyperliquid API** (real OHLCV candles per symbol)
- **Real Hyperliquid SDK integration** (EIP-712 signing via `hyperliquid-python-sdk`)
- **Proper testnet support** (unified account, correct API endpoints)
- **Per-symbol TA engines** (independent analysis for BTC, ETH, etc.)
- Macro liquidity monitor framework (Fed balance, stablecoin flows, ETF flows, funding rates)
- Geopolitical risk filter
- Risk management (position sizing, SL/TP validation, R:R enforcement)
- **Correct SHORT take-profit direction** (TP below entry for shorts)
- **Real account state via POST** (balances, positions, margin)
- **Position close implementation** (enumerates and closes positions by symbol)
- Dry-run mode (simulates orders without placing them)
- pm2 deployment config for VPS

### What Needs Work

- Macro indicators still use mostly placeholder values (except funding rates)
- Signal generation is conservative (98.7% neutral in simulation - by design, needs live tuning)
- Testnet account needs funding to actually place orders
- Divergence detection not yet implemented

---

## Quick Start

### Prerequisites

- Python 3.9+
- pip

### 1. Clone & Install

```bash
git clone <your-repo-url> hyperliquid-bot
cd hyperliquid-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
nano .env
```

Fill in your credentials:

```
HYPERLIQUID_PRIVATE_KEY=your_private_key_here
HYPERLIQUID_ACCOUNT=your_wallet_address_here
ACCOUNT_SIZE=10000
MAX_LOSS_PER_TRADE=0.02
SYMBOLS=BTC,ETH
CYCLE_INTERVAL=60
USE_TESTNET=true
DRY_RUN=true
```

### 3. Run Tests

```bash
python3 test_bot.py           # 23 unit tests
python3 integration_test.py   # 4 integration tests
python3 test_with_data.py     # 4 live data tests
```

### 4. Run Bot (Dry-Run Mode)

```bash
python3 hyperliquid_trading_bot.py
```

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HYPERLIQUID_PRIVATE_KEY` | *required* | Your Hyperliquid wallet private key |
| `HYPERLIQUID_ACCOUNT` | *required* | Your wallet address |
| `ACCOUNT_SIZE` | `10000` | Account size in USD for position sizing |
| `MAX_LOSS_PER_TRADE` | `0.02` | Max risk per trade (2%) |
| `SYMBOLS` | `BTC,ETH` | Comma-separated trading pairs |
| `CYCLE_INTERVAL` | `60` | Seconds between bot cycles |
| `USE_TESTNET` | `true` | Use Hyperliquid testnet |
| `DRY_RUN` | `true` | Simulate trades without placing orders |

### Modes

| Mode | USE_TESTNET | DRY_RUN | Purpose |
|------|:-----------:|:-------:|---------|
| Safe Test | any | `true` | Test logic without trading |
| Testnet | `true` | `false` | Test with real API calls, no real funds |
| Live | `false` | `false` | Production trading (real money) |

---

## Deploy with pm2 on Your VPS

Your VPS is already running a Polymarket bot. Here's how to add this bot alongside it without conflicts.

### 1. SSH into your VPS

```bash
ssh root@your-vps-ip
```

### 2. Create bot directory (separate from your Polymarket bot)

```bash
mkdir -p /home/hyperliquid-bot/logs
cd /home/hyperliquid-bot
```

### 3. Upload bot files

**Option A: SCP from your local machine** (run from your laptop, not the VPS)

```bash
scp -r ./* root@your-vps-ip:/home/hyperliquid-bot/
```

**Option B: Git clone**

```bash
cd /home/hyperliquid-bot
git clone <your-repo-url> .
```

### 4. Set up Python environment

```bash
cd /home/hyperliquid-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 5. Create your .env file

```bash
cp .env.example .env
nano .env
# Fill in your REAL credentials
# Set USE_TESTNET=true and DRY_RUN=true for first run
```

**Important:** `.env` is in `.gitignore` - your keys stay on the VPS, never in GitHub.

### 6. Verify bot runs

```bash
source venv/bin/activate
python3 hyperliquid_trading_bot.py
# Should show config output and complete one cycle without errors
# Press Ctrl+C to stop
```

### 7. Install pm2 (skip if already installed for Polymarket bot)

```bash
# Check if pm2 is already installed
pm2 --version

# If not installed:
npm install -g pm2
```

### 8. Start the bot with pm2

```bash
cd /home/hyperliquid-bot
pm2 start ecosystem.config.js
```

### 9. Verify both bots are running

```bash
pm2 list
```

You should see something like:

```
┌─────┬──────────────────────┬──────┬────────┬───────────┐
│ id  │ name                 │ mode │ status │ cpu       │
├─────┼──────────────────────┼──────┼────────┼───────────┤
│ 0   │ polymarket-bot       │ fork │ online │ 0.1%      │
│ 1   │ hyperliquid-bot      │ fork │ online │ 0.2%      │
└─────┴──────────────────────┴──────┴────────┴───────────┘
```

### 10. Set pm2 to auto-start on reboot

```bash
pm2 save
pm2 startup
# Follow the command it prints (copy-paste and run it)
```

### pm2 Commands Cheat Sheet

```bash
# View all running processes
pm2 list

# View hyperliquid bot logs (live)
pm2 logs hyperliquid-bot

# View last 100 lines of logs
pm2 logs hyperliquid-bot --lines 100

# Restart the bot (after code changes)
pm2 restart hyperliquid-bot

# Stop the bot
pm2 stop hyperliquid-bot

# Delete from pm2
pm2 delete hyperliquid-bot

# Monitor CPU/memory
pm2 monit

# View detailed info
pm2 describe hyperliquid-bot
```

### Updating the Bot

```bash
cd /home/hyperliquid-bot
git pull                       # or scp new files
source venv/bin/activate
pip install -r requirements.txt  # if deps changed
pm2 restart hyperliquid-bot
```

---

## 1,000 Trade Simulation Results

We ran the bot's TA logic through 1,000 simulated market scenarios (trending up, trending down, sideways, volatile spikes, flash crashes, whipsaws, low volume, gradual reversals) using realistic synthetic price data.

### Signal Generation

| Metric | Count | % |
|--------|------:|--:|
| Total Simulations | 1,000 | 100% |
| Neutral/Wait (no trade) | 987 | 98.7% |
| Trades Executed | 13 | 1.3% |

**The bot is extremely conservative.** 98.7% of market scenarios produced a NEUTRAL signal because the 3-confirmation minimum combined with requiring `signal_strength >= 2` is nearly impossible to satisfy when indicators naturally conflict.

### Trade Outcomes (of 13 executed)

| Outcome | Count | % |
|---------|------:|--:|
| Wins | 2 | 15.4% |
| Losses | 5 | 38.5% |
| Timeouts | 6 | 46.2% |

**Win Rate: 15.4%** - This is below the 60-70% target stated in the README.

### Known Issues

#### Fixed in v1.1.0

1. ~~No live price data feed~~ - Now fetches real OHLCV candles from Hyperliquid API
2. ~~Wrong API signature scheme~~ - Now uses `hyperliquid-python-sdk` with EIP-712 signing
3. ~~Hardcoded entry price~~ - Now uses current market price from live candle data
4. ~~Take profit wrong for shorts~~ - `calculate_take_profit()` now accepts `side` parameter
5. ~~`get_account_state()` uses GET~~ - Now uses POST with proper JSON body
6. ~~`close_position()` empty stub~~ - Now enumerates and closes positions
7. ~~Structure detection bug~~ - `higher_low` now correctly uses `min()` comparison
8. ~~Funding rate logic inverted~~ - Now correctly maps positive funding to BEARISH

#### Remaining

9. **Most macro data is placeholder** - Fed liquidity, stablecoin flows, ETF flows still return static values. Funding rates now attempt live fetch.

10. **Conservative signal generation** - 98.7% of simulated scenarios produce NEUTRAL. This is by design (high-confirmation only) but may need tuning for your trading style. Lower `MIN_CONFIRMATIONS` or add more indicators if you want more signals.

11. **Divergence detection is dead code** - `detect_divergence()` always returns False and is never called.

12. **No WebSocket integration** - Uses REST polling at cycle interval. Consider adding WebSocket for lower latency.

---

## File Structure

```
hyperliquid-bot/
├── hyperliquid_trading_bot.py   # Main bot code (v1.1 - SDK integrated)
├── ecosystem.config.js          # pm2 deployment config
├── requirements.txt             # Python dependencies (includes hyperliquid SDK)
├── .env.example                 # Config template (copy to .env)
├── .gitignore                   # Keeps .env and logs out of git
├── test_bot.py                  # 23 unit tests
├── integration_test.py          # 4 integration tests
├── test_with_data.py            # 4 live data tests
├── simulate_1000_trades.py      # 1,000 trade stress test
├── simulation_results.json      # Latest simulation output
├── README.md                    # This file
├── QUICKSTART.md                # Quick setup guide
├── TESTING_GUIDE.md             # Detailed testing docs
├── TEST_REPORT.md               # Test results from initial build
├── DEPLOYMENT_READY.txt         # Initial deployment checklist
├── Bot config guide.md          # Deep dive into trading logic
├── Macro dashboard.md           # Daily macro monitoring
├── Vps setup readme.md          # VPS setup (screen/systemd)
└── Quick reference.md           # Command cheat sheet
```

---

## Architecture

```
┌─────────────────────────────────────────────┐
│              Main Bot Loop                   │
│         (HyperliquidTradingBot)              │
│                                              │
│  1. Macro Assessment                         │
│     └─ Fed, Stablecoins, ETFs, Funding       │
│                                              │
│  2. Technical Analysis (per symbol)          │
│     └─ RSI, MACD, BB, Structure, Order Flow  │
│                                              │
│  3. Signal Generation                        │
│     └─ 3+ confirmations required             │
│     └─ Confidence >= 65%                     │
│                                              │
│  4. Risk Validation                          │
│     └─ R:R >= 1.5:1                          │
│     └─ Position sizing (2% max risk)         │
│                                              │
│  5. Order Execution                          │
│     └─ Hyperliquid API (dry-run / testnet)   │
│                                              │
│  6. Logging & Performance Tracking           │
└─────────────────────────────────────────────┘
```

---

## Running the Simulation Yourself

```bash
source venv/bin/activate
python3 simulate_1000_trades.py
```

This generates `simulation_results.json` with detailed metrics.

---

## Monitoring

```bash
# pm2 logs (if deployed)
pm2 logs hyperliquid-bot --lines 50

# Direct log file
tail -f hyperliquid_bot.log

# Check for errors
grep ERROR hyperliquid_bot.log | tail -20
```

---

## Disclaimer

- Futures trading carries extreme risk. You can lose your entire account.
- This is not financial advice.
- The bot has known issues (see above) and is NOT production-ready for live trading.
- Always test on testnet first with DRY_RUN=true.
- Never trade with money you can't afford to lose.
