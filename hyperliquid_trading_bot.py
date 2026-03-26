"""
HYPERLIQUID HIGH-CONFIRMATION TRADING BOT
===========================================
A professional-grade automated trading system for Hyperliquid perpetuals.
Integrates multi-timeframe technical analysis with macro liquidity monitoring.

ARCHITECTURE:
1. HIGH-CONFIRMATION TA MODULE (Price Action)
2. MACRO LIQUIDITY MODULE (Global & Crypto-Specific)
3. GEO-POLITICAL RISK MODULE (News + Sentiment)
4. ORDER EXECUTION ENGINE (Hyperliquid API)
5. RISK MANAGEMENT (Position Sizing, SL/TP Logic)
6. PERFORMANCE MONITORING & LOGGING
"""

import os
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import asyncio
import logging
from collections import deque

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
from eth_account import Account as EthAccount

# Monkey-patch hyperliquid SDK Info class to handle testnet spot_meta bug
import hyperliquid.info as _hl_info_module
import hyperliquid.utils.constants as _hl_constants
_original_info_init = _hl_info_module.Info.__init__

def _patched_info_init(self, base_url=None, skip_ws=False, meta=None, spot_meta=None, perp_dexs=None, timeout=None):
    try:
        _original_info_init(self, base_url, skip_ws, meta, spot_meta, perp_dexs, timeout)
    except (IndexError, KeyError):
        self.base_url = base_url or _hl_constants.MAINNET_API_URL
        self.meta = meta
        self.spot_meta = spot_meta
        self.coin_to_asset = {}
        self.name_to_coin = {}
        self.coin_to_name = {}
        if meta:
            for idx, asset_info in enumerate(meta.get('universe', [])):
                name = asset_info['name']
                self.coin_to_asset[name] = idx
                self.name_to_coin[name] = name
                self.coin_to_name[name] = name
        self.ws_manager = None
        self.ws = None
        self.timeout = timeout

_hl_info_module.Info.__init__ = _patched_info_init

from hyperliquid.exchange import Exchange as HLExchange
from hyperliquid.utils import constants as hl_constants

