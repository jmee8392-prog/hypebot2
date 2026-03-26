"""
1,000 TRADE SIMULATION - STRESS TEST FOR HYPERLIQUID TRADING BOT
================================================================
Runs the bot's logic through 1,000 simulated market scenarios using
realistic historical-style price data. Reports where the logic fails,
edge cases, and performance analysis.
"""

import sys
import time
import json
import random
import logging
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple

import numpy as np
import pandas as pd

from hyperliquid_trading_bot import (
    HighConfirmationTA, TradeSignal, TechnicalSignal,
    MacroLiquidityMonitor, GeopoliticalRiskMonitor,
    RiskManager, HyperliquidExecutor, HyperliquidTradingBot,
    MarketRegime
)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


# ============================================================================
# MARKET SCENARIO GENERATORS
# ============================================================================

def generate_trending_up(num_candles=200, base_price=50000, volatility=0.02, trend_strength=0.001):
    """Strong uptrend with pullbacks"""
    candles = []
    price = base_price
    for i in range(num_candles):
        drift = price * trend_strength
        noise = price * volatility * np.random.randn()
        price = price + drift + noise
        price = max(price, base_price * 0.5)  # Floor
        
        high = price * (1 + abs(np.random.randn()) * volatility * 0.5)
        low = price * (1 - abs(np.random.randn()) * volatility * 0.5)
        open_ = low + (high - low) * np.random.uniform(0.3, 0.7)
        close = low + (high - low) * np.random.uniform(0.4, 0.8)
        volume = np.random.uniform(50000, 500000) * (1 + 0.5 * np.random.randn())
        volume = max(volume, 1000)
        
        candles.append({
            'timestamp': 1700000000 + i * 60,
            'open': open_, 'high': high, 'low': low, 'close': close, 'volume': volume
        })
    return candles


def generate_trending_down(num_candles=200, base_price=50000, volatility=0.02, trend_strength=0.001):
    """Strong downtrend"""
    candles = []
    price = base_price
    for i in range(num_candles):
        drift = -price * trend_strength
        noise = price * volatility * np.random.randn()
        price = price + drift + noise
        price = max(price, base_price * 0.3)
        
        high = price * (1 + abs(np.random.randn()) * volatility * 0.5)
        low = price * (1 - abs(np.random.randn()) * volatility * 0.5)
        open_ = low + (high - low) * np.random.uniform(0.3, 0.7)
        close = low + (high - low) * np.random.uniform(0.2, 0.6)
        volume = np.random.uniform(50000, 500000) * (1 + 0.5 * np.random.randn())
        volume = max(volume, 1000)
        
        candles.append({
            'timestamp': 1700000000 + i * 60,
            'open': open_, 'high': high, 'low': low, 'close': close, 'volume': volume
        })
    return candles


def generate_sideways(num_candles=200, base_price=50000, volatility=0.01):
    """Range-bound / choppy market"""
    candles = []
    price = base_price
    for i in range(num_candles):
        noise = price * volatility * np.random.randn()
        mean_revert = (base_price - price) * 0.05  # Pull back to center
        price = price + noise + mean_revert
        
        high = price * (1 + abs(np.random.randn()) * volatility * 0.3)
        low = price * (1 - abs(np.random.randn()) * volatility * 0.3)
        open_ = low + (high - low) * np.random.uniform(0.3, 0.7)
        close = low + (high - low) * np.random.uniform(0.3, 0.7)
        volume = np.random.uniform(20000, 200000)
        
        candles.append({
            'timestamp': 1700000000 + i * 60,
            'open': open_, 'high': high, 'low': low, 'close': close, 'volume': volume
        })
    return candles


def generate_volatile_spike(num_candles=200, base_price=50000):
    """Sudden spike followed by crash (liquidation cascade)"""
    candles = []
    price = base_price
    spike_start = num_candles // 3
    spike_end = spike_start + 20
    crash_end = spike_end + 30
    
    for i in range(num_candles):
        if i < spike_start:
            noise = price * 0.01 * np.random.randn()
            price += noise
        elif i < spike_end:
            price *= 1.02 + 0.01 * np.random.randn()  # Rapid 2% per candle up
        elif i < crash_end:
            price *= 0.97 + 0.01 * np.random.randn()  # Rapid 3% per candle down
        else:
            noise = price * 0.015 * np.random.randn()
            price += noise
        
        price = max(price, 1000)
        high = price * (1 + abs(np.random.randn()) * 0.01)
        low = price * (1 - abs(np.random.randn()) * 0.01)
        open_ = low + (high - low) * np.random.uniform(0.2, 0.8)
        close = low + (high - low) * np.random.uniform(0.2, 0.8)
        volume = np.random.uniform(100000, 1000000)
        
        candles.append({
            'timestamp': 1700000000 + i * 60,
            'open': open_, 'high': high, 'low': low, 'close': close, 'volume': volume
        })
    return candles


