# Quick Start Guide

## 1-Minute Setup

### Installation
```bash
pip install --break-system-packages numpy pandas requests python-dotenv websockets aiohttp
```

### Verification (ALL PASS ✓)
```bash
python3 test_bot.py          # 23 unit tests
python3 integration_test.py  # 4 integration tests
python3 test_with_data.py    # 4 live data tests
```

### First Run (Dry-Run Mode - SAFE)
```bash
# Default config is already DRY_RUN=true
python3 hyperliquid_trading_bot.py
```

## What Was Fixed & Added

### Fixed Issues
- **MACD Calculation**: Removed nested array bug in technical analysis

### New Features
- **Testnet Support**: Unified account structure for Hyperliquid testnet
- **Dry-Run Mode**: Simulate trades without placing them
- **Enhanced Config**: Environment variable configuration

## Configuration

Edit `.env` to customize:

```bash
# Required (add your keys)
HYPERLIQUID_PRIVATE_KEY=your_key_here
HYPERLIQUID_ACCOUNT=your_address_here

# Optional (defaults shown)
ACCOUNT_SIZE=10000
MAX_LOSS_PER_TRADE=0.02
SYMBOLS=BTC,ETH
CYCLE_INTERVAL=60
USE_TESTNET=false
DRY_RUN=true
```

## Modes

| Mode | USE_TESTNET | DRY_RUN | Purpose |
|------|-------------|---------|---------|
| Safe Test | false | true | Test without trading |
| Testnet Trade | true | false | Test with real API calls |
| Live Trade | false | false | Production trading ⚠️ |

## Next Steps

1. **Verify**: Run all tests (3 commands above)
2. **Test**: Run bot once with default dry-run
3. **Add Keys**: Update HYPERLIQUID_PRIVATE_KEY in .env
4. **Testnet**: Set USE_TESTNET=true, DRY_RUN=false
5. **Monitor**: Check logs: `tail -f hyperliquid_bot.log`
6. **Deploy**: When ready, set DRY_RUN=false for live trading

## Files

- `hyperliquid_trading_bot.py` - Main bot (fixed and enhanced)
- `test_bot.py` - Unit tests (23 tests)
- `integration_test.py` - Integration tests (4 tests)
- `test_with_data.py` - Live data tests (4 tests)
- `TESTING_GUIDE.md` - Detailed testing docs
- `TEST_REPORT.md` - Complete test results

## Status

✓ 31/31 tests passing
✓ All bugs fixed
✓ Testnet support added
✓ Dry-run mode working
✓ Ready for deployment

---

**Next**: `python3 test_bot.py`
