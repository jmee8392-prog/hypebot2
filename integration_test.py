"""
INTEGRATION TEST - Tests bot with testnet and dry-run mode enabled
"""

import os
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hyperliquid_trading_bot import HyperliquidTradingBot


def test_dry_run_mode():
    """Test bot in dry-run mode"""
    logger.info("\n" + "="*70)
    logger.info("INTEGRATION TEST - DRY RUN MODE")
    logger.info("="*70 + "\n")

    config = {
        'HYPERLIQUID_PRIVATE_KEY': 'test_key_123',
        'HYPERLIQUID_ACCOUNT': '0xtest123',
        'ACCOUNT_SIZE': 10000,
        'MAX_LOSS_PER_TRADE': 0.02,
        'SYMBOLS': ['BTC', 'ETH'],
        'CYCLE_INTERVAL': 1,
        'USE_TESTNET': False,
        'DRY_RUN': True,
    }

    try:
        bot = HyperliquidTradingBot(config)
        assert bot.dry_run == True, "Dry run should be enabled"
        assert bot.is_testnet == False, "Should be mainnet"

        bot._cycle()

        summary = bot.get_performance_summary()
        logger.info(f"\nDry Run Results:")
        logger.info(f"  Trades Executed: {summary.get('total_trades', 0)}")
        logger.info(f"  Avg Confidence: {summary.get('avg_confidence', 0):.2%}")

        logger.info("\n✓ DRY RUN TEST PASSED")
        return True
    except Exception as e:
        logger.error(f"\n✗ DRY RUN TEST FAILED: {e}")
        return False


def test_testnet_unified_account():
    """Test bot in testnet with unified account"""
    logger.info("\n" + "="*70)
    logger.info("INTEGRATION TEST - TESTNET UNIFIED ACCOUNT")
    logger.info("="*70 + "\n")

    config = {
        'HYPERLIQUID_PRIVATE_KEY': 'testnet_key_456',
        'HYPERLIQUID_ACCOUNT': '0xtestnet456',
        'ACCOUNT_SIZE': 5000,
        'MAX_LOSS_PER_TRADE': 0.01,
        'SYMBOLS': ['BTC'],
        'CYCLE_INTERVAL': 1,
        'USE_TESTNET': True,
        'DRY_RUN': True,
    }

    try:
        bot = HyperliquidTradingBot(config)
        assert bot.dry_run == True, "Dry run should be enabled"
        assert bot.is_testnet == True, "Should be testnet"
        assert bot.executor.account_type == "unified", "Should use unified account"

        logger.info(f"Executor Account Type: {bot.executor.account_type}")
        logger.info(f"Executor API URL: {bot.executor.base_url}")

        bot._cycle()

        logger.info("\n✓ TESTNET UNIFIED ACCOUNT TEST PASSED")
        return True
    except Exception as e:
        logger.error(f"\n✗ TESTNET UNIFIED ACCOUNT TEST FAILED: {e}")
        return False


def test_mainnet_perps():
    """Test bot in mainnet with perps (default)"""
    logger.info("\n" + "="*70)
    logger.info("INTEGRATION TEST - MAINNET PERPS")
    logger.info("="*70 + "\n")

    config = {
        'HYPERLIQUID_PRIVATE_KEY': 'mainnet_key_789',
        'HYPERLIQUID_ACCOUNT': '0xmainnet789',
        'ACCOUNT_SIZE': 50000,
        'MAX_LOSS_PER_TRADE': 0.02,
        'SYMBOLS': ['BTC', 'ETH', 'SOL'],
        'CYCLE_INTERVAL': 1,
        'USE_TESTNET': False,
        'DRY_RUN': True,
    }

    try:
        bot = HyperliquidTradingBot(config)
        assert bot.dry_run == True, "Dry run should be enabled"
        assert bot.is_testnet == False, "Should be mainnet"
        assert bot.executor.account_type == "perps", "Should use perps account"

        logger.info(f"Executor Account Type: {bot.executor.account_type}")
        logger.info(f"Number of Trading Symbols: {len(bot.trading_symbols)}")

        bot._cycle()

        logger.info("\n✓ MAINNET PERPS TEST PASSED")
        return True
    except Exception as e:
        logger.error(f"\n✗ MAINNET PERPS TEST FAILED: {e}")
        return False


def test_order_placement_dry_run():
    """Test order placement in dry-run mode"""
    logger.info("\n" + "="*70)
    logger.info("INTEGRATION TEST - ORDER PLACEMENT (DRY RUN)")
    logger.info("="*70 + "\n")

    config = {
        'HYPERLIQUID_PRIVATE_KEY': 'test_key',
        'HYPERLIQUID_ACCOUNT': '0xtest',
        'ACCOUNT_SIZE': 10000,
        'MAX_LOSS_PER_TRADE': 0.02,
        'SYMBOLS': ['BTC'],
        'CYCLE_INTERVAL': 1,
        'USE_TESTNET': False,
        'DRY_RUN': True,
    }

    try:
        bot = HyperliquidTradingBot(config)

        result = bot.executor.place_order(
            symbol='BTC',
            side='BUY',
            size=5000,
            limit_price=65000,
            leverage=2.0
        )

        assert result is not None, "Order result should not be None"
        assert result['status'] == 'dry_run_simulated', "Should indicate dry run"
        assert result['symbol'] == 'BTC', "Symbol should match"

        logger.info(f"Dry Run Order Result: {result}")
        logger.info("\n✓ ORDER PLACEMENT (DRY RUN) TEST PASSED")
        return True
    except Exception as e:
        logger.error(f"\n✗ ORDER PLACEMENT (DRY RUN) TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_integration_tests():
    """Run all integration tests"""
    logger.info("\n" + "="*70)
    logger.info("HYPERLIQUID BOT - INTEGRATION TEST SUITE")
    logger.info("="*70)

    tests = [
        ("Dry Run Mode", test_dry_run_mode),
        ("Testnet Unified Account", test_testnet_unified_account),
        ("Mainnet Perps", test_mainnet_perps),
        ("Order Placement (Dry Run)", test_order_placement_dry_run),
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
            logger.error(f"Test {test_name} crashed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    logger.info("\n" + "="*70)
    logger.info("INTEGRATION TEST RESULTS")
    logger.info("="*70)
    logger.info(f"Passed: {passed}")
    logger.info(f"Failed: {failed}")

    if failed == 0:
        logger.info("\n✓ ALL INTEGRATION TESTS PASSED")
    else:
        logger.info(f"\n✗ {failed} INTEGRATION TESTS FAILED")

    logger.info("="*70 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = run_all_integration_tests()
    sys.exit(0 if success else 1)