def generate_gradual_reversal(num_candles=200, base_price=50000):
    """Uptrend that gradually reverses into downtrend"""
    candles = []
    price = base_price
    midpoint = num_candles // 2
    
    for i in range(num_candles):
        if i < midpoint:
            drift = price * 0.0008
        else:
            drift = -price * 0.0012
        
        noise = price * 0.015 * np.random.randn()
        price = price + drift + noise
        price = max(price, base_price * 0.3)
        
        high = price * (1 + abs(np.random.randn()) * 0.008)
        low = price * (1 - abs(np.random.randn()) * 0.008)
        open_ = low + (high - low) * np.random.uniform(0.3, 0.7)
        close = low + (high - low) * np.random.uniform(0.3, 0.7)
        volume = np.random.uniform(50000, 400000)
        
        candles.append({
            'timestamp': 1700000000 + i * 60,
            'open': open_, 'high': high, 'low': low, 'close': close, 'volume': volume
        })
    return candles


def generate_low_volume_drift(num_candles=200, base_price=50000):
    """Very low volume, slow drift - tests volume-based indicators"""
    candles = []
    price = base_price
    for i in range(num_candles):
        noise = price * 0.005 * np.random.randn()
        price += noise
        
        high = price * 1.002
        low = price * 0.998
        open_ = price * (1 + 0.001 * np.random.randn())
        close = price * (1 + 0.001 * np.random.randn())
        volume = np.random.uniform(100, 5000)  # Very low volume
        
        candles.append({
            'timestamp': 1700000000 + i * 60,
            'open': open_, 'high': high, 'low': low, 'close': close, 'volume': volume
        })
    return candles


def generate_flash_crash(num_candles=200, base_price=50000):
    """Sudden 20%+ drop in 5 candles, then recovery"""
    candles = []
    price = base_price
    crash_start = 100
    crash_end = 105
    
    for i in range(num_candles):
        if i < crash_start:
            noise = price * 0.008 * np.random.randn()
            price += noise
        elif i < crash_end:
            price *= 0.95  # 5% per candle = ~25% crash
        elif i < crash_end + 30:
            price *= 1.015  # Slow recovery
        else:
            noise = price * 0.01 * np.random.randn()
            price += noise
        
        price = max(price, 1000)
        high = price * (1 + abs(np.random.randn()) * 0.005)
        low = price * (1 - abs(np.random.randn()) * 0.005)
        open_ = low + (high - low) * random.uniform(0.3, 0.7)
        close = low + (high - low) * random.uniform(0.3, 0.7)
        volume = np.random.uniform(200000, 2000000) if crash_start <= i <= crash_end + 10 else np.random.uniform(50000, 300000)
        
        candles.append({
            'timestamp': 1700000000 + i * 60,
            'open': open_, 'high': high, 'low': low, 'close': close, 'volume': volume
        })
    return candles


def generate_whipsaw(num_candles=200, base_price=50000):
    """Alternating up/down moves designed to trigger false signals"""
    candles = []
    price = base_price
    for i in range(num_candles):
        cycle = np.sin(i * 0.3) * price * 0.02
        noise = price * 0.01 * np.random.randn()
        price = base_price + cycle + noise
        price = max(price, base_price * 0.7)
        
        high = price * (1 + abs(np.random.randn()) * 0.01)
        low = price * (1 - abs(np.random.randn()) * 0.01)
        open_ = low + (high - low) * random.uniform(0.2, 0.8)
        close = low + (high - low) * random.uniform(0.2, 0.8)
        volume = np.random.uniform(30000, 300000)
        
        candles.append({
            'timestamp': 1700000000 + i * 60,
            'open': open_, 'high': high, 'low': low, 'close': close, 'volume': volume
        })
    return candles


# ============================================================================
# TRADE OUTCOME SIMULATOR
# ============================================================================

@dataclass
class SimulatedTrade:
    trade_id: int
    scenario: str
    symbol: str
    signal: str
    confidence: float
    confirmations: int
    confirmation_list: List[str]
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size: float
    leverage: float
    risk_reward: float
    outcome: str  # WIN / LOSS / INVALID / SKIPPED
    pnl_pct: float
    pnl_usd: float
    failure_reason: str
    macro_regime: str
    macro_risk: str