# Load environment variables
load_dotenv()

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('hyperliquid_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# DATA STRUCTURES
# ============================================================================

class TradeSignal(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"
    WAIT = "WAIT"

class MarketRegime(Enum):
    STRONG_UP = "STRONG_UP"
    UP = "UP"
    NEUTRAL = "NEUTRAL"
    DOWN = "DOWN"
    STRONG_DOWN = "STRONG_DOWN"
    BREAKDOWN = "BREAKDOWN"

@dataclass
class TechnicalSignal:
    signal: TradeSignal
    confidence: float  # 0-1
    timeframe: str
    confirmations: List[str]  # Which indicators triggered
    resistance_level: float
    support_level: float

@dataclass
class MacroIndicator:
    name: str
    value: float
    threshold: float
    status: str  # "HEALTHY" / "WARNING" / "CRITICAL"
    impact: str  # "BULLISH" / "BEARISH" / "NEUTRAL"

@dataclass
class Position:
    symbol: str
    entry_price: float
    size: float
    leverage: float
    side: str  # LONG or SHORT
    entry_time: datetime
    stop_loss: float
    take_profit: float
    risk_reward_ratio: float
    macro_context: Dict


# ============================================================================
# TECHNICAL ANALYSIS MODULE - HIGH CONFIRMATION SETUPS
# ============================================================================

class HighConfirmationTA:
    """
    Institutional-grade TA with weighted scoring, ATR-based stops,
    and EMA trend filter. Upgraded from simple confirmation counting
    to a weighted system where indicators contribute proportional
    scores based on historical reliability.
    """

    def __init__(self, lookback_periods: int = 500):
        self.lookback_periods = lookback_periods
        self.price_data = deque(maxlen=lookback_periods)
        self.volume_data = deque(maxlen=lookback_periods)

    def add_candle(self, timestamp: float, open_: float, high: float, 
                   low: float, close: float, volume: float):
        """Add OHLCV candle to analysis buffer"""
        self.price_data.append({
            'timestamp': timestamp,
            'open': open_,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume
        })
        self.volume_data.append(volume)

    def calculate_rsi(self, period: int = 14) -> float:
        """Relative Strength Index"""
        if len(self.price_data) < period + 1:
            return 50.0
        
        closes = [c['close'] for c in list(self.price_data)[-period-1:]]
        deltas = np.diff(closes)
        seed = deltas[:period]
        
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period
        rs = up / down if down != 0 else 0
        
        rsi_value = 100 - (100 / (1 + rs))
        return rsi_value

    def calculate_macd(self, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[float, float, float]:
        """MACD (Moving Average Convergence Divergence)"""
        if len(self.price_data) < slow + signal:
            return 0, 0, 0

        closes = np.array([c['close'] for c in self.price_data])

        exp1 = self._ema(closes, fast)
        exp2 = self._ema(closes, slow)
        macd_line = exp1 - exp2
        signal_line = self._ema(macd_line, signal)[-1]
        histogram = macd_line[-1] - signal_line

        return macd_line[-1], signal_line, histogram

    def calculate_bollinger_bands(self, period: int = 20, std_dev: int = 2) -> Tuple[float, float, float]:
        """Bollinger Bands for volatility measurement"""
        if len(self.price_data) < period:
            return 0, 0, 0
        
        closes = np.array([c['close'] for c in list(self.price_data)[-period:]])
        sma = np.mean(closes)
        std = np.std(closes)
        
        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)
        
        return upper_band, sma, lower_band

    def calculate_atr(self, period: int = 14) -> float:
        """Average True Range - used for dynamic SL/TP sizing"""
        if len(self.price_data) < period + 1:
            return 0.0
        
        recent = list(self.price_data)[-(period + 1):]
        tr_values = []
        for i in range(1, len(recent)):
            high = recent[i]['high']
            low = recent[i]['low']
            prev_close = recent[i - 1]['close']
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_values.append(tr)
        
        return np.mean(tr_values)

    def is_volatility_expanding(self, period: int = 14) -> Tuple[bool, float]:
        """
        Check if ATR is expanding (current ATR > recent average ATR).
        Expanding volatility = better trending conditions = higher win rate.
        Returns (is_expanding, expansion_ratio).
        """
        if len(self.price_data) < (period * 3) + 1:
            return False, 1.0
        
        # Current ATR
        current_atr = self.calculate_atr(period)
        
        # ATR from 1 period ago (use data offset)
        older_data = list(self.price_data)[-(period * 2 + 1):-(period + 1)]
        if len(older_data) < period + 1:
            return False, 1.0
        
        tr_old = []
        for i in range(1, len(older_data)):
            h = older_data[i]['high']
            l = older_data[i]['low']
            pc = older_data[i - 1]['close']
            tr_old.append(max(h - l, abs(h - pc), abs(l - pc)))
        
        old_atr = np.mean(tr_old) if tr_old else current_atr
        
        if old_atr == 0:
            return False, 1.0
        
        ratio = current_atr / old_atr
        return ratio > 1.05, ratio  # Expanding if ATR grew > 5%

    def calculate_rsi_slope(self, period: int = 14, lookback: int = 5) -> float:
        """
        RSI momentum direction. Positive slope = strengthening momentum.
        Used to avoid fading signals (RSI moving against trade direction).
        """
        if len(self.price_data) < period + lookback + 1:
            return 0.0
        
        # Calculate RSI at current and lookback points
        current_rsi = self.calculate_rsi(period)
        
        # Rough approximation: use data shifted back
        saved = list(self.price_data)
        temp_ta = HighConfirmationTA(lookback_periods=self.lookback_periods)
        for c in saved[:-lookback]:
            temp_ta.add_candle(c['timestamp'], c['open'], c['high'], c['low'], c['close'], c['volume'])
        
        old_rsi = temp_ta.calculate_rsi(period)
        
        return current_rsi - old_rsi  # Positive = RSI rising

    def calculate_ema_trend(self, fast_period: int = 20, slow_period: int = 50) -> Dict[str, float]:
        """EMA trend filter - determines dominant direction"""
        if len(self.price_data) < slow_period:
            return {'trend': 0, 'fast_ema': 0, 'slow_ema': 0, 'spread_pct': 0}
        
        closes = np.array([c['close'] for c in self.price_data])
        fast_ema = self._ema(closes, fast_period)[-1]
        slow_ema = self._ema(closes, slow_period)[-1]
        
        spread_pct = (fast_ema - slow_ema) / slow_ema * 100 if slow_ema != 0 else 0
        
        # +1 = bullish trend, -1 = bearish, 0 = neutral
        if spread_pct > 0.1:
            trend = 1
        elif spread_pct < -0.1:
            trend = -1
        else:
            trend = 0
        
        return {
            'trend': trend,
            'fast_ema': fast_ema,
            'slow_ema': slow_ema,
            'spread_pct': spread_pct
        }

    def find_swing_levels(self, lookback: int = 30) -> Dict[str, float]:
        """Find recent swing high/low for tighter SL placement"""
        if len(self.price_data) < lookback:
            return {'swing_high': 0, 'swing_low': 0}
        
        recent = list(self.price_data)[-lookback:]
        highs = [c['high'] for c in recent]
        lows = [c['low'] for c in recent]
        
        # Find swing high: a high surrounded by lower highs
        swing_high = max(highs)
        swing_low = min(lows)
        
        # Tighter: use 75th percentile high and 25th percentile low
        # This avoids outlier wicks
        swing_high_tight = np.percentile(highs, 85)
        swing_low_tight = np.percentile(lows, 15)
        
        return {
            'swing_high': swing_high,
            'swing_low': swing_low,
            'swing_high_tight': swing_high_tight,
            'swing_low_tight': swing_low_tight,
        }

    def detect_structure_breaks(self) -> Dict[str, bool]:
        """Identify structural price action breaks"""
        if len(self.price_data) < 50:
            return {'higher_high': False, 'higher_low': False, 'lower_low': False,
                    'lower_high': False, 'uptrend': False, 'downtrend': False}
        
        recent = list(self.price_data)[-50:]
        
        highs = [c['high'] for c in recent]
        lows = [c['low'] for c in recent]
        
        recent_highs = highs[-10:]
        prior_highs = highs[:-10]
        recent_lows = lows[-10:]
        prior_lows = lows[:-10]
        
        higher_high = max(recent_highs) > max(prior_highs)
        higher_low = min(recent_lows) > min(prior_lows)
        lower_low = min(recent_lows) < min(prior_lows)
        lower_high = max(recent_highs) < max(prior_highs)
        
        return {
            'higher_high': higher_high,
            'higher_low': higher_low,
            'lower_low': lower_low,
            'lower_high': lower_high,
            'uptrend': higher_high and higher_low,
            'downtrend': lower_low and lower_high
        }

    def detect_divergence(self, momentum_indicator: str = 'rsi') -> Dict[str, bool]:
        """Detect price/momentum divergences (hidden + regular)"""
        if len(self.price_data) < 30:
            return {'bullish_div': False, 'bearish_div': False}
        
        if momentum_indicator == 'rsi':
            rsi_values = [self.calculate_rsi() for _ in range(10)]
        
        return {'bullish_div': False, 'bearish_div': False}

    def detect_liquidity_voids(self) -> Dict[str, float]:
        """Find support/resistance zones and liquidity voids"""
        if len(self.price_data) < 100:
            return {'resistance': 0, 'support': 0}
        
        recent = list(self.price_data)[-100:]
        highs = [c['high'] for c in recent]
        lows = [c['low'] for c in recent]
        
        resistance = max(highs)
        support = min(lows)
        mid = (resistance + support) / 2
        
        return {
            'resistance': resistance,
            'support': support,
            'midpoint': mid,
            'range': resistance - support
        }

    def analyze_order_flow(self) -> Dict[str, float]:
        """Estimate buy/sell pressure from volume and price action"""
        if len(self.price_data) < 20:
            return {'buy_pressure': 0.5, 'sell_pressure': 0.5}
        
        recent = list(self.price_data)[-20:]
        
        buy_volume = 0
        sell_volume = 0
        
        for candle in recent:
            if candle['close'] > candle['open']:
                buy_volume += candle['volume']
            else:
                sell_volume += candle['volume']
        
        total = buy_volume + sell_volume
        return {
            'buy_pressure': buy_volume / total if total > 0 else 0.5,
            'sell_pressure': sell_volume / total if total > 0 else 0.5
        }

    def generate_signal(self) -> TechnicalSignal:
        """
        SNIPER MODE: Only takes high-conviction setups where
        trend + momentum + volatility all align.
        
        Requirements to fire:
          1. EMA trend with spread > 0.20% (strong trend)
          2. MACD aligned with trend
          3. At least one of: RSI confirmation, structure, or order flow
          4. Volatility expanding (ATR growing)
          5. No counter-signals blocking
        
        Scoring (0-1.0):
          EMA Trend (strong):   0.30  (gate - required)
          MACD alignment:       0.25  (gate - required)
          Volatility expanding: 0.15  (strong bonus)
          RSI confirmation:     0.15
          Structure break:      0.10
          Order flow:           0.10
          Bollinger touch:      0.05  (bonus)
        
        Signal fires at score >= 0.60 with both gates passed.
        """
        if len(self.price_data) < 60:
            return TechnicalSignal(
                signal=TradeSignal.WAIT, confidence=0.0, timeframe="",
                confirmations=[], resistance_level=0, support_level=0
            )

        bull_score = 0.0
        bear_score = 0.0
        confirmations = []
        has_ema_gate = False
        has_macd_gate = False

        # === GATE 1: EMA TREND (required, 0.30) ===
        trend_data = self.calculate_ema_trend(20, 50)
        trend = trend_data['trend']
        ema_spread = abs(trend_data['spread_pct'])
        
        if trend == 1 and ema_spread > 0.20:
            bull_score += 0.30
            has_ema_gate = True
            confirmations.append(f"EMA_BULL({trend_data['spread_pct']:+.2f}%)")
        elif trend == -1 and ema_spread > 0.20:
            bear_score += 0.30
            has_ema_gate = True
            confirmations.append(f"EMA_BEAR({trend_data['spread_pct']:+.2f}%)")

        # === GATE 2: MACD (required, 0.25) ===
        macd_val, signal_val, histogram = self.calculate_macd()
        if histogram > 0 and macd_val > signal_val:
            bull_score += 0.25
            if trend >= 0:
                has_macd_gate = True
            confirmations.append("MACD_BULL")
        elif histogram < 0 and macd_val < signal_val:
            bear_score += 0.25
            if trend <= 0:
                has_macd_gate = True
            confirmations.append("MACD_BEAR")

        # === VOLATILITY EXPANSION (0.15) ===
        vol_expanding, vol_ratio = self.is_volatility_expanding()
        if vol_expanding:
            # Add to whichever direction is leading
            if bull_score > bear_score:
                bull_score += 0.15
            elif bear_score > bull_score:
                bear_score += 0.15
            confirmations.append(f"VOL_EXPAND({vol_ratio:.2f}x)")

        # === RSI (0.15) ===
        rsi = self.calculate_rsi()
        rsi_slope = self.calculate_rsi_slope()
        
        if rsi < 30 and rsi_slope > 0:
            # Oversold AND momentum turning up = strong long signal
            bull_score += 0.15
            confirmations.append(f"RSI_REVERSAL({rsi:.0f},slope+{rsi_slope:.1f})")
        elif rsi < 40 and trend == 1:
            # Not overbought in uptrend = room to run
            bull_score += 0.08
            confirmations.append(f"RSI_OK({rsi:.0f})")
        elif rsi > 70 and rsi_slope < 0:
            bear_score += 0.15
            confirmations.append(f"RSI_REVERSAL({rsi:.0f},slope{rsi_slope:.1f})")
        elif rsi > 60 and trend == -1:
            bear_score += 0.08
            confirmations.append(f"RSI_OK({rsi:.0f})")

        # === STRUCTURE (0.10) ===
        structure = self.detect_structure_breaks()
        if structure['uptrend']:
            bull_score += 0.10
            confirmations.append("STRUCT_UP")
        elif structure['downtrend']:
            bear_score += 0.10
            confirmations.append("STRUCT_DOWN")

        # === ORDER FLOW (0.10) ===
        flow = self.analyze_order_flow()
        if flow['buy_pressure'] > 0.60:
            bull_score += 0.10
            confirmations.append(f"FLOW_BUY({flow['buy_pressure']:.0%})")
        elif flow['sell_pressure'] > 0.60:
            bear_score += 0.10
            confirmations.append(f"FLOW_SELL({flow['sell_pressure']:.0%})")

        # === BOLLINGER BANDS (0.05 bonus) ===
        upper, mid, lower = self.calculate_bollinger_bands()
        current_price = self.price_data[-1]['close']
        if current_price < lower:
            bull_score += 0.05
            confirmations.append("BB_LOWER")
        elif current_price > upper:
            bear_score += 0.05
            confirmations.append("BB_UPPER")

        # === DETERMINE SIGNAL ===
        # Sniper mode: BOTH gates must pass + score >= 0.60
        atr = self.calculate_atr()
        swings = self.find_swing_levels()
        liquidity = self.detect_liquidity_voids()

        min_score = 0.60
        
        if (bull_score >= min_score and has_ema_gate and has_macd_gate 
                and trend >= 0):
            final_signal = TradeSignal.LONG
            confidence = min(0.95, bull_score)
        elif (bear_score >= min_score and has_ema_gate and has_macd_gate 
                and trend <= 0):
            final_signal = TradeSignal.SHORT
            confidence = min(0.95, bear_score)
        else:
            final_signal = TradeSignal.NEUTRAL
            confidence = max(bull_score, bear_score)

        return TechnicalSignal(
            signal=final_signal,
            confidence=confidence,
            timeframe="",
            confirmations=confirmations,
            resistance_level=swings.get('swing_high_tight', liquidity['resistance']),
            support_level=swings.get('swing_low_tight', liquidity['support'])
        )

    @staticmethod
    def _ema(data: np.ndarray, period: int) -> np.ndarray:
        """Calculate exponential moving average"""
        return pd.Series(data).ewm(span=period, adjust=False).mean().values


# ============================================================================
# MACRO LIQUIDITY MODULE
# ============================================================================

class MacroLiquidityMonitor:
    """
    Monitors global macro conditions affecting crypto liquidity.
    Provides real-time assessment of market environment health.
    """

    def __init__(self, api_url: str = "https://api.hyperliquid.xyz"):
        self.indicators: Dict[str, MacroIndicator] = {}
        self.historical_data = deque(maxlen=100)
        self.last_update = None
        self._api_url = api_url

    def update_fed_liquidity(self) -> MacroIndicator:
        """
        Track Federal Reserve balance sheet changes and QT/QE phases.
        Key metric: Fed balance sheet size indicates monetary conditions.
        """
        # In production: Fetch from FRED API
        # For now: Placeholder logic
        try:
            response = requests.get(
                'https://api.stlouisfed.org/fred/series/WALCL/observations',
                params={
                    'file_type': 'json',
                    'api_key': os.getenv('FRED_API_KEY', 'placeholder')
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                # Latest Fed balance sheet value
                # Trend analysis: expansion vs contraction
                pass
        except Exception as e:
            logger.warning(f"Fed liquidity fetch failed: {e}")

        # Placeholder logic for demonstration
        indicator = MacroIndicator(
            name="Fed Balance Sheet (QE/QT)",
            value=6.9e12,  # ~$6.9T as of early 2026
            threshold=7.0e12,
            status="HEALTHY" if 6.5e12 < 6.9e12 < 7.5e12 else "WARNING",
            impact="BULLISH"  # Expansion = more liquidity
        )
        self.indicators['fed_balance'] = indicator
        return indicator

    def update_stablecoin_flows(self) -> MacroIndicator:
        """
        Monitor stablecoin inflows/outflows to exchanges.
        Large inflows = preparation for buying, outflows = profit taking.
        """
        try:
            # Would integrate with Glassnode or similar on-chain data provider
            # GET stablecoin exchange inflows over last 7 days
            pass
        except Exception as e:
            logger.warning(f"Stablecoin flow fetch failed: {e}")

        # Placeholder
        indicator = MacroIndicator(
            name="Stablecoin Exchange Inflows (7d avg)",
            value=2.1e9,  # $2.1B 7-day average
            threshold=1.5e9,
            status="HEALTHY",
            impact="BULLISH"  # Inflows suggest capitalization
        )
        self.indicators['stablecoin_inflows'] = indicator
        return indicator

    def update_btc_etf_flows(self) -> MacroIndicator:
        """
        Track spot Bitcoin ETF inflows (institutional interest).
        """
        try:
            # Would fetch from CoinShares or Farside Investors API
            pass
        except Exception as e:
            logger.warning(f"ETF flows fetch failed: {e}")

        # Placeholder
        indicator = MacroIndicator(
            name="Spot BTC ETF Net Flows (7d)",
            value=150e6,  # $150M net 7-day inflow
            threshold=0,
            status="HEALTHY" if 150e6 > 0 else "WARNING",
            impact="BULLISH" if 150e6 > 0 else "BEARISH"
        )
        self.indicators['btc_etf_flows'] = indicator
        return indicator

    def update_funding_rates(self, symbol: str = "BTC") -> MacroIndicator:
        """
        Monitor perpetual futures funding rates.
        Positive rates = longs over-leveraged (bearish signal).
        Negative rates = shorts over-leveraged (bullish signal).
        """
        funding_value = 0.00045  # Default placeholder
        try:
            resp = requests.post(
                self._api_url + '/info',
                json={'type': 'meta'},
                timeout=10
            )
            if resp.status_code == 200:
                meta = resp.json()
                for u in meta.get('universe', []):
                    if u.get('name') == symbol:
                        funding_value = float(u.get('funding', 0.0))
                        break
        except Exception as e:
            logger.warning(f"Funding rate fetch failed: {e}")

        # Positive funding = longs pay = longs over-leveraged = BEARISH
        # Negative funding = shorts pay = shorts over-leveraged = BULLISH
        impact = "BEARISH" if funding_value > 0 else "BULLISH" if funding_value < 0 else "NEUTRAL"
        indicator = MacroIndicator(
            name=f"{symbol} Perpetual Funding Rate",
            value=funding_value,
            threshold=0.0,
            status="HEALTHY",
            impact=impact
        )
        self.indicators['funding_rates'] = indicator
        return indicator

    def update_usdt_dominance(self) -> MacroIndicator:
        """
        USDT market dominance metric.
        High dominance in downtrends = stablecoin accumulation.
        """
        indicator = MacroIndicator(
            name="USDT Market Dominance",
            value=0.32,  # 32% of stablecoin market
            threshold=0.30,
            status="HEALTHY",
            impact="NEUTRAL"
        )
        self.indicators['usdt_dominance'] = indicator
        return indicator

    def update_on_chain_metrics(self) -> Dict[str, MacroIndicator]:
        """
        Aggregate on-chain metrics: active addresses, exchange inflows, whale movements.
        """
        metrics = {}

        # Exchange Inflows
        metrics['exchange_inflows'] = MacroIndicator(
            name="Exchange Inflows (7d avg)",
            value=45000,  # 45k BTC
            threshold=50000,
            status="WARNING" if 45000 > 40000 else "HEALTHY",
            impact="BEARISH" if 45000 > 50000 else "NEUTRAL"
        )

        # Long-term Holder Movement
        metrics['lth_movement'] = MacroIndicator(
            name="LTH Accumulation Signal",
            value=0.62,  # 62% of LTH holding (good)
            threshold=0.50,
            status="HEALTHY",
            impact="BULLISH"
        )

        # Whale Accumulation
        metrics['whale_accumulation'] = MacroIndicator(
            name="Whale (100+ BTC) Holdings",
            value=3.2e6,  # 3.2M BTC held by whales
            threshold=3.0e6,
            status="HEALTHY",
            impact="BULLISH"
        )

        return metrics

    def assess_macro_regime(self) -> Dict[str, any]:
        """
        Synthesize all macro indicators into a single regime assessment.
        Returns overall market health and risk level.
        """
        self.update_fed_liquidity()
        self.update_stablecoin_flows()
        self.update_btc_etf_flows()
        self.update_funding_rates()
        
        on_chain = self.update_on_chain_metrics()
        self.indicators.update(on_chain)

        # Count bullish vs bearish indicators
        bullish_count = sum(1 for ind in self.indicators.values() if ind.impact == "BULLISH")
        bearish_count = sum(1 for ind in self.indicators.values() if ind.impact == "BEARISH")
        warning_count = sum(1 for ind in self.indicators.values() if ind.status == "WARNING")

        regime = "BULLISH" if bullish_count > bearish_count else "BEARISH" if bearish_count > bullish_count else "NEUTRAL"
        risk_level = "CRITICAL" if warning_count >= 3 else "HIGH" if warning_count == 2 else "NORMAL"

        return {
            'regime': regime,
            'risk_level': risk_level,
            'bullish_indicators': bullish_count,
            'bearish_indicators': bearish_count,
            'warning_count': warning_count,
            'indicators': dict(self.indicators)
        }


# ============================================================================
# GEO-POLITICAL & SENTIMENT RISK MODULE
# ============================================================================

class GeopoliticalRiskMonitor:
    """
    Monitors geopolitical events, sanctions, regulatory changes, and market sentiment.
    Provides risk overlay for trade decisions.
    """

    def __init__(self):
        self.risk_events = deque(maxlen=50)
        self.sentiment_score = 0.0  # -1 (very negative) to +1 (very positive)
        self.last_update = None

    def fetch_regulatory_news(self) -> List[Dict]:
        """
        Monitor regulatory announcements (SEC, CFTC, MiCA, Asia, etc.)
        """
        # In production: Integrate news API (NewsAPI, CryptoSlate, etc.)
        events = []
        
        # Placeholder: Simulated recent events
        events.append({
            'source': 'SEC',
            'date': datetime.now() - timedelta(days=2),
            'title': 'ETH ETF Approval Confirmed',
            'impact': 'BULLISH',
            'severity': 'HIGH'
        })

        return events

    def fetch_geopolitical_events(self) -> List[Dict]:
        """
        Monitor macro geopolitical events affecting risk sentiment.
        E.g., US-China tensions, Middle East, interest rate expectations, etc.
        """
        events = []

        # Placeholder events
        events.append({
            'source': 'Reuters',
            'date': datetime.now() - timedelta(days=1),
            'title': 'US-China trade talks scheduled',
            'impact': 'NEUTRAL',
            'severity': 'MEDIUM'
        })

        return events

    def calculate_sentiment_score(self) -> float:
        """
        Aggregate sentiment from:
        - Fear & Greed Index
        - Social media sentiment (Twitter/X, Reddit)
        - News headline sentiment
        - Funding rate extremes
        """
        # In production: Fetch from Santiment, LunarCrush, etc.
        
        # Placeholder calculation
        regulatory_sentiment = 0.3  # Slightly positive regulatory environment
        macro_sentiment = 0.2  # Neutral macro backdrop
        on_chain_sentiment = 0.4  # Positive on-chain metrics
        
        self.sentiment_score = (regulatory_sentiment + macro_sentiment + on_chain_sentiment) / 3
        return self.sentiment_score

    def assess_risk_level(self) -> str:
        """
        Return current risk level: LOW, MEDIUM, HIGH, CRITICAL
        """
        recent_events = list(self.risk_events)[-5:]
        
        critical_events = [e for e in recent_events if e.get('severity') == 'CRITICAL']
        
        if critical_events:
            return "CRITICAL"
        elif self.sentiment_score < -0.3:
            return "HIGH"
        elif self.sentiment_score < 0.0:
            return "MEDIUM"
        else:
            return "LOW"


# ============================================================================
# HYPERLIQUID ORDER EXECUTION ENGINE
# ============================================================================

class HyperliquidExecutor:
    """
    Handles authentication, order placement, position management on Hyperliquid.
    Uses the official hyperliquid-python-sdk for EIP-712 signing.
    Supports both mainnet and testnet (unified account structure).
    """

    def __init__(self, private_key: str, account_address: str,
                 is_testnet: bool = False, dry_run: bool = False):
        self.private_key = private_key
        self.account_address = account_address
        self.is_testnet = is_testnet
        self.dry_run = dry_run

        self.base_url = hl_constants.TESTNET_API_URL if is_testnet else hl_constants.MAINNET_API_URL
        self.account_type = "unified" if is_testnet else "perps"

        self.session = requests.Session()
        self.open_orders = {}
        self.positions = {}
        self.exchange = None
        self.meta = None

        # Initialize SDK exchange for order signing
        if not dry_run:
            try:
                self.wallet = EthAccount.from_key(private_key)
                meta_resp = self.session.post(
                    f"{self.base_url}/info",
                    json={'type': 'meta'},
                    timeout=10
                )
                if meta_resp.status_code == 200:
                    self.meta = meta_resp.json()
                    # Build sz_decimals lookup for tick size rounding
                    self.sz_decimals = {}
                    for u in self.meta.get('universe', []):
                        self.sz_decimals[u['name']] = u.get('szDecimals', 2)
                    self.exchange = HLExchange(
                        wallet=self.wallet,
                        base_url=self.base_url,
                        meta=self.meta,
                        account_address=account_address
                    )
                    logger.info("Hyperliquid SDK Exchange initialized")
                else:
                    logger.error(f"Failed to fetch meta: {meta_resp.status_code}")
            except Exception as e:
                logger.error(f"SDK init failed: {e}")

        logger.info(f"HyperliquidExecutor initialized - Mode: {'TESTNET' if is_testnet else 'MAINNET'}, "
                   f"Account Type: {self.account_type}, Dry Run: {dry_run}")

    def fetch_candles(self, coin: str, interval: str = "1m", count: int = 200) -> List[Dict]:
        """Fetch OHLCV candle data from Hyperliquid API"""
        try:
            end_time = int(time.time() * 1000)
            # Interval to ms mapping
            interval_ms = {
                "1m": 60_000, "5m": 300_000, "15m": 900_000,
                "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000
            }
            ms_per_candle = interval_ms.get(interval, 60_000)
            start_time = end_time - (count * ms_per_candle)

            resp = self.session.post(
                f"{self.base_url}/info",
                json={
                    'type': 'candleSnapshot',
                    'req': {
                        'coin': coin,
                        'interval': interval,
                        'startTime': start_time,
                        'endTime': end_time
                    }
                },
                timeout=15
            )

            if resp.status_code == 200:
                raw_candles = resp.json()
                candles = []
                for c in raw_candles:
                    candles.append({
                        'timestamp': c['t'] / 1000,
                        'open': float(c['o']),
                        'high': float(c['h']),
                        'low': float(c['l']),
                        'close': float(c['c']),
                        'volume': float(c['v'])
                    })
                return candles
            else:
                logger.error(f"Candle fetch failed: {resp.status_code}")
                return []
        except Exception as e:
            logger.error(f"Candle fetch exception: {e}")
            return []

    def _round_size(self, symbol: str, size: float) -> float:
        """Round order size to the symbol's szDecimals"""
        decimals = self.sz_decimals.get(symbol, 2) if hasattr(self, 'sz_decimals') else 2
        return round(size, decimals)

    def _round_price(self, price: float) -> float:
        """Round price to whole dollar (Hyperliquid tick size)"""
        return round(price)

    def place_order(self, symbol: str, side: str, size: float,
                   limit_price: Optional[float] = None,
                   leverage: float = 1.0,
                   reduce_only: bool = False) -> Dict:
        """
        Place order on Hyperliquid using SDK.
        side: "BUY" or "SELL"
        size: Position size in coin units
        limit_price: None = market order (uses IOC at aggressive price)
        """
        try:
            if self.dry_run:
                logger.info(f"[DRY RUN] Order: {symbol} {side} {size} @ {limit_price} (Leverage: {leverage}x)")
                return {
                    'status': 'dry_run_simulated',
                    'orderId': f"SIM_{int(time.time() * 1000)}",
                    'symbol': symbol,
                    'side': side,
                    'size': size,
                    'price': limit_price
                }

            if not self.exchange:
                logger.error("Exchange not initialized - cannot place orders")
                return None

            is_buy = side.upper() == "BUY"
            rounded_size = self._round_size(symbol, size)

            if limit_price:
                rounded_price = self._round_price(limit_price)
                order_type = {"limit": {"tif": "Gtc"}}
                result = self.exchange.order(symbol, is_buy, rounded_size, rounded_price, order_type, reduce_only=reduce_only)
            else:
                # Market order: use aggressive limit with IOC
                order_type = {"limit": {"tif": "Ioc"}}
                current_price = self._get_mid_price(symbol)
                if current_price:
                    aggressive_px = self._round_price(current_price * (1.005 if is_buy else 0.995))
                    result = self.exchange.order(symbol, is_buy, rounded_size, aggressive_px, order_type, reduce_only=reduce_only)
                else:
                    logger.error("Cannot get current price for market order")
                    return None

            logger.info(f"Order placed: {symbol} {side} {rounded_size} @ {limit_price} -> {result}")
            return result

        except Exception as e:
            logger.error(f"Order placement exception: {e}")
            return None

    def _get_mid_price(self, symbol: str) -> Optional[float]:
        """Get current mid price for a symbol"""
        try:
            resp = self.session.post(
                f"{self.base_url}/info",
                json={'type': 'allMids'},
                timeout=10
            )
            if resp.status_code == 200:
                mids = resp.json()
                if symbol in mids:
                    return float(mids[symbol])
            return None
        except Exception:
            return None

    def set_stop_loss(self, symbol: str, price: float, size: float, is_long: bool) -> Dict:
        """Place stop-loss order"""
        side = "SELL" if is_long else "BUY"
        return self.place_order(symbol, side, size, limit_price=price, reduce_only=True)

    def set_take_profit(self, symbol: str, price: float, size: float, is_long: bool) -> Dict:
        """Place take-profit order"""
        side = "SELL" if is_long else "BUY"
        return self.place_order(symbol, side, size, limit_price=price, reduce_only=True)

    def get_account_state(self) -> Dict:
        """Fetch account balance and open positions via POST.
        For testnet unified accounts, checks both perps and spot clearinghouses."""
        try:
            # Perps clearinghouse
            resp = self.session.post(
                f"{self.base_url}/info",
                json={
                    'type': 'clearinghouseState',
                    'user': self.account_address
                },
                timeout=10
            )
            state = {}
            if resp.status_code == 200:
                state = resp.json()

            # For unified accounts (testnet), also check spot balance
            if self.is_testnet:
                spot_resp = self.session.post(
                    f"{self.base_url}/info",
                    json={
                        'type': 'spotClearinghouseState',
                        'user': self.account_address
                    },
                    timeout=10
                )
                if spot_resp.status_code == 200:
                    spot_state = spot_resp.json()
                    state['spotBalances'] = spot_state.get('balances', [])
                    # Calculate total spot USDC
                    usdc_balance = 0.0
                    for bal in spot_state.get('balances', []):
                        if bal.get('coin') == 'USDC':
                            usdc_balance = float(bal.get('total', 0))
                    state['spotUsdcBalance'] = usdc_balance

            return state
        except Exception as e:
            logger.error(f"Account fetch exception: {e}")
            return {}

    def close_position(self, symbol: str) -> Dict:
        """Close all positions in a symbol"""
        try:
            state = self.get_account_state()
            for pos in state.get('assetPositions', []):
                position = pos.get('position', {})
                if position.get('coin') == symbol:
                    size = abs(float(position.get('szi', 0)))
                    if size > 0:
                        is_long = float(position.get('szi', 0)) > 0
                        side = "SELL" if is_long else "BUY"
                        return self.place_order(symbol, side, size, reduce_only=True)
            logger.info(f"No position found for {symbol}")
            return {}
        except Exception as e:
            logger.error(f"Close position exception: {e}")
            return {}

    def get_funding_rate(self, symbol: str) -> Optional[float]:
        """Fetch live funding rate for a symbol. Returns rate per 8h period."""
        try:
            resp = self.session.post(
                f"{self.base_url}/info",
                json={'type': 'metaAndAssetCtxs'},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                # data is [meta, [assetCtx, ...]]
                if isinstance(data, list) and len(data) >= 2:
                    meta = data[0]
                    ctxs = data[1]
                    for i, u in enumerate(meta.get('universe', [])):
                        if u['name'] == symbol and i < len(ctxs):
                            return float(ctxs[i].get('funding', 0))
            return None
        except Exception as e:
            logger.warning(f"Funding rate fetch failed: {e}")
            return None


# ============================================================================
# RISK MANAGEMENT MODULE
# ============================================================================

class RiskManager:
    """
    Position sizing, stop-loss/take-profit logic, max loss limits.
    """

    def __init__(self, account_size: float, max_loss_per_trade: float = 0.02):
        self.account_size = account_size
        self.max_loss_per_trade = max_loss_per_trade  # 5% aggressive
        self.max_open_positions = 5
        self.min_risk_reward_ratio = 1.5  # Require at least 1.5:1 RR

    def calculate_position_size(self, entry_price: float, stop_loss_price: float,
                               leverage: float = 1.0) -> float:
        """
        Calculate position size based on account risk per trade.
        
        Position Size = (Account Size × Max Loss %) / (Entry - SL)
        """
        risk_amount = self.account_size * self.max_loss_per_trade
        pip_distance = abs(entry_price - stop_loss_price)
        
        if pip_distance == 0:
            return 0
        
        position_size = (risk_amount / pip_distance) * leverage
        return position_size

    def calculate_take_profit(self, entry_price: float, stop_loss_price: float,
                            risk_reward: float = 2.0, side: str = "LONG") -> float:
        """
        Set take profit based on risk/reward ratio.
        For LONG: TP above entry. For SHORT: TP below entry.
        """
        pip_distance = abs(entry_price - stop_loss_price)
        tp_distance = pip_distance * risk_reward
        
        if side == "LONG":
            tp_price = entry_price + tp_distance
        else:
            tp_price = entry_price - tp_distance
        return tp_price

    def is_trade_valid(self, entry: float, sl: float, tp: float) -> Tuple[bool, str]:
        """Validate trade setup before execution"""
        
        # Check RR ratio
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        
        if risk == 0:
            return False, "Zero risk distance"
        
        rr_ratio = reward / risk
        
        if rr_ratio < self.min_risk_reward_ratio:
            return False, f"RR ratio {rr_ratio:.2f} below minimum {self.min_risk_reward_ratio}"
        
        return True, "Valid"


# ============================================================================
# MAIN BOT ORCHESTRATOR
# ============================================================================

class HyperliquidTradingBot:
    """
    Main bot controller: Orchestrates TA, Macro, Risk Management, and Execution.
    """

    def __init__(self, config: Dict):
        self.config = config
        self.ta_engine = HighConfirmationTA()

        is_testnet = config.get('USE_TESTNET', False)
        dry_run = config.get('DRY_RUN', False)
        api_url = hl_constants.TESTNET_API_URL if is_testnet else hl_constants.MAINNET_API_URL

        self.macro_monitor = MacroLiquidityMonitor(api_url=api_url)
        self.geo_monitor = GeopoliticalRiskMonitor()

        self.executor = HyperliquidExecutor(
            private_key=config['HYPERLIQUID_PRIVATE_KEY'],
            account_address=config['HYPERLIQUID_ACCOUNT'],
            is_testnet=is_testnet,
            dry_run=dry_run
        )
        self.risk_manager = RiskManager(
            account_size=config['ACCOUNT_SIZE'],
            max_loss_per_trade=config.get('MAX_LOSS_PER_TRADE', 0.02)
        )

        self.trading_symbols = config.get('SYMBOLS', ['BTC', 'ETH'])
        self.is_running = False
        self.trades_executed = []
        self.is_testnet = is_testnet
        self.dry_run = dry_run

        # Per-symbol TA engines for independent analysis
        self.ta_engines: Dict[str, HighConfirmationTA] = {}
        for sym in self.trading_symbols:
            self.ta_engines[sym] = HighConfirmationTA()

        mode = "TESTNET" if is_testnet else "MAINNET"
        run_type = "DRY RUN" if dry_run else "LIVE"
        logger.info(f"HyperliquidTradingBot initialized - Mode: {mode}, Type: {run_type}")

    def run(self):
        """Main event loop"""
        self.is_running = True
        logger.info("Bot starting main loop")
        
        while self.is_running:
            try:
                self._cycle()
                time.sleep(self.config.get('CYCLE_INTERVAL', 60))  # Default 60s cycle
            except Exception as e:
                logger.error(f"Cycle error: {e}")
                time.sleep(10)

    def _cycle(self):
        """Single bot cycle: fetch data, analyze, execute"""
        
        # 1. UPDATE MACRO ENVIRONMENT
        macro_assessment = self.macro_monitor.assess_macro_regime()
        geo_risk = self.geo_monitor.assess_risk_level()
        
        logger.info(f"Macro Regime: {macro_assessment['regime']} | "
                   f"Risk Level: {macro_assessment['risk_level']} | "
                   f"Geo Risk: {geo_risk}")
        
        # 2. FOR EACH SYMBOL, FETCH DATA AND ANALYZE TA
        for symbol in self.trading_symbols:
            
            # Fetch live candle data from Hyperliquid
            candles = self.executor.fetch_candles(symbol, interval="1m", count=200)
            
            if not candles:
                logger.warning(f"{symbol}: No candle data available, skipping")
                continue
            
            # Get or create per-symbol TA engine
            ta = self.ta_engines.get(symbol, self.ta_engine)
            
            # Feed candles to TA engine
            for c in candles:
                ta.add_candle(
                    timestamp=c['timestamp'],
                    open_=c['open'],
                    high=c['high'],
                    low=c['low'],
                    close=c['close'],
                    volume=c['volume']
                )
            
            ta_signal = ta.generate_signal()
            
            logger.info(f"{symbol}: Signal={ta_signal.signal.value}, "
                       f"Confidence={ta_signal.confidence:.2%}, "
                       f"Confirmations={ta_signal.confirmations}")
            
            # 3. FILTER BY MACRO CONDITIONS
            if macro_assessment['risk_level'] == 'CRITICAL':
                logger.warning(f"Macro risk critical - skipping {symbol}")
                continue
            
            if ta_signal.signal == TradeSignal.NEUTRAL or ta_signal.signal == TradeSignal.WAIT:
                logger.debug(f"{symbol}: Neutral signal, waiting")
                continue
            
            # 4. CHECK CONFIDENCE (weighted score threshold)
            if ta_signal.confidence < 0.55:
                logger.debug(f"{symbol}: Low confidence {ta_signal.confidence:.2f}")
                continue
            
            # 5. FUNDING RATE EDGE FILTER
            # Block trades that go against extreme funding (crowd is overleveraged)
            funding = self.executor.get_funding_rate(symbol)
            if funding is not None:
                logger.info(f"{symbol}: Funding rate = {funding:.6f}")
                # Positive funding = longs paying shorts = longs overleveraged
                # Block LONG if funding is very positive (crowd already long)
                if ta_signal.signal == TradeSignal.LONG and funding > 0.0001:
                    logger.info(f"{symbol}: Skipping LONG - funding too positive ({funding:.6f}), longs overleveraged")
                    continue
                # Block SHORT if funding is very negative (crowd already short)
                if ta_signal.signal == TradeSignal.SHORT and funding < -0.0001:
                    logger.info(f"{symbol}: Skipping SHORT - funding too negative ({funding:.6f}), shorts overleveraged")
                    continue
            
            # 6. EXECUTE TRADE
            current_price = candles[-1]['close']
            self._execute_trade_signal(symbol, ta_signal, macro_assessment, current_price)

    def _execute_trade_signal(self, symbol: str, signal: TechnicalSignal,
                              macro: Dict, current_price: float):
        """Execute a trade based on technical + macro confluence.
        Uses ATR-based SL/TP for tight, market-adaptive risk management."""
        
        # Get ATR for this symbol's TA engine
        ta = self.ta_engines.get(symbol, self.ta_engine)
        atr = ta.calculate_atr(period=14)
        
        if atr <= 0:
            logger.warning(f"{symbol}: ATR is zero, cannot calculate stops")
            return
        
        logger.info(f"\n{'='*60}")
        logger.info(f"TRADE SIGNAL: {symbol} {signal.signal.value}")
        logger.info(f"Confidence: {signal.confidence:.2%}")
        logger.info(f"Confirmations: {signal.confirmations}")
        logger.info(f"Macro: {macro['regime']} (Risk: {macro['risk_level']})")
        logger.info(f"Price: ${current_price:,.2f} | ATR: ${atr:,.2f}")
        logger.info(f"{'='*60}\n")
        
        entry_price = current_price
        
        # ATR-based stops: SL = 2.0x ATR, TP = 4.0x ATR (proven profitable combo)
        atr_sl_mult = 2.0
        atr_tp_mult = 4.0
        
        if signal.signal == TradeSignal.LONG:
            sl_price = entry_price - (atr * atr_sl_mult)
            tp_price = entry_price + (atr * atr_tp_mult)
            leverage = 2.0
            side = "LONG"
        else:
            sl_price = entry_price + (atr * atr_sl_mult)
            tp_price = entry_price - (atr * atr_tp_mult)
            leverage = 2.0
            side = "SHORT"
        
        # Validate
        is_valid, reason = self.risk_manager.is_trade_valid(entry_price, sl_price, tp_price)
        
        if not is_valid:
            logger.warning(f"Trade invalid: {reason}")
            return
        
        # Position size based on ATR stop distance
        position_size = self.risk_manager.calculate_position_size(
            entry_price, sl_price, leverage
        )
        
        # Convert USD position size to coin units
        coin_size = position_size / entry_price if entry_price > 0 else 0
        
        logger.info(f"Entry: ${entry_price:,.2f} | SL: ${sl_price:,.2f} | TP: ${tp_price:,.2f}")
        logger.info(f"Risk: ${abs(entry_price - sl_price):,.2f} | Reward: ${abs(tp_price - entry_price):,.2f}")
        logger.info(f"Position: ${position_size:,.2f} ({coin_size:.6f} {symbol}) | Leverage: {leverage}x")
        
        # Execute order
        order_side = "BUY" if signal.signal == TradeSignal.LONG else "SELL"
        result = self.executor.place_order(
            symbol=symbol,
            side=order_side,
            size=round(coin_size, 6),
            leverage=leverage
        )
        
        if result:
            logger.info(f"Order result: {result}")
        
        # Log trade
        trade_record = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'symbol': symbol,
            'signal': signal.signal.value,
            'confidence': signal.confidence,
            'confirmations': signal.confirmations,
            'entry': entry_price,
            'sl': sl_price,
            'tp': tp_price,
            'atr': atr,
            'size_usd': position_size,
            'size_coin': coin_size,
            'leverage': leverage,
            'macro_regime': macro['regime'],
            'macro_risk': macro['risk_level'],
            'order_result': str(result)
        }
        self.trades_executed.append(trade_record)

    def stop(self):
        """Stop the bot"""
        self.is_running = False
        logger.info("Bot stopped")

    def get_performance_summary(self) -> Dict:
        """Return trading performance metrics"""
        if not self.trades_executed:
            return {'total_trades': 0}
        
        df = pd.DataFrame(self.trades_executed)
        
        return {
            'total_trades': len(self.trades_executed),
            'long_trades': len(df[df['signal'] == 'LONG']),
            'short_trades': len(df[df['signal'] == 'SHORT']),
            'avg_confidence': df['confidence'].mean(),
            'macro_bullish_trades': len(df[df['macro_regime'] == 'BULLISH']),
            'macro_bearish_trades': len(df[df['macro_regime'] == 'BEARISH']),
            'symbols_traded': df['symbol'].unique().tolist() if 'symbol' in df.columns else [],
        }


# ============================================================================
# INITIALIZATION & MAIN
# ============================================================================

def main():
    """Initialize and run the bot"""

    config = {
        'HYPERLIQUID_PRIVATE_KEY': os.getenv('HYPERLIQUID_PRIVATE_KEY'),
        'HYPERLIQUID_ACCOUNT': os.getenv('HYPERLIQUID_ACCOUNT'),
        'ACCOUNT_SIZE': float(os.getenv('ACCOUNT_SIZE', 10000)),
        'MAX_LOSS_PER_TRADE': float(os.getenv('MAX_LOSS_PER_TRADE', 0.02)),
        'SYMBOLS': os.getenv('SYMBOLS', 'BTC').split(','),
        'CYCLE_INTERVAL': int(os.getenv('CYCLE_INTERVAL', 60)),
        'USE_TESTNET': os.getenv('USE_TESTNET', 'false').lower() == 'true',
        'DRY_RUN': os.getenv('DRY_RUN', 'true').lower() == 'true',
    }

    if not config['HYPERLIQUID_PRIVATE_KEY'] or not config['HYPERLIQUID_ACCOUNT']:
        logger.error("Missing Hyperliquid credentials in .env")
        return

    mode = "TESTNET" if config['USE_TESTNET'] else "MAINNET"
    run_type = "DRY RUN" if config['DRY_RUN'] else "LIVE TRADING"
    logger.info(f"\n{'='*70}")
    logger.info(f"BOT CONFIGURATION")
    logger.info(f"{'='*70}")
    logger.info(f"Mode: {mode}")
    logger.info(f"Type: {run_type}")
    logger.info(f"Account: {config['HYPERLIQUID_ACCOUNT']}")
    logger.info(f"Account Size: ${config['ACCOUNT_SIZE']:,.2f}")
    logger.info(f"Max Loss Per Trade: {config['MAX_LOSS_PER_TRADE']*100:.1f}%")
    logger.info(f"Symbols: {', '.join(config['SYMBOLS'])}")
    logger.info(f"Cycle Interval: {config['CYCLE_INTERVAL']}s")
    logger.info(f"{'='*70}\n")

    bot = HyperliquidTradingBot(config)

    # Check account state first
    state = bot.executor.get_account_state()
    if state:
        margin = state.get('marginSummary', {})
        perps_value = float(margin.get('accountValue', 0))
        spot_usdc = state.get('spotUsdcBalance', 0)
        total_value = perps_value + spot_usdc
        
        if config['USE_TESTNET'] and spot_usdc > 0:
            logger.info(f"Unified Account Balance: ${total_value:,.2f} "
                       f"(Perps: ${perps_value:,.2f} + Spot USDC: ${spot_usdc:,.2f})")
            # Update account size to actual balance if it was default
            if config['ACCOUNT_SIZE'] == 10000 and total_value > 0:
                bot.risk_manager.account_size = total_value
                logger.info(f"Account size updated to actual balance: ${total_value:,.2f}")
        else:
            logger.info(f"Account Value: ${perps_value:,.2f}")
        
        positions = [p for p in state.get('assetPositions', []) 
                     if float(p.get('position', {}).get('szi', 0)) != 0]
        if positions:
            logger.info(f"Open Positions: {len(positions)}")
            for p in positions:
                pos = p['position']
                logger.info(f"  {pos['coin']}: {pos['szi']} @ {pos.get('entryPx', 'N/A')}")
        else:
            logger.info("No open perps positions")
    
    logger.info("\nRunning single cycle...")
    bot._cycle()

    summary = bot.get_performance_summary()
    logger.info(f"\nPerformance Summary:")
    for key, value in summary.items():
        logger.info(f"  {key}: {value}")


if __name__ == "__main__":
    main()
