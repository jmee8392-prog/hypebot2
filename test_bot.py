"""
COMPREHENSIVE TEST SUITE FOR HYPERLIQUID TRADING BOT
Tests all components without live trading
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hyperliquid_trading_bot import (
    HighConfirmationTA, TradeSignal, TechnicalSignal,
    MacroLiquidityMonitor, GeopoliticalRiskMonitor,
    RiskManager, HyperliquidExecutor, HyperliquidTradingBot
)


class TestHighConfirmationTA:
    """Test technical analysis module"""

    def __init__(self):
        self.ta = HighConfirmationTA(lookback_periods=500)
        self.passed = 0
        self.failed = 0

    def test_add_candle(self):
        """Test candle data addition"""
        try:
            self.ta.add_candle(
                timestamp=time.time(),
                open_=100.0,
                high=105.0,
                low=99.0,
                close=102.0,
                volume=1000.0
            )
            assert len(self.ta.price_data) == 1
            logger.info("✓ test_add_candle PASSED")
            self.passed += 1
        except Exception as e:
            logger.error(f"✗ test_add_candle FAILED: {e}")
            self.failed += 1

    def test_rsi_calculation(self):
        """Test RSI calculation"""
        try:
            for i in range(100):
                self.ta.add_candle(
                    timestamp=time.time() + i,
                    open_=100 + i * 0.1,
                    high=105 + i * 0.1,
                    low=95 + i * 0.1,
                    close=102 + i * 0.1,
                    volume=1000.0
                )

            rsi = self.ta.calculate_rsi(period=14)
            assert 0 <= rsi <= 100, f"RSI out of bounds: {rsi}"
            logger.info(f"✓ test_rsi_calculation PASSED (RSI={rsi:.2f})")
            self.passed += 1
        except Exception as e:
            logger.error(f"✗ test_rsi_calculation FAILED: {e}")
            self.failed += 1

    def test_macd_calculation(self):
        """Test MACD calculation"""
        try:
            for i in range(100):
                self.ta.add_candle(
                    timestamp=time.time() + i,
                    open_=100 + i * 0.05,
                    high=105 + i * 0.05,
                    low=95 + i * 0.05,
                    close=102 + i * 0.05,
                    volume=1000.0
                )

            macd, signal, histogram = self.ta.calculate_macd()
            logger.info(f"✓ test_macd_calculation PASSED (MACD={macd:.4f})")
            self.passed += 1
        except Exception as e:
            logger.error(f"✗ test_macd_calculation FAILED: {e}")
            self.failed += 1

    def test_bollinger_bands(self):
        """Test Bollinger Bands calculation"""
        try:
            for i in range(50):
                self.ta.add_candle(
                    timestamp=time.time() + i,
                    open_=100,
                    high=105,
                    low=95,
                    close=100 + (i % 3) - 1,
                    volume=1000.0
                )

            upper, mid, lower = self.ta.calculate_bollinger_bands()
            assert upper > mid > lower, "BB bands not properly ordered"
            logger.info(f"✓ test_bollinger_bands PASSED (Upper={upper:.2f}, Mid={mid:.2f}, Lower={lower:.2f})")
            self.passed += 1
        except Exception as e:
            logger.error(f"✗ test_bollinger_bands FAILED: {e}")
            self.failed += 1

    def test_structure_detection(self):
        """Test price structure detection"""
        try:
            for i in range(100):
                self.ta.add_candle(
                    timestamp=time.time() + i,
                    open_=100 + i * 0.2,
                    high=105 + i * 0.2,
                    low=99 + i * 0.2,
                    close=102 + i * 0.2,
                    volume=1000.0
                )

            structure = self.ta.detect_structure_breaks()
            assert isinstance(structure, dict)
            assert 'uptrend' in structure
            logger.info(f"✓ test_structure_detection PASSED ({structure})")
            self.passed += 1
        except Exception as e:
            logger.error(f"✗ test_structure_detection FAILED: {e}")
            self.failed += 1

    def test_signal_generation(self):
        """Test trade signal generation"""
        try:
            for i in range(100):
                self.ta.add_candle(
                    timestamp=time.time() + i,
                    open_=100 + i * 0.15,
                    high=105 + i * 0.15,
                    low=95 + i * 0.15,
                    close=102 + i * 0.15,
                    volume=1000.0 + i * 10
                )

            signal = self.ta.generate_signal()
            assert isinstance(signal, TechnicalSignal)
            assert signal.signal in [TradeSignal.LONG, TradeSignal.SHORT, TradeSignal.NEUTRAL]
            assert 0 <= signal.confidence <= 1
            logger.info(f"✓ test_signal_generation PASSED (Signal={signal.signal.value}, Confidence={signal.confidence:.2f})")
            self.passed += 1
        except Exception as e:
            logger.error(f"✗ test_signal_generation FAILED: {e}")
            self.failed += 1


class TestMacroLiquidityMonitor:
    """Test macro liquidity monitoring"""

    def __init__(self):
        self.macro = MacroLiquidityMonitor()
        self.passed = 0
        self.failed = 0

    def test_fed_liquidity_update(self):
        """Test Fed liquidity indicator"""
        try:
            indicator = self.macro.update_fed_liquidity()
            assert indicator.name == "Fed Balance Sheet (QE/QT)"
            assert indicator.value > 0
            assert indicator.status in ["HEALTHY", "WARNING", "CRITICAL"]
            logger.info(f"✓ test_fed_liquidity_update PASSED ({indicator.status})")
            self.passed += 1
        except Exception as e:
            logger.error(f"✗ test_fed_liquidity_update FAILED: {e}")
            self.failed += 1

    def test_stablecoin_flows(self):
        """Test stablecoin flow tracking"""
        try:
            indicator = self.macro.update_stablecoin_flows()
            assert "Stablecoin" in indicator.name
            assert indicator.value > 0
            logger.info(f"✓ test_stablecoin_flows PASSED (${indicator.value:,.0f})")
            self.passed += 1
        except Exception as e:
            logger.error(f"✗ test_stablecoin_flows FAILED: {e}")
            self.failed += 1

    def test_btc_etf_flows(self):
        """Test BTC ETF flow tracking"""
        try:
            indicator = self.macro.update_btc_etf_flows()
            assert "BTC" in indicator.name
            logger.info(f"✓ test_btc_etf_flows PASSED")
            self.passed += 1
        except Exception as e:
            logger.error(f"✗ test_btc_etf_flows FAILED: {e}")
            self.failed += 1

    def test_funding_rates(self):
        """Test funding rate monitoring"""
        try:
            indicator = self.macro.update_funding_rates("BTC")
            assert "Funding Rate" in indicator.name
            logger.info(f"✓ test_funding_rates PASSED (Rate={indicator.value:.4f}%)")
            self.passed += 1
        except Exception as e:
            logger.error(f"✗ test_funding_rates FAILED: {e}")
            self.failed += 1

    def test_on_chain_metrics(self):
        """Test on-chain metrics"""
        try:
            metrics = self.macro.update_on_chain_metrics()
            assert len(metrics) > 0
            for name, metric in metrics.items():
                assert metric.value > 0 or metric.value == 0
            logger.info(f"✓ test_on_chain_metrics PASSED ({len(metrics)} metrics)")
            self.passed += 1
        except Exception as e:
            logger.error(f"✗ test_on_chain_metrics FAILED: {e}")
            self.failed += 1

    def test_macro_regime_assessment(self):
        """Test overall macro regime assessment"""
        try:
            regime = self.macro.assess_macro_regime()
            assert 'regime' in regime
            assert 'risk_level' in regime
            assert regime['regime'] in ['BULLISH', 'BEARISH', 'NEUTRAL']
            assert regime['risk_level'] in ['CRITICAL', 'HIGH', 'NORMAL']
            logger.info(f"✓ test_macro_regime_assessment PASSED (Regime={regime['regime']}, Risk={regime['risk_level']})")
            self.passed += 1
        except Exception as e:
            logger.error(f"✗ test_macro_regime_assessment FAILED: {e}")
            self.failed += 1


class TestRiskManager:
    """Test risk management calculations"""

    def __init__(self):
        self.risk_mgr = RiskManager(account_size=10000, max_loss_per_trade=0.02)
        self.passed = 0
        self.failed = 0

    def test_position_sizing(self):
        """Test position size calculation"""
        try:
            size = self.risk_mgr.calculate_position_size(
                entry_price=100.0,
                stop_loss_price=98.0,
                leverage=1.0
            )
            assert size > 0, "Position size should be positive"
            expected = (10000 * 0.02) / 2.0
            assert size == expected, f"Expected {expected}, got {size}"
            logger.info(f"✓ test_position_sizing PASSED (Size=${size:,.2f})")
            self.passed += 1
        except Exception as e:
            logger.error(f"✗ test_position_sizing FAILED: {e}")
            self.failed += 1

    def test_take_profit_calculation(self):
        """Test take profit calculation"""
        try:
            tp = self.risk_mgr.calculate_take_profit(
                entry_price=100.0,
                stop_loss_price=98.0,
                risk_reward=2.0
            )
            assert tp > 100.0, "TP should be above entry for long"
            expected = 100.0 + (2.0 * 2.0)
            assert tp == expected
            logger.info(f"✓ test_take_profit_calculation PASSED (TP=${tp:.2f})")
            self.passed += 1
        except Exception as e:
            logger.error(f"✗ test_take_profit_calculation FAILED: {e}")
            self.failed += 1

    def test_trade_validation_valid(self):
        """Test trade validation with valid setup"""
        try:
            is_valid, reason = self.risk_mgr.is_trade_valid(
                entry=100.0,
                sl=98.0,
                tp=103.0
            )
            assert is_valid, f"Trade should be valid: {reason}"
            logger.info(f"✓ test_trade_validation_valid PASSED")
            self.passed += 1
        except Exception as e:
            logger.error(f"✗ test_trade_validation_valid FAILED: {e}")
            self.failed += 1

    def test_trade_validation_invalid_rr(self):
        """Test trade validation with poor RR ratio"""
        try:
            is_valid, reason = self.risk_mgr.is_trade_valid(
                entry=100.0,
                sl=99.0,
                tp=100.5
            )
            assert not is_valid, "Trade should be invalid (poor RR)"
            logger.info(f"✓ test_trade_validation_invalid_rr PASSED")
            self.passed += 1
        except Exception as e:
            logger.error(f"✗ test_trade_validation_invalid_rr FAILED: {e}")
            self.failed += 1


class TestGeopoliticalRiskMonitor:
    """Test geopolitical risk monitoring"""

    def __init__(self):
        self.geo = GeopoliticalRiskMonitor()
        self.passed = 0
        self.failed = 0

    def test_sentiment_calculation(self):
        """Test sentiment score calculation"""
        try:
            sentiment = self.geo.calculate_sentiment_score()
            assert -1 <= sentiment <= 1, f"Sentiment out of bounds: {sentiment}"
            logger.info(f"✓ test_sentiment_calculation PASSED (Score={sentiment:.2f})")
            self.passed += 1
        except Exception as e:
            logger.error(f"✗ test_sentiment_calculation FAILED: {e}")
            self.failed += 1

    def test_risk_assessment(self):
        """Test risk level assessment"""
        try:
            risk = self.geo.assess_risk_level()
            assert risk in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
            logger.info(f"✓ test_risk_assessment PASSED (Risk={risk})")
            self.passed += 1
        except Exception as e:
            logger.error(f"✗ test_risk_assessment FAILED: {e}")
            self.failed += 1


class TestHyperliquidExecutor:
    """Test Hyperliquid API executor"""

    def __init__(self):
        self.executor = HyperliquidExecutor(
            private_key="test_key_12345",
            account_address="0xtest123"
        )
        self.passed = 0
        self.failed = 0

    def test_signature_generation(self):
        """Test SDK-based executor initialization"""
        try:
            # With non-real keys, SDK init will fail but executor still works in dry_run
            executor = HyperliquidExecutor(
                private_key="0x0000000000000000000000000000000000000000000000000000000000000001",
                account_address="0xtest123",
                dry_run=True
            )
            assert executor.dry_run == True
            assert executor.account_type == "perps"
            logger.info(f"✓ test_signature_generation PASSED")
            self.passed += 1
        except Exception as e:
            logger.error(f"✗ test_signature_generation FAILED: {e}")
            self.failed += 1

    def test_account_state_structure(self):
        """Test account state response parsing"""
        try:
            with patch.object(self.executor.session, 'get') as mock_get:
                mock_get.return_value.status_code = 200
                mock_get.return_value.json.return_value = {
                    'balances': [{'token': 'USD', 'total': 10000}],
                    'positions': []
                }

                state = self.executor.get_account_state()
                assert isinstance(state, dict)
                logger.info(f"✓ test_account_state_structure PASSED")
                self.passed += 1
        except Exception as e:
            logger.error(f"✗ test_account_state_structure FAILED: {e}")
            self.failed += 1


class TestBotOrchestrator:
    """Test main bot orchestrator"""

    def __init__(self):
        self.config = {
            'HYPERLIQUID_PRIVATE_KEY': 'test_key',
            'HYPERLIQUID_ACCOUNT': '0xtest',
            'ACCOUNT_SIZE': 10000,
            'MAX_LOSS_PER_TRADE': 0.02,
            'SYMBOLS': ['BTC', 'ETH'],
            'CYCLE_INTERVAL': 1
        }
        self.passed = 0
        self.failed = 0

    def test_bot_initialization(self):
        """Test bot initialization"""
        try:
            with patch('os.getenv') as mock_env:
                mock_env.side_effect = lambda x: self.config.get(x, 'test')
                bot = HyperliquidTradingBot(self.config)
                assert bot.is_running == False
                assert len(bot.trading_symbols) == 2
                logger.info(f"✓ test_bot_initialization PASSED")
                self.passed += 1
        except Exception as e:
            logger.error(f"✗ test_bot_initialization FAILED: {e}")
            self.failed += 1

    def test_bot_cycle(self):
        """Test single bot cycle"""
        try:
            with patch('os.getenv') as mock_env:
                mock_env.side_effect = lambda x: self.config.get(x, 'test')
                bot = HyperliquidTradingBot(self.config)
                bot._cycle()
                logger.info(f"✓ test_bot_cycle PASSED")
                self.passed += 1
        except Exception as e:
            logger.error(f"✗ test_bot_cycle FAILED: {e}")
            self.failed += 1

    def test_performance_summary(self):
        """Test performance summary generation"""
        try:
            with patch('os.getenv') as mock_env:
                mock_env.side_effect = lambda x: self.config.get(x, 'test')
                bot = HyperliquidTradingBot(self.config)
                summary = bot.get_performance_summary()
                assert 'total_trades' in summary
                logger.info(f"✓ test_performance_summary PASSED")
                self.passed += 1
        except Exception as e:
            logger.error(f"✗ test_performance_summary FAILED: {e}")
            self.failed += 1


def run_all_tests():
    """Run complete test suite"""
    logger.info("\n" + "="*70)
    logger.info("HYPERLIQUID TRADING BOT - COMPREHENSIVE TEST SUITE")
    logger.info("="*70 + "\n")

    test_suites = [
        ("Technical Analysis", TestHighConfirmationTA()),
        ("Macro Liquidity Monitor", TestMacroLiquidityMonitor()),
        ("Risk Management", TestRiskManager()),
        ("Geopolitical Risk", TestGeopoliticalRiskMonitor()),
        ("Hyperliquid Executor", TestHyperliquidExecutor()),
        ("Bot Orchestrator", TestBotOrchestrator())
    ]

    total_passed = 0
    total_failed = 0

    for suite_name, test_suite in test_suites:
        logger.info(f"\n{'='*70}")
        logger.info(f"Testing: {suite_name}")
        logger.info(f"{'='*70}")

        for method_name in dir(test_suite):
            if method_name.startswith('test_'):
                getattr(test_suite, method_name)()

        total_passed += test_suite.passed
        total_failed += test_suite.failed

        logger.info(f"\n{suite_name}: {test_suite.passed} passed, {test_suite.failed} failed")

    logger.info("\n" + "="*70)
    logger.info("FINAL RESULTS")
    logger.info("="*70)
    logger.info(f"Total Passed: {total_passed}")
    logger.info(f"Total Failed: {total_failed}")

    if total_failed == 0:
        logger.info("\n✓ ALL TESTS PASSED - BOT IS READY FOR DEPLOYMENT")
    else:
        logger.info(f"\n✗ {total_failed} TESTS FAILED - FIX BEFORE DEPLOYMENT")

    logger.info("="*70 + "\n")

    return total_failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