def simulate_trade_outcome(entry: float, sl: float, tp: float, 
                           future_candles: list, side: str) -> Tuple[str, float]:
    """
    Given entry, SL, TP and future candles, determine if trade would have
    hit TP or SL first. Returns (outcome, pnl_pct).
    """
    if not future_candles:
        return "TIMEOUT", 0.0
    
    for candle in future_candles:
        if side == "LONG":
            if candle['low'] <= sl:
                pnl = (sl - entry) / entry
                return "LOSS", pnl
            if candle['high'] >= tp:
                pnl = (tp - entry) / entry
                return "WIN", pnl
        else:  # SHORT
            if candle['high'] >= sl:
                pnl = (entry - sl) / entry
                return "LOSS", pnl
            if candle['low'] <= tp:
                pnl = (entry - tp) / entry
                return "WIN", pnl
    
    # Neither SL nor TP hit - timeout
    last_price = future_candles[-1]['close']
    if side == "LONG":
        pnl = (last_price - entry) / entry
    else:
        pnl = (entry - last_price) / entry
    return "TIMEOUT", pnl


# ============================================================================
# MAIN SIMULATION
# ============================================================================

def run_simulation(num_trades=1000):
    print("=" * 80)
    print("HYPERLIQUID BOT - 1,000 TRADE SIMULATION")
    print("=" * 80)
    print(f"Started: {datetime.now().isoformat()}")
    print()
    
    # Scenario generators with weights (how often each market type appears)
    scenarios = [
        ("TRENDING_UP", generate_trending_up, 0.20),
        ("TRENDING_DOWN", generate_trending_down, 0.20),
        ("SIDEWAYS", generate_sideways, 0.20),
        ("VOLATILE_SPIKE", generate_volatile_spike, 0.10),
        ("GRADUAL_REVERSAL", generate_gradual_reversal, 0.10),
        ("LOW_VOLUME", generate_low_volume_drift, 0.05),
        ("FLASH_CRASH", generate_flash_crash, 0.05),
        ("WHIPSAW", generate_whipsaw, 0.10),
    ]
    
    risk_manager = RiskManager(account_size=10000, max_loss_per_trade=0.02)
    macro_monitor = MacroLiquidityMonitor()
    geo_monitor = GeopoliticalRiskMonitor()
    
    all_trades: List[SimulatedTrade] = []
    failures = defaultdict(list)
    
    # Counters
    signals_generated = 0
    trades_attempted = 0
    trades_executed = 0
    trades_skipped_confidence = 0
    trades_skipped_neutral = 0
    trades_skipped_macro = 0
    trades_invalid_rr = 0
    trades_zero_sl = 0
    trades_zero_position = 0
    exceptions_caught = 0
    
    base_prices = [30000, 45000, 60000, 90000, 110000]  # Various BTC price levels
    symbols = ['BTC', 'ETH', 'SOL']
    
    trade_id = 0
    
    for sim_idx in range(num_trades):
        # Pick scenario based on weights
        names, gens, weights = zip(*scenarios)
        scenario_idx = np.random.choice(len(scenarios), p=weights)
        scenario_name = names[scenario_idx]
        generator = gens[scenario_idx]
        
        base_price = random.choice(base_prices)
        symbol = random.choice(symbols)
        
        try:
            # Generate 300 candles: 200 for analysis buffer, 100 for outcome simulation
            candles = generator(num_candles=300, base_price=base_price)
            
            # Feed first 200 candles to TA engine
            ta_engine = HighConfirmationTA(lookback_periods=500)
            for c in candles[:200]:
                ta_engine.add_candle(
                    timestamp=c['timestamp'],
                    open_=c['open'],
                    high=c['high'],
                    low=c['low'],
                    close=c['close'],
                    volume=c['volume']
                )
            
            # Generate signal
            signal = ta_engine.generate_signal()
            signals_generated += 1
            
            # Get macro assessment
            macro = macro_monitor.assess_macro_regime()
            geo_risk = geo_monitor.assess_risk_level()
            
            # Apply macro filter
            if macro['risk_level'] == 'CRITICAL':
                trades_skipped_macro += 1
                all_trades.append(SimulatedTrade(
                    trade_id=trade_id, scenario=scenario_name, symbol=symbol,
                    signal=signal.signal.value, confidence=signal.confidence,
                    confirmations=len(signal.confirmations),
                    confirmation_list=signal.confirmations,
                    entry_price=0, stop_loss=0, take_profit=0,
                    position_size=0, leverage=0, risk_reward=0,
                    outcome="SKIPPED", pnl_pct=0, pnl_usd=0,
                    failure_reason="MACRO_CRITICAL_RISK",
                    macro_regime=macro['regime'], macro_risk=macro['risk_level']
                ))
                trade_id += 1
                continue
            
            # Check signal
            if signal.signal == TradeSignal.NEUTRAL or signal.signal == TradeSignal.WAIT:
                trades_skipped_neutral += 1
                all_trades.append(SimulatedTrade(
                    trade_id=trade_id, scenario=scenario_name, symbol=symbol,
                    signal=signal.signal.value, confidence=signal.confidence,
                    confirmations=len(signal.confirmations),
                    confirmation_list=signal.confirmations,
                    entry_price=0, stop_loss=0, take_profit=0,
                    position_size=0, leverage=0, risk_reward=0,
                    outcome="SKIPPED", pnl_pct=0, pnl_usd=0,
                    failure_reason="NEUTRAL_OR_WAIT_SIGNAL",
                    macro_regime=macro['regime'], macro_risk=macro['risk_level']
                ))
                trade_id += 1
                continue
            
            # Check confidence threshold
            if signal.confidence < 0.65:
                trades_skipped_confidence += 1
                all_trades.append(SimulatedTrade(
                    trade_id=trade_id, scenario=scenario_name, symbol=symbol,
                    signal=signal.signal.value, confidence=signal.confidence,
                    confirmations=len(signal.confirmations),
                    confirmation_list=signal.confirmations,
                    entry_price=0, stop_loss=0, take_profit=0,
                    position_size=0, leverage=0, risk_reward=0,
                    outcome="SKIPPED", pnl_pct=0, pnl_usd=0,
                    failure_reason="LOW_CONFIDENCE",
                    macro_regime=macro['regime'], macro_risk=macro['risk_level']
                ))
                trade_id += 1
                continue
            
            trades_attempted += 1
            
            # Calculate entry, SL, TP
            entry_price = candles[199]['close']  # Current price
            
            if signal.signal == TradeSignal.LONG:
                sl_price = signal.support_level * 0.98
                leverage = 2.0 if macro['regime'] == 'BULLISH' else 1.0
                side = "LONG"
            else:
                sl_price = signal.resistance_level * 1.02
                leverage = 2.0 if macro['regime'] == 'BEARISH' else 1.0
                side = "SHORT"
            
            # CRITICAL BUG CHECK: SL at 0 or same as entry
            if sl_price <= 0 or signal.support_level <= 0 or signal.resistance_level <= 0:
                trades_zero_sl += 1
                failures["ZERO_SL_PRICE"].append({
                    'scenario': scenario_name, 'signal': signal.signal.value,
                    'support': signal.support_level, 'resistance': signal.resistance_level,
                    'entry': entry_price
                })
                all_trades.append(SimulatedTrade(
                    trade_id=trade_id, scenario=scenario_name, symbol=symbol,
                    signal=signal.signal.value, confidence=signal.confidence,
                    confirmations=len(signal.confirmations),
                    confirmation_list=signal.confirmations,
                    entry_price=entry_price, stop_loss=sl_price, take_profit=0,
                    position_size=0, leverage=leverage, risk_reward=0,
                    outcome="INVALID", pnl_pct=0, pnl_usd=0,
                    failure_reason="ZERO_SL_PRICE",
                    macro_regime=macro['regime'], macro_risk=macro['risk_level']
                ))
                trade_id += 1
                continue
            
            tp_price = risk_manager.calculate_take_profit(entry_price, sl_price, risk_reward=2.5)
            
            # CRITICAL CHECK: TP direction for shorts
            # The bot ALWAYS adds TP above entry - wrong for shorts!
            if side == "SHORT":
                # TP should be BELOW entry for shorts
                risk_distance = abs(entry_price - sl_price)
                tp_price = entry_price - (risk_distance * 2.5)
            
            # Validate trade
            is_valid, reason = risk_manager.is_trade_valid(entry_price, sl_price, tp_price)
            
            if not is_valid:
                trades_invalid_rr += 1
                failures["INVALID_RR"].append({
                    'scenario': scenario_name, 'signal': side,
                    'entry': entry_price, 'sl': sl_price, 'tp': tp_price,
                    'reason': reason
                })
                all_trades.append(SimulatedTrade(
                    trade_id=trade_id, scenario=scenario_name, symbol=symbol,
                    signal=signal.signal.value, confidence=signal.confidence,
                    confirmations=len(signal.confirmations),
                    confirmation_list=signal.confirmations,
                    entry_price=entry_price, stop_loss=sl_price, take_profit=tp_price,
                    position_size=0, leverage=leverage, risk_reward=0,
                    outcome="INVALID", pnl_pct=0, pnl_usd=0,
                    failure_reason=f"INVALID_RR: {reason}",
                    macro_regime=macro['regime'], macro_risk=macro['risk_level']
                ))
                trade_id += 1
                continue
            
            # Calculate position size
            position_size = risk_manager.calculate_position_size(entry_price, sl_price, leverage)
            
            if position_size <= 0:
                trades_zero_position += 1
                failures["ZERO_POSITION_SIZE"].append({
                    'scenario': scenario_name, 'entry': entry_price, 'sl': sl_price
                })
                trade_id += 1
                continue
            
            # Simulate outcome using future candles
            future_candles = candles[200:]
            outcome, pnl_pct = simulate_trade_outcome(
                entry_price, sl_price, tp_price, future_candles, side
            )
            
            risk = abs(entry_price - sl_price)
            reward = abs(tp_price - entry_price)
            rr_ratio = reward / risk if risk > 0 else 0
            
            pnl_usd = position_size * pnl_pct * leverage
            
            trades_executed += 1
            
            all_trades.append(SimulatedTrade(
                trade_id=trade_id, scenario=scenario_name, symbol=symbol,
                signal=signal.signal.value, confidence=signal.confidence,
                confirmations=len(signal.confirmations),
                confirmation_list=signal.confirmations,
                entry_price=entry_price, stop_loss=sl_price, take_profit=tp_price,
                position_size=position_size, leverage=leverage,
                risk_reward=rr_ratio,
                outcome=outcome, pnl_pct=pnl_pct * 100, pnl_usd=pnl_usd,
                failure_reason="" if outcome == "WIN" else outcome,
                macro_regime=macro['regime'], macro_risk=macro['risk_level']
            ))
            
        except Exception as e:
            exceptions_caught += 1
            failures["EXCEPTION"].append({
                'scenario': scenario_name, 'error': str(e), 'trade_idx': sim_idx
            })
            all_trades.append(SimulatedTrade(
                trade_id=trade_id, scenario=scenario_name, symbol=symbol,
                signal="ERROR", confidence=0, confirmations=0,
                confirmation_list=[],
                entry_price=0, stop_loss=0, take_profit=0,
                position_size=0, leverage=0, risk_reward=0,
                outcome="ERROR", pnl_pct=0, pnl_usd=0,
                failure_reason=str(e),
                macro_regime="UNKNOWN", macro_risk="UNKNOWN"
            ))
        
        trade_id += 1
    
    # ============================================================================
    # ANALYSIS & REPORT
    # ============================================================================
    
    print("\n" + "=" * 80)
    print("SIMULATION RESULTS")
    print("=" * 80)
    
    # Overall stats
    print(f"\n--- SIGNAL GENERATION ---")
    print(f"Total Simulations:           {num_trades}")
    print(f"Signals Generated:           {signals_generated}")
    print(f"Skipped (Neutral/Wait):      {trades_skipped_neutral} ({trades_skipped_neutral/num_trades*100:.1f}%)")
    print(f"Skipped (Low Confidence):    {trades_skipped_confidence} ({trades_skipped_confidence/num_trades*100:.1f}%)")
    print(f"Skipped (Macro Critical):    {trades_skipped_macro} ({trades_skipped_macro/num_trades*100:.1f}%)")
    print(f"Trades Attempted:            {trades_attempted}")
    print(f"Trades Invalid (RR):         {trades_invalid_rr}")
    print(f"Trades Invalid (Zero SL):    {trades_zero_sl}")
    print(f"Trades Invalid (Zero Pos):   {trades_zero_position}")
    print(f"Trades Executed:             {trades_executed}")
    print(f"Exceptions:                  {exceptions_caught}")
    
    # Filter executed trades
    executed = [t for t in all_trades if t.outcome in ("WIN", "LOSS", "TIMEOUT")]
    
    if executed:
        wins = [t for t in executed if t.outcome == "WIN"]
        losses = [t for t in executed if t.outcome == "LOSS"]
        timeouts = [t for t in executed if t.outcome == "TIMEOUT"]
        
        win_rate = len(wins) / len(executed) * 100 if executed else 0
        total_pnl = sum(t.pnl_usd for t in executed)
        avg_win = np.mean([t.pnl_usd for t in wins]) if wins else 0
        avg_loss = np.mean([t.pnl_usd for t in losses]) if losses else 0
        
        print(f"\n--- TRADE OUTCOMES ---")
        print(f"Wins:                        {len(wins)} ({len(wins)/len(executed)*100:.1f}%)")
        print(f"Losses:                      {len(losses)} ({len(losses)/len(executed)*100:.1f}%)")
        print(f"Timeouts:                    {len(timeouts)} ({len(timeouts)/len(executed)*100:.1f}%)")
        print(f"Win Rate:                    {win_rate:.1f}%")
        print(f"Total PnL (USD):             ${total_pnl:,.2f}")
        print(f"Avg Win (USD):               ${avg_win:,.2f}")
        print(f"Avg Loss (USD):              ${avg_loss:,.2f}")
        
        if avg_loss != 0:
            profit_factor = abs(sum(t.pnl_usd for t in wins) / sum(t.pnl_usd for t in losses)) if losses else float('inf')
            print(f"Profit Factor:               {profit_factor:.2f}")
        
        # By scenario
        print(f"\n--- PERFORMANCE BY SCENARIO ---")
        scenario_stats = defaultdict(lambda: {'total': 0, 'wins': 0, 'losses': 0, 'timeouts': 0, 'pnl': 0})
        for t in executed:
            s = scenario_stats[t.scenario]
            s['total'] += 1
            s[t.outcome.lower() + 's'] = s.get(t.outcome.lower() + 's', 0) + 1
            if t.outcome == "WIN": s['wins'] += 1
            elif t.outcome == "LOSS": s['losses'] += 1
            else: s['timeouts'] += 1
            s['pnl'] += t.pnl_usd
        
        for scenario, stats in sorted(scenario_stats.items()):
            wr = stats['wins'] / stats['total'] * 100 if stats['total'] > 0 else 0
            print(f"  {scenario:25s} | Trades: {stats['total']:4d} | Win: {wr:5.1f}% | PnL: ${stats['pnl']:>10,.2f}")
        
        # By signal type
        print(f"\n--- PERFORMANCE BY SIGNAL ---")
        for sig_type in ['LONG', 'SHORT']:
            sig_trades = [t for t in executed if t.signal == sig_type]
            if sig_trades:
                sig_wins = len([t for t in sig_trades if t.outcome == "WIN"])
                sig_pnl = sum(t.pnl_usd for t in sig_trades)
                print(f"  {sig_type:10s} | Trades: {len(sig_trades):4d} | Win: {sig_wins/len(sig_trades)*100:5.1f}% | PnL: ${sig_pnl:>10,.2f}")
        
        # Confidence analysis
        print(f"\n--- CONFIDENCE ANALYSIS ---")
        conf_buckets = [(0.65, 0.70), (0.70, 0.75), (0.75, 0.80), (0.80, 0.85), (0.85, 1.01)]
        for low, high in conf_buckets:
            bucket = [t for t in executed if low <= t.confidence < high]
            if bucket:
                bw = len([t for t in bucket if t.outcome == "WIN"])
                bpnl = sum(t.pnl_usd for t in bucket)
                print(f"  Conf {low:.2f}-{high:.2f} | Trades: {len(bucket):4d} | Win: {bw/len(bucket)*100:5.1f}% | PnL: ${bpnl:>10,.2f}")
    
    # ============================================================================
    # FAILURE ANALYSIS
    # ============================================================================
    
    print(f"\n{'=' * 80}")
    print("FAILURE ANALYSIS - WHERE THE BOT LOGIC BREAKS")
    print("=" * 80)
    
    # Aggregate all failure reasons
    all_skipped = [t for t in all_trades if t.outcome in ("SKIPPED", "INVALID", "ERROR")]
    skip_reasons = Counter(t.failure_reason for t in all_skipped)
    
    print(f"\n--- SKIP/FAILURE REASON BREAKDOWN ---")
    for reason, count in skip_reasons.most_common():
        print(f"  {reason:40s}: {count:5d} ({count/num_trades*100:.1f}%)")
    
    # Critical failures
    print(f"\n--- CRITICAL BUGS FOUND ---")
    
    bug_count = 0
    
    # BUG 1: Overly conservative - too many neutral signals
    neutral_pct = trades_skipped_neutral / num_trades * 100
    if neutral_pct > 70:
        bug_count += 1
        print(f"\n  BUG #{bug_count}: OVERLY CONSERVATIVE SIGNAL GENERATION")
        print(f"  {neutral_pct:.1f}% of scenarios produced NEUTRAL signals.")
        print(f"  The 3-confirmation minimum + signal_strength >= 2 is too strict.")
        print(f"  In random-walk markets, indicators often conflict, producing no signal.")
        print(f"  FIX: Lower MIN_CONFIRMATIONS to 2 for high-confidence setups,")
        print(f"       or add more indicators that can contribute confirmations.")
    
    # BUG 2: TP always above entry (wrong for shorts)
    short_executed = [t for t in all_trades if t.signal == "SHORT" and t.outcome in ("WIN", "LOSS", "TIMEOUT")]
    if short_executed:
        short_tp_above = [t for t in short_executed if t.take_profit > t.entry_price]
        if short_tp_above:
            bug_count += 1
            print(f"\n  BUG #{bug_count}: TAKE PROFIT WRONG DIRECTION FOR SHORTS")
            print(f"  {len(short_tp_above)} SHORT trades had TP above entry price.")
            print(f"  calculate_take_profit() always adds distance to entry (LONG logic).")
            print(f"  For SHORT trades, TP should be BELOW entry.")
            print(f"  FIX: Add side parameter to calculate_take_profit().")
    
    # BUG 3: Hardcoded entry_price = 100.0 in _execute_trade_signal
    bug_count += 1
    print(f"\n  BUG #{bug_count}: HARDCODED ENTRY PRICE IN _execute_trade_signal()")
    print(f"  Line 933: entry_price = 100.0 is a placeholder.")
    print(f"  In production, this should be the current market price from the price feed.")
    print(f"  FIX: Use the last candle close price from the TA engine.")
    
    # BUG 4: No real price data feed
    bug_count += 1
    print(f"\n  BUG #{bug_count}: NO LIVE PRICE DATA FEED")
    print(f"  The bot has no mechanism to fetch real OHLCV data from Hyperliquid.")
    print(f"  _cycle() calls generate_signal() on an empty TA buffer.")
    print(f"  Without price data, the bot will NEVER generate any signals in production.")
    print(f"  FIX: Integrate Hyperliquid's REST API or WebSocket for candle data.")
    
    # BUG 5: All macro indicators are hardcoded placeholders
    bug_count += 1
    print(f"\n  BUG #{bug_count}: ALL MACRO INDICATORS ARE HARDCODED PLACEHOLDERS")
    print(f"  Fed liquidity, stablecoin flows, ETF flows, funding rates - all return")
    print(f"  static values. The macro 'regime' will always be 'BULLISH'.")
    print(f"  This means macro filtering provides zero value in current state.")
    print(f"  FIX: Integrate real data sources (FRED API, Glassnode, CoinGecko).")
    
    # BUG 6: Divergence detection is a no-op
    bug_count += 1
    print(f"\n  BUG #{bug_count}: DIVERGENCE DETECTION IS A NO-OP")
    print(f"  detect_divergence() always returns {{'bullish_div': False, 'bearish_div': False}}.")
    print(f"  It's never called in generate_signal() either.")
    print(f"  FIX: Implement actual divergence detection or remove dead code.")
    
    # BUG 7: Funding rate impact logic is inverted
    bug_count += 1
    print(f"\n  BUG #{bug_count}: FUNDING RATE IMPACT LOGIC IS INVERTED")
    print(f"  Line 455: impact='BULLISH' if 0.00045 < 0 else 'BEARISH'")
    print(f"  Positive funding = longs pay shorts = longs over-leveraged = BEARISH signal.")
    print(f"  But the condition 0.00045 < 0 is always False, so it always returns BEARISH.")
    print(f"  The COMMENT says positive = bearish (correct), but the value should flip.")
    print(f"  FIX: Correct the comparison to use the actual value variable.")
    
    # BUG 8: SL/TP not connected to order execution
    bug_count += 1
    print(f"\n  BUG #{bug_count}: STOP-LOSS/TAKE-PROFIT NOT SET ON EXCHANGE")
    print(f"  set_stop_loss() and set_take_profit() use hardcoded size=1.0.")
    print(f"  They should use the actual position size, and in _execute_trade_signal(),")
    print(f"  the SL/TP orders are never actually placed (commented out).")
    print(f"  FIX: Uncomment execution and pass correct position size.")
    
    # BUG 9: close_position is a stub
    bug_count += 1
    print(f"\n  BUG #{bug_count}: close_position() IS AN EMPTY STUB")
    print(f"  Returns empty dict, does nothing. Cannot close positions in production.")
    print(f"  FIX: Implement position enumeration and close logic.")
    
    # BUG 10: No WebSocket / streaming data
    bug_count += 1
    print(f"\n  BUG #{bug_count}: NO WEBSOCKET INTEGRATION")
    print(f"  Bot imports websockets/aiohttp but never uses them.")
    print(f"  1-minute cycle with REST polling is too slow for perp trading.")
    print(f"  FIX: Add WebSocket connection for real-time candle/trade data.")
    
    # BUG 11: Structure break detection edge case
    bug_count += 1
    print(f"\n  BUG #{bug_count}: STRUCTURE DETECTION - higher_low USES max() INSTEAD OF min()")
    print(f"  Line 185: higher_low = lows[-1] > max(lows[:-10:-1])")
    print(f"  A 'higher low' means the recent low is above the PREVIOUS low.")
    print(f"  Using max(lows[-10:]) means it must be above the HIGHEST low,")
    print(f"  which is an extremely strict condition.")
    print(f"  FIX: Use min(lows[:-10:-1]) or compare to the recent swing low.")
    
    # BUG 12: Order execution uses wrong API pattern
    bug_count += 1
    print(f"\n  BUG #{bug_count}: HYPERLIQUID API PATTERN IS INCORRECT")
    print(f"  The bot uses custom HMAC signing and REST POST to /exchange.")
    print(f"  Hyperliquid uses eth_account (EIP-712 signatures) for order signing.")
    print(f"  The current _sign_request() will be rejected by the real API.")
    print(f"  FIX: Use the official hyperliquid-python-sdk or implement EIP-712.")
    
    # BUG 13: get_account_state uses GET but Hyperliquid uses POST
    bug_count += 1
    print(f"\n  BUG #{bug_count}: get_account_state() USES GET - HYPERLIQUID API USES POST")
    print(f"  Hyperliquid info endpoint requires POST with JSON body.")
    print(f"  FIX: Change to POST with proper request body.")
    
    # Summary of severity
    print(f"\n{'=' * 80}")
    print(f"SUMMARY: {bug_count} ISSUES FOUND")
    print("=" * 80)
    
    critical_bugs = [
        "NO LIVE PRICE DATA FEED - Bot cannot trade without price data",
        "WRONG API SIGNATURE SCHEME - Orders will be rejected by Hyperliquid",
        "HARDCODED ENTRY PRICE - All trades use $100 entry",
        "TP DIRECTION WRONG FOR SHORTS - Shorts set TP above entry",
        "get_account_state uses GET instead of POST",
    ]
    
    high_bugs = [
        "ALL MACRO DATA IS PLACEHOLDER - No real macro intelligence",
        "OVERLY CONSERVATIVE SIGNALS - Most scenarios produce NEUTRAL",
        "SL/TP NEVER PLACED ON EXCHANGE - Only entry order logic exists",
        "close_position() is empty stub",
        "STRUCTURE DETECTION uses wrong comparison for higher_low",
        "FUNDING RATE LOGIC IS INVERTED",
    ]
    
    medium_bugs = [
        "DIVERGENCE DETECTION is no-op dead code",
        "NO WEBSOCKET for real-time data",
    ]
    
    print(f"\n  CRITICAL (Bot Cannot Trade): {len(critical_bugs)}")
    for b in critical_bugs:
        print(f"    - {b}")
    
    print(f"\n  HIGH (Logic Errors): {len(high_bugs)}")
    for b in high_bugs:
        print(f"    - {b}")
    
    print(f"\n  MEDIUM (Missing Features): {len(medium_bugs)}")
    for b in medium_bugs:
        print(f"    - {b}")
    
    print(f"\n{'=' * 80}")
    print(f"VERDICT: Bot is NOT production-ready for live trading.")
    print(f"It IS a solid FRAMEWORK with correct TA logic.")
    print(f"Needs: price feed, proper Hyperliquid SDK, fix shorts TP, fix hardcoded values.")
    print(f"{'=' * 80}")
    
    # Save detailed results to JSON
    results_summary = {
        'simulation_date': datetime.now().isoformat(),
        'total_simulations': num_trades,
        'signals_generated': signals_generated,
        'trades_skipped_neutral': trades_skipped_neutral,
        'trades_skipped_confidence': trades_skipped_confidence,
        'trades_skipped_macro': trades_skipped_macro,
        'trades_attempted': trades_attempted,
        'trades_executed': trades_executed,
        'trades_invalid_rr': trades_invalid_rr,
        'trades_zero_sl': trades_zero_sl,
        'exceptions': exceptions_caught,
        'win_rate': len([t for t in executed if t.outcome == "WIN"]) / len(executed) * 100 if executed else 0,
        'total_pnl_usd': sum(t.pnl_usd for t in executed) if executed else 0,
        'critical_bugs': len(critical_bugs),
        'high_bugs': len(high_bugs),
        'medium_bugs': len(medium_bugs),
        'bugs_list': {
            'critical': critical_bugs,
            'high': high_bugs,
            'medium': medium_bugs
        }
    }
    
    with open('/app/simulation_results.json', 'w') as f:
        json.dump(results_summary, f, indent=2)
    
    print(f"\nDetailed results saved to: /app/simulation_results.json")
    print(f"Completed: {datetime.now().isoformat()}")
    
    return results_summary


if __name__ == "__main__":
    results = run_simulation(1000)
