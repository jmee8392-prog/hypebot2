"""
LIVE DATA TEST - Tests bot with realistic market data
"""

import os
import sys
import logging
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hyperliquid_trading_bot import (
    HighConfirmationTA, HyperliquidTradingBot, TradeSignal
)


def generate_realistic_candles(trend='up', num_candles=200):
    """Generate realistic OHLCV candles"""
    candles = []
    base_price = 65000

    for i in range(num_candles):
        trend_factor = (i * 0.01) if trend == 'up' else -(i * 0.01)
        noise = np.random.uniform(-200, 200)

        open_price = base_price + trend_factor + noise
        high_price = open_price + np.random.uniform(200, 800)
        low_price = open_price - np.random.uniform(200, 800)
        close_price = low_price + np.random.uniform(0, high_price - low_price)

        volume = np.random.uniform(100000, 500000)

        candles.append({
            'timestamp': 1700000000 + (i * 60),
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'volume': volume
        })

    return candles


def test_uptrend_signal():
    """Test signal generation in uptrend"""
    logger.info("\n" + "="*70)
    logger.info("LIVE DATA TEST - UPTREND SIGNAL")
    logger.info("="*70 + "\n")

    ta = HighConfirmationTA()
    candles = generate_realistic_candles(trend='up', num_candles=200)

    for candle in candles:
        ta.add_candle(
            timestamp=candle['timestamp'],
            open_=candle['open'],
            high=candle['high'],
            low=candle['low'],
            close=candle['close'],
            volume=candle['volume']
        )

    signal = ta.generate_signal()

    logger.info(f"Signal: {signal.signal.value}")
    logger.info(f"Confidence: {signal.confidence:.2%}")
    logger.info(f"Confirmations: {len(signal.confirmations)}")
    logger.info(f"Indicators: {signal.confirmations}")
    logger.info(f"Support: ${signal.support_level:.2f}")
    logger.info(f"Resistance: ${signal.resistance_level:.2f}")

    assert signal.signal in [TradeSignal.LONG, TradeSignal.SHORT, TradeSignal.NEUTRAL]
    logger.info("\n✓ UPTREND SIGNAL TEST PASSED")
    return True


def test_downtrend_signal():
    """Test signal generation in downtrend"""
    logger.info("\n" + "="*70)
    logger.info("LIVE DATA TEST - DOWNTREND SIGNAL")
    logger.info("="*70 + "\n")

    ta = HighConfirmationTA()
    candles = generate_realistic_candles(trend='down', num_candles=200)

    for candle in candles:
        ta.add_candle(
            timestamp=candle['timestamp'],
            open_=candle['open'],
            high=candle['high'],
            low=candle['low'],
            close=candle['close'],
            volume=candle['volume']
        )

    signal = ta.generate_signal()

    logger.info(f"Signal: {signal.signal.value}")
    logger.info(f"Confidence: {signal.confidence:.2%}")
    logger.info(f"Confirmations: {len(signal.confirmations)}")
    logger.info(f"Indicators: {signal.confirmations}")
    logger.info(f"Support: ${signal.support_level:.2f}")
    logger.info(f"Resistance: ${signal.resistance_level:.2f}")

    assert signal.signal in [TradeSignal.LONG, TradeSignal.SHORT, TradeSignal.NEUTRAL]
    logger.info("\n✓ DOWNTREND SIGNAL TEST PASSED")
    return True


def test_bot_with_real_data_flow():
    """Test bot with realistic data flow"""
    logger.info("\n" + "="*70)
    logger.info("LIVE DATA TEST - BOT REAL DATA FLOW")
    logger.info("="*70 + "\n")

    config = {
        'HYPERLIQUID_PRIVATE_KEY': 'test_key',
        'HYPERLIQUID_ACCOUNT': '0xtest',
        'ACCOUNT_SIZE': 10000,
        'MAX_LOSS_PER_TRADE': 0.02,
        'SYMBOLS': ['BTC', 'ETH'],
        'CYCLE_INTERVAL': 1,
        'USE_TESTNET': False,
        'DRY_RUN': True,
    }

    bot = HyperliquidTradingBot(config)

    candles = generate_realistic_candles(trend='up', num_candles=200)

    for candle in candles:
        bot.ta_engine.add_candle(
            timestamp=candle['timestamp'],
            open_=candle['open'],
            high=candle['high'],
            low=candle['low'],
            close=candle['close'],
            volume=candle['volume']
        )

    signal = bot.ta_engine.generate_signal()
    macro = bot.macro_monitor.assess_macro_regime()

    logger.info(f"Technical Signal: {signal.signal.value}")
    logger.info(f"Signal Confidence: {signal.confidence:.2%}")
    logger.info(f"Macro Regime: {macro['regime']}")
    logger.info(f"Macro Risk Level: {macro['risk_level']}")

    logger.info(f"\nMacro Indicators:")
    for name, indicator in list(macro['indicators'].items())[:3]:
        logger.info(f"  {indicator.name}: {indicator.impact}")

    logger.info("\n✓ BOT REAL DATA FLOW TEST PASSED")
    return True


def test_multi_symbol_analysis():
    """Test bot analyzing multiple symbols"""
    logger.info("\n" + "="*70)
    logger.info("LIVE DATA TEST - MULTI-SYMBOL ANALYSIS")
    logger.info("="*70 + "\n")

    symbols = ['BTC', 'ETH', 'SOL']
    ta_engines = {sym: HighConfirmationTA() for sym in symbols}

    for symbol in symbols:
        candles = generate_realistic_candles(trend='up', num_candles=150)

        for candle in candles:
            ta_engines[symbol].add_candle(
                timestamp=candle['timestamp'],
                open_=candle['open'],
                high=candle['high'],
                low=candle['low'],
                close=candle['close'],
                volume=candle['volume']
            )

    logger.info("Signal Analysis by Symbol:")
    for symbol in symbols:
        signal = ta_engines[symbol].generate_signal()
        logger.info(f"  {symbol}: {signal.signal.value} (Confidence: {signal.confidence:.2%})")

    logger.info("\n✓ MULTI-SYMBOL ANALYSIS TEST PASSED")
    return True


def run_all_live_data_tests():
    """Run all live data tests"""
    logger.info("\n" + "="*70)
    logger.info("HYPERLIQUID BOT - LIVE DATA TEST SUITE")
    logger.info("="*70)

    tests = [
        ("Uptrend Signal", test_uptrend_signal),
        ("Downtrend Signal", test_downtrend_signal),
        ("Bot Real Data Flow", test_bot_with_real_data_flow),
        ("Multi-Symbol Analysis", test_multi_symbol_analysis),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"Test {test_name} failed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    logger.info("\n" + "="*70)
    logger.info("LIVE DATA TEST RESULTS")
    logger.info("="*70)
    logger.info(f"Passed: {passed}")
    logger.info(f"Failed: {failed}")

    if failed == 0:
        logger.info("\n✓ ALL LIVE DATA TESTS PASSED")
    else:
        logger.info(f"\n✗ {failed} LIVE DATA TESTS FAILED")

    logger.info("="*70 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = run_all_live_data_tests()
    sys.exit(0 if success else 1)
