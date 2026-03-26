#!/usr/bin/env python3
"""
COMPREHENSIVE BACKEND TEST FOR HYPERLIQUID TRADING BOT
Tests all backend functionality including API connections, data fetching, and trading logic
"""

import os
import sys
import time
import json
import logging
from datetime import datetime
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()

# Import bot modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hyperliquid_trading_bot import (
    HyperliquidTradingBot, HyperliquidExecutor, HighConfirmationTA,
    MacroLiquidityMonitor, RiskManager, TradeSignal
)

class HyperliquidBotTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []
        
        # Test configuration
        self.config = {
            'HYPERLIQUID_PRIVATE_KEY': os.getenv('HYPERLIQUID_PRIVATE_KEY'),
            'HYPERLIQUID_ACCOUNT': os.getenv('HYPERLIQUID_ACCOUNT'),
            'ACCOUNT_SIZE': float(os.getenv('ACCOUNT_SIZE', 10000)),
            'MAX_LOSS_PER_TRADE': float(os.getenv('MAX_LOSS_PER_TRADE', 0.02)),
            'SYMBOLS': os.getenv('SYMBOLS', 'BTC,ETH').split(','),
            'CYCLE_INTERVAL': int(os.getenv('CYCLE_INTERVAL', 60)),
            'USE_TESTNET': os.getenv('USE_TESTNET', 'false').lower() == 'true',
            'DRY_RUN': os.getenv('DRY_RUN', 'true').lower() == 'true',
        }

    def run_test(self, test_name, test_func):
        """Run a single test and track results"""
        self.tests_run += 1
        logger.info(f"\n🔍 Testing {test_name}...")
        
        try:
            result = test_func()
            if result:
                self.tests_passed += 1
                logger.info(f"✅ {test_name} PASSED")
                return True
            else:
                self.tests_failed += 1
                self.failures.append(test_name)
                logger.error(f"❌ {test_name} FAILED")
                return False
        except Exception as e:
            self.tests_failed += 1
            self.failures.append(f"{test_name}: {str(e)}")
            logger.error(f"❌ {test_name} FAILED with exception: {e}")
            return False

    def test_environment_variables(self):
        """Test that all required environment variables are set"""
        required_vars = ['HYPERLIQUID_PRIVATE_KEY', 'HYPERLIQUID_ACCOUNT']
        
        for var in required_vars:
            if not self.config.get(var):
                logger.error(f"Missing required environment variable: {var}")
                return False
        
        logger.info(f"Account: {self.config['HYPERLIQUID_ACCOUNT']}")
        logger.info(f"Testnet: {self.config['USE_TESTNET']}")
        logger.info(f"Dry Run: {self.config['DRY_RUN']}")
        return True

    def test_hyperliquid_executor_init(self):
        """Test HyperliquidExecutor initialization"""
        try:
            executor = HyperliquidExecutor(
                private_key=self.config['HYPERLIQUID_PRIVATE_KEY'],
                account_address=self.config['HYPERLIQUID_ACCOUNT'],
                is_testnet=self.config['USE_TESTNET'],
                dry_run=self.config['DRY_RUN']
            )
            
            # Check initialization
            assert executor.is_testnet == self.config['USE_TESTNET']
            assert executor.dry_run == self.config['DRY_RUN']
            assert executor.account_type == ("unified" if self.config['USE_TESTNET'] else "perps")
            
            logger.info(f"Executor initialized - Account Type: {executor.account_type}")
            return True
        except Exception as e:
            logger.error(f"Executor initialization failed: {e}")
            return False

    def test_account_state_fetch(self):
        """Test fetching account state from Hyperliquid API"""
        try:
            executor = HyperliquidExecutor(
                private_key=self.config['HYPERLIQUID_PRIVATE_KEY'],
                account_address=self.config['HYPERLIQUID_ACCOUNT'],
                is_testnet=self.config['USE_TESTNET'],
                dry_run=self.config['DRY_RUN']
            )
            
            state = executor.get_account_state()
            
            if not state:
                logger.error("No account state returned")
                return False
            
            # Check expected fields
            expected_fields = ['marginSummary', 'assetPositions']
            for field in expected_fields:
                if field not in state:
                    logger.error(f"Missing field in account state: {field}")
                    return False
            
            margin = state.get('marginSummary', {})
            account_value = float(margin.get('accountValue', 0))
            logger.info(f"Account Value: ${account_value:,.2f}")
            
            positions = state.get('assetPositions', [])
            logger.info(f"Open Positions: {len(positions)}")
            
            return True
        except Exception as e:
            logger.error(f"Account state fetch failed: {e}")
            return False

    def test_candle_data_fetch(self):
        """Test fetching live candle data from Hyperliquid"""
        try:
            executor = HyperliquidExecutor(
                private_key=self.config['HYPERLIQUID_PRIVATE_KEY'],
                account_address=self.config['HYPERLIQUID_ACCOUNT'],
                is_testnet=self.config['USE_TESTNET'],
                dry_run=self.config['DRY_RUN']
            )
            
            # Test BTC candles
            candles = executor.fetch_candles('BTC', interval='1m', count=10)
            
            if not candles:
                logger.error("No candle data returned")
                return False
            
            if len(candles) == 0:
                logger.error("Empty candle data")
                return False
            
            # Validate candle structure
            latest = candles[-1]
            required_fields = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            for field in required_fields:
                if field not in latest:
                    logger.error(f"Missing field in candle: {field}")
                    return False
            
            logger.info(f"Fetched {len(candles)} BTC candles")
            logger.info(f"Latest BTC: Open=${latest['open']:,.2f}, Close=${latest['close']:,.2f}, Volume={latest['volume']:,.0f}")
            
            # Test ETH candles
            eth_candles = executor.fetch_candles('ETH', interval='1m', count=5)
            if eth_candles:
                logger.info(f"Fetched {len(eth_candles)} ETH candles")
                logger.info(f"Latest ETH: ${eth_candles[-1]['close']:,.2f}")
            
            return True
        except Exception as e:
            logger.error(f"Candle data fetch failed: {e}")
            return False

    def test_technical_analysis_engine(self):
        """Test TA engine with real market data"""
        try:
            executor = HyperliquidExecutor(
                private_key=self.config['HYPERLIQUID_PRIVATE_KEY'],
                account_address=self.config['HYPERLIQUID_ACCOUNT'],
                is_testnet=self.config['USE_TESTNET'],
                dry_run=self.config['DRY_RUN']
            )
            
            # Fetch real candle data
            candles = executor.fetch_candles('BTC', interval='1m', count=100)
            if not candles:
                logger.error("No candle data for TA test")
                return False
            
            # Initialize TA engine
            ta = HighConfirmationTA()
            
            # Feed candles to TA engine
            for candle in candles:
                ta.add_candle(
                    timestamp=candle['timestamp'],
                    open_=candle['open'],
                    high=candle['high'],
                    low=candle['low'],
                    close=candle['close'],
                    volume=candle['volume']
                )
            
            # Generate signal
            signal = ta.generate_signal()
            
            # Validate signal
            assert signal.signal in [TradeSignal.LONG, TradeSignal.SHORT, TradeSignal.NEUTRAL, TradeSignal.WAIT]
            assert 0 <= signal.confidence <= 1
            assert isinstance(signal.confirmations, list)
            
            logger.info(f"TA Signal: {signal.signal.value}")
            logger.info(f"Confidence: {signal.confidence:.2%}")
            logger.info(f"Confirmations: {len(signal.confirmations)} - {signal.confirmations}")
            logger.info(f"Support: ${signal.support_level:,.2f}")
            logger.info(f"Resistance: ${signal.resistance_level:,.2f}")
            
            return True
        except Exception as e:
            logger.error(f"TA engine test failed: {e}")
            return False

    def test_macro_liquidity_monitor(self):
        """Test macro liquidity monitoring"""
        try:
            api_url = "https://api.hyperliquid-testnet.xyz" if self.config['USE_TESTNET'] else "https://api.hyperliquid.xyz"
            macro = MacroLiquidityMonitor(api_url=api_url)
            
            # Test macro regime assessment
            regime = macro.assess_macro_regime()
            
            # Validate regime structure
            required_fields = ['regime', 'risk_level', 'bullish_indicators', 'bearish_indicators']
            for field in required_fields:
                if field not in regime:
                    logger.error(f"Missing field in macro regime: {field}")
                    return False
            
            logger.info(f"Macro Regime: {regime['regime']}")
            logger.info(f"Risk Level: {regime['risk_level']}")
            logger.info(f"Bullish Indicators: {regime['bullish_indicators']}")
            logger.info(f"Bearish Indicators: {regime['bearish_indicators']}")
            
            return True
        except Exception as e:
            logger.error(f"Macro monitor test failed: {e}")
            return False

    def test_risk_manager(self):
        """Test risk management calculations"""
        try:
            risk_mgr = RiskManager(
                account_size=self.config['ACCOUNT_SIZE'],
                max_loss_per_trade=self.config['MAX_LOSS_PER_TRADE']
            )
            
            # Test position sizing
            entry_price = 70000.0
            stop_loss = 68000.0
            leverage = 2.0
            
            position_size = risk_mgr.calculate_position_size(entry_price, stop_loss, leverage)
            
            if position_size <= 0:
                logger.error("Position size calculation returned zero or negative")
                return False
            
            logger.info(f"Position Size: ${position_size:,.2f}")
            
            # Test take profit calculation
            tp_long = risk_mgr.calculate_take_profit(entry_price, stop_loss, risk_reward=2.0, side="LONG")
            tp_short = risk_mgr.calculate_take_profit(entry_price, stop_loss, risk_reward=2.0, side="SHORT")
            
            logger.info(f"Take Profit LONG: ${tp_long:,.2f}")
            logger.info(f"Take Profit SHORT: ${tp_short:,.2f}")
            
            # Validate TP directions
            if tp_long <= entry_price:
                logger.error("LONG take profit should be above entry")
                return False
            
            if tp_short >= entry_price:
                logger.error("SHORT take profit should be below entry")
                return False
            
            # Test trade validation
            is_valid, reason = risk_mgr.is_trade_valid(entry_price, stop_loss, tp_long)
            logger.info(f"Trade Validation: {is_valid} - {reason}")
            
            return True
        except Exception as e:
            logger.error(f"Risk manager test failed: {e}")
            return False

    def test_bot_initialization(self):
        """Test full bot initialization"""
        try:
            bot = HyperliquidTradingBot(self.config)
            
            # Check bot components
            assert bot.ta_engine is not None
            assert bot.macro_monitor is not None
            assert bot.executor is not None
            assert bot.risk_manager is not None
            
            # Check configuration
            assert bot.trading_symbols == self.config['SYMBOLS']
            assert bot.is_testnet == self.config['USE_TESTNET']
            assert bot.dry_run == self.config['DRY_RUN']
            
            logger.info(f"Bot initialized successfully")
            logger.info(f"Trading symbols: {bot.trading_symbols}")
            logger.info(f"Mode: {'TESTNET' if bot.is_testnet else 'MAINNET'}")
            logger.info(f"Type: {'DRY RUN' if bot.dry_run else 'LIVE'}")
            
            return True
        except Exception as e:
            logger.error(f"Bot initialization failed: {e}")
            return False

    def test_bot_cycle(self):
        """Test a complete bot cycle"""
        try:
            bot = HyperliquidTradingBot(self.config)
            
            # Run one cycle
            bot._cycle()
            
            # Check performance summary
            summary = bot.get_performance_summary()
            
            logger.info(f"Cycle completed successfully")
            logger.info(f"Total trades: {summary.get('total_trades', 0)}")
            logger.info(f"Symbols analyzed: {len(summary.get('symbols_traded', []))}")
            
            return True
        except Exception as e:
            logger.error(f"Bot cycle test failed: {e}")
            return False

    def test_order_placement_dry_run(self):
        """Test order placement in dry run mode"""
        try:
            # Force dry run for this test
            test_config = self.config.copy()
            test_config['DRY_RUN'] = True
            
            bot = HyperliquidTradingBot(test_config)
            
            # Test order placement
            result = bot.executor.place_order(
                symbol='BTC',
                side='BUY',
                size=0.001,  # Small size
                limit_price=70000.0,
                leverage=1.0
            )
            
            if not result:
                logger.error("Order placement returned None")
                return False
            
            # Check dry run result
            if 'dry_run_simulated' not in str(result.get('status', '')):
                logger.error("Expected dry run simulation status")
                return False
            
            logger.info(f"Dry run order result: {result}")
            return True
        except Exception as e:
            logger.error(f"Order placement test failed: {e}")
            return False

    def test_funding_rate_fetch(self):
        """Test funding rate fetching"""
        try:
            api_url = "https://api.hyperliquid-testnet.xyz" if self.config['USE_TESTNET'] else "https://api.hyperliquid.xyz"
            macro = MacroLiquidityMonitor(api_url=api_url)
            
            # Test funding rate for BTC
            funding_indicator = macro.update_funding_rates('BTC')
            
            logger.info(f"BTC Funding Rate: {funding_indicator.value:.6f}")
            logger.info(f"Funding Impact: {funding_indicator.impact}")
            
            return True
        except Exception as e:
            logger.error(f"Funding rate test failed: {e}")
            return False

    def run_all_tests(self):
        """Run all backend tests"""
        logger.info("=" * 80)
        logger.info("HYPERLIQUID TRADING BOT - COMPREHENSIVE BACKEND TEST")
        logger.info("=" * 80)
        logger.info(f"Started: {datetime.now().isoformat()}")
        logger.info("")
        
        # Define test suite
        tests = [
            ("Environment Variables", self.test_environment_variables),
            ("HyperliquidExecutor Initialization", self.test_hyperliquid_executor_init),
            ("Account State Fetch", self.test_account_state_fetch),
            ("Candle Data Fetch", self.test_candle_data_fetch),
            ("Technical Analysis Engine", self.test_technical_analysis_engine),
            ("Macro Liquidity Monitor", self.test_macro_liquidity_monitor),
            ("Risk Manager", self.test_risk_manager),
            ("Bot Initialization", self.test_bot_initialization),
            ("Bot Cycle", self.test_bot_cycle),
            ("Order Placement (Dry Run)", self.test_order_placement_dry_run),
            ("Funding Rate Fetch", self.test_funding_rate_fetch),
        ]
        
        # Run all tests
        for test_name, test_func in tests:
            self.run_test(test_name, test_func)
            time.sleep(0.5)  # Brief pause between tests
        
        # Print final results
        logger.info("\n" + "=" * 80)
        logger.info("BACKEND TEST RESULTS")
        logger.info("=" * 80)
        logger.info(f"Tests Run: {self.tests_run}")
        logger.info(f"Tests Passed: {self.tests_passed}")
        logger.info(f"Tests Failed: {self.tests_failed}")
        
        if self.tests_failed == 0:
            logger.info("\n✅ ALL BACKEND TESTS PASSED")
            logger.info("Bot backend is ready for deployment!")
        else:
            logger.info(f"\n❌ {self.tests_failed} TESTS FAILED")
            logger.info("Failed tests:")
            for failure in self.failures:
                logger.info(f"  - {failure}")
        
        logger.info("=" * 80)
        logger.info(f"Completed: {datetime.now().isoformat()}")
        
        return self.tests_failed == 0

def main():
    """Main test runner"""
    tester = HyperliquidBotTester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())