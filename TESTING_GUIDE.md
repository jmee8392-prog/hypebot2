# Hyperliquid Trading Bot - Testing Guide

## Overview

All components have been tested and debugged. The bot is ready for deployment with full testnet and dry-run support.

## Test Results Summary

### ✓ Unit Tests (23/23 PASSED)
- **Technical Analysis**: 6/6 tests passed
  - Candle data handling
  - RSI calculation
  - MACD calculation (fixed)
  - Bollinger Bands
  - Price structure detection
  - Trade signal generation

- **Macro Liquidity Monitor**: 6/6 tests passed
  - Fed liquidity tracking
  - Stablecoin flows
  - BTC ETF flows
  - Funding rates
  - On-chain metrics
  - Macro regime assessment

- **Risk Management**: 4/4 tests passed
  - Position sizing calculation
  - Take profit calculation
  - Trade validation

- **Geopolitical Risk**: 2/2 tests passed
  - Sentiment score calculation
  - Risk level assessment

- **Hyperliquid Executor**: 2/2 tests passed
  - Signature generation
  - Account state handling

- **Bot Orchestrator**: 3/3 tests passed
  - Bot initialization
  - Single cycle execution
  - Performance summary

### ✓ Integration Tests (4/4 PASSED)
- Dry run mode (mainnet, simulated orders)
- Testnet unified account support
- Mainnet perps support
- Order placement in dry-run mode

### ✓ Live Data Tests (4/4 PASSED)
- Uptrend signal generation
- Downtrend signal generation
- Bot real data flow with macro analysis
- Multi-symbol analysis

## Running Tests

### Quick Test (Recommended for first run)
```bash
# Run all unit tests
python3 test_bot.py

# Run integration tests
python3 integration_test.py

# Run live data tests
python3 test_with_data.py
```

### Quick Verification
```bash
# Run the bot once in dry-run mode
python3 hyperliquid_trading_bot.py
```

## Configuration

### Environment Variables (.env)

**Required:**
```
HYPERLIQUID_PRIVATE_KEY=your_private_key_here
HYPERLIQUID_ACCOUNT=your_account_address_here
```

**Optional (defaults provided):**
```
ACCOUNT_SIZE=10000                 # Account size in USD
MAX_LOSS_PER_TRADE=0.02           # 2% max loss per trade
SYMBOLS=BTC,ETH                    # Trading symbols
CYCLE_INTERVAL=60                  # Seconds between cycles

USE_TESTNET=false                  # Set to true for testnet
DRY_RUN=true                        # Set to false for live trading
```

## Modes

### Dry Run Mode (SAFE FOR TESTING)
- **Description**: Simulates orders without placing them on the exchange
- **Purpose**: Test bot logic without risking funds
- **Configuration**: `DRY_RUN=true`
- **Order Status**: All orders show as `dry_run_simulated`

### Testnet Mode
- **Description**: Trades on Hyperliquid testnet with unified account
- **Purpose**: Test with real API calls without risking funds
- **Configuration**: `USE_TESTNET=true`
- **Account Type**: Unified (not perps-only)
- **API Endpoint**: `https://testnet.hyperliquid.xyz`

### Mainnet Mode
- **Description**: Live trading on Hyperliquid mainnet
- **Purpose**: Production trading
- **Configuration**: `USE_TESTNET=false, DRY_RUN=false`
- **Account Type**: Perps
- **API Endpoint**: `https://api.hyperliquid.xyz`

## Recommended Testing Workflow

### Step 1: Verify Unit Tests Pass
```bash
python3 test_bot.py
# Expected: All 23 tests pass ✓
```

### Step 2: Run Integration Tests
```bash
python3 integration_test.py
# Expected: All 4 integration tests pass ✓
```

### Step 3: Test with Live Data
```bash
python3 test_with_data.py
# Expected: All 4 live data tests pass ✓
```

### Step 4: Dry Run on Mainnet
```bash
# Update .env:
# DRY_RUN=true
# USE_TESTNET=false

python3 hyperliquid_trading_bot.py
# Expected: Bot runs one cycle, shows configuration, no trades executed
```

### Step 5: Dry Run on Testnet
```bash
# Update .env:
# DRY_RUN=true
# USE_TESTNET=true

python3 hyperliquid_trading_bot.py
# Expected: Bot runs one cycle with testnet settings
```

### Step 6: Add Credentials (Skip if Testing)
Add your Hyperliquid credentials to `.env`:
```
HYPERLIQUID_PRIVATE_KEY=your_key
HYPERLIQUID_ACCOUNT=your_address
```

### Step 7: Live Testnet Trading (OPTIONAL)
```bash
# Update .env:
# DRY_RUN=false
# USE_TESTNET=true

python3 hyperliquid_trading_bot.py
# Trades will be executed on testnet (no real funds at risk)
```

### Step 8: Live Mainnet Trading (AFTER VERIFICATION)
```bash
# Update .env:
# DRY_RUN=false
# USE_TESTNET=false

python3 hyperliquid_trading_bot.py
# Live trading - CAUTION: Real funds at risk
```

## Debugging

### Enable Verbose Logging
Edit `hyperliquid_trading_bot.py` line 42:
```python
logging.basicConfig(
    level=logging.DEBUG,  # Changed from INFO
    ...
)
```

### Check Log File
```bash
tail -f hyperliquid_bot.log
```

### Common Issues

**Issue**: Missing environment variables
- **Solution**: Check `.env` file has all required variables
- **Command**: `echo $HYPERLIQUID_PRIVATE_KEY`

**Issue**: API connection errors
- **Solution**: Verify credentials and testnet/mainnet selection
- **Command**: Check logs for specific error messages

**Issue**: Order placement failures
- **Solution**: Verify account has sufficient margin
- **Command**: Check account state in logs

## Known Working Scenarios

✓ Unit tests pass reliably
✓ Technical analysis indicators calculate correctly
✓ Risk management validates trades properly
✓ Macro indicators assess market conditions
✓ Testnet mode uses unified account structure
✓ Dry-run mode simulates orders correctly
✓ Multi-symbol analysis works
✓ Performance tracking calculates metrics

## Fixed Issues

**MACD Calculation Bug** (FIXED)
- Issue: Creating nested array in `calculate_macd()`
- Fix: Use macd_line directly in EMA calculation
- Status: ✓ Verified fixed and tested

## Next Steps After Testing

1. ✓ Run all tests (completed)
2. ✓ Verify dry-run mode works (completed)
3. ✓ Test on testnet (ready)
4. Add real credentials when ready
5. Deploy to VPS/server
6. Monitor performance metrics
7. Adjust parameters based on live results

## Safety Features Implemented

- ✓ High-confirmation technical analysis (3+ signals required)
- ✓ Macro regime filtering (won't trade in critical risk)
- ✓ Risk/reward ratio validation
- ✓ Position sizing based on account risk
- ✓ Dry-run mode prevents live trading
- ✓ Testnet mode separates from mainnet
- ✓ Comprehensive error handling and logging
- ✓ Account state verification before trades

## Support

For issues or questions:
1. Check logs: `cat hyperliquid_bot.log | tail -100`
2. Run relevant test: `python3 test_bot.py`
3. Verify configuration in `.env`
4. Check Hyperliquid API status

---

**Status**: All tests passing, bot ready for deployment
**Last Updated**: 2026-03-26
