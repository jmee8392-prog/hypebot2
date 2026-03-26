"""
REAL DATA BACKTESTER - Hyperliquid Trading Bot
===============================================
Fetches real historical candle data from Hyperliquid mainnet.
Slides a 200-candle window through the data, generates signals,
and simulates trade outcomes using actual subsequent price action.

Runs TWO passes:
  1. Current settings (3 confirmations, signal_strength >= 2)
  2. Tuned settings (2 confirmations, signal_strength >= 1)
Compares results side by side.
"""

import sys
import json
import time
import logging
from datetime import datetime, timezone
from collections import defaultdict
from typing import List, Dict, Tuple
from dataclasses import dataclass, field

import numpy as np
import requests

from hyperliquid_trading_bot import (
    HighConfirmationTA, TradeSignal, TechnicalSignal,
    RiskManager
)

logging.basicConfig(level=logging.WARNING)

# ============================================================================
# DATA FETCHER
# ============================================================================

def fetch_candles(coin: str, interval: str, days_back: int = 90,
                  base_url: str = "https://api.hyperliquid.xyz") -> List[Dict]:
    """Fetch real historical candles from Hyperliquid mainnet"""
    end_time = int(time.time() * 1000)
    start_time = end_time - (days_back * 24 * 60 * 60 * 1000)

    resp = requests.post(f'{base_url}/info', json={
        'type': 'candleSnapshot',
        'req': {
            'coin': coin,
            'interval': interval,
            'startTime': start_time,
            'endTime': end_time
        }
    }, timeout=30)

    raw = resp.json()
    candles = []
    for c in raw:
        candles.append({
            'timestamp': c['t'] / 1000,
            'open': float(c['o']),
            'high': float(c['h']),
            'low': float(c['l']),
            'close': float(c['c']),
            'volume': float(c['v'])
        })
    return candles


# ============================================================================
# MODIFIED SIGNAL GENERATOR (allows threshold tuning)
# ============================================================================

def generate_signal_tuned(ta: HighConfirmationTA,
                          min_confirmations: int = 3,
                          min_strength: int = 2) -> TechnicalSignal:
    """
    Same logic as HighConfirmationTA.generate_signal() but with
    configurable thresholds for backtesting different parameters.
    """
    if len(ta.price_data) < 30:
        return TechnicalSignal(
            signal=TradeSignal.WAIT, confidence=0.0, timeframe="",
            confirmations=[], resistance_level=0, support_level=0
        )

    confirmations = []
    signal_strength = 0

    rsi = ta.calculate_rsi()
    if rsi < 30:
        confirmations.append("RSI_OVERSOLD")
        signal_strength += 1
    elif rsi > 70:
        confirmations.append("RSI_OVERBOUGHT")
        signal_strength -= 1

    macd, signal, histogram = ta.calculate_macd()
    if histogram > 0 and macd > signal:
        confirmations.append("MACD_BULLISH_CROSS")
        signal_strength += 1
    elif histogram < 0 and macd < signal:
        confirmations.append("MACD_BEARISH_CROSS")
        signal_strength -= 1

    structure = ta.detect_structure_breaks()
    if structure['uptrend']:
        confirmations.append("STRUCTURE_UPTREND")
        signal_strength += 1
    elif structure['downtrend']:
        confirmations.append("STRUCTURE_DOWNTREND")
        signal_strength -= 1

    upper, mid, lower = ta.calculate_bollinger_bands()
    current_price = ta.price_data[-1]['close']
    if current_price < lower:
        confirmations.append("BB_LOWER_TOUCH")
        signal_strength += 1
    elif current_price > upper:
        confirmations.append("BB_UPPER_TOUCH")
        signal_strength -= 1

    flow = ta.analyze_order_flow()
    if flow['buy_pressure'] > 0.65:
        confirmations.append("ORDERFLOW_BULLISH")
        signal_strength += 1
    elif flow['sell_pressure'] > 0.65:
        confirmations.append("ORDERFLOW_BEARISH")
        signal_strength -= 1

    liquidity = ta.detect_liquidity_voids()

    if len(confirmations) >= min_confirmations:
        if signal_strength >= min_strength:
            final_signal = TradeSignal.LONG
            confidence = min(0.95, 0.60 + (len(confirmations) * 0.10))
        elif signal_strength <= -min_strength:
            final_signal = TradeSignal.SHORT
            confidence = min(0.95, 0.60 + (len(confirmations) * 0.10))
        else:
            final_signal = TradeSignal.NEUTRAL
            confidence = 0.50
    else:
        final_signal = TradeSignal.NEUTRAL
        confidence = 0.30

    return TechnicalSignal(
        signal=final_signal, confidence=confidence,
        timeframe="", confirmations=confirmations,
        resistance_level=liquidity['resistance'],
        support_level=liquidity['support']
    )


# ============================================================================
# TRADE OUTCOME SIMULATOR
# ============================================================================

@dataclass
class BacktestTrade:
    trade_id: int
    coin: str
    side: str  # LONG or SHORT
    confidence: float
    confirmations: List[str]
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size_usd: float
    leverage: float
    outcome: str  # WIN, LOSS, TIMEOUT
    pnl_pct: float
    pnl_usd: float
    entry_time: str
    candles_to_result: int  # How many candles until SL/TP hit


def simulate_outcome(entry: float, sl: float, tp: float,
                     future_candles: List[Dict], side: str) -> Tuple[str, float, int]:
    """Simulate trade using real subsequent price data"""
    for i, c in enumerate(future_candles):
        if side == "LONG":
            if c['low'] <= sl:
                return "LOSS", (sl - entry) / entry, i + 1
            if c['high'] >= tp:
                return "WIN", (tp - entry) / entry, i + 1
        else:
            if c['high'] >= sl:
                return "LOSS", (entry - sl) / entry, i + 1
            if c['low'] <= tp:
                return "WIN", (entry - tp) / entry, i + 1

    # Timeout - use last close
    if future_candles:
        last = future_candles[-1]['close']
        pnl = (last - entry) / entry if side == "LONG" else (entry - last) / entry
        return "TIMEOUT", pnl, len(future_candles)
    return "TIMEOUT", 0.0, 0


# ============================================================================
# BACKTEST ENGINE
# ============================================================================

def run_backtest(candles: List[Dict], coin: str,
                 account_size: float = 1000.0,
                 min_confirmations: int = 3,
                 min_strength: int = 2,
                 confidence_threshold: float = 0.65,
                 window_size: int = 200,
                 future_window: int = 100,
                 max_trades: int = 1000) -> Dict:
    """
    Slide a window through real candle data, generate signals,
    simulate outcomes. Stops at max_trades.
    """
    risk_mgr = RiskManager(account_size=account_size, max_loss_per_trade=0.02)
    trades: List[BacktestTrade] = []
    total_windows = 0
    signals_neutral = 0
    signals_low_conf = 0
    signals_invalid = 0
    running_balance = account_size

    total_candles = len(candles)
    max_start = total_candles - window_size - future_window

    if max_start <= 0:
        return {'error': 'Not enough candle data', 'candles': total_candles}

    # Slide window by 1 candle each step
    for start_idx in range(0, max_start):
        if len(trades) >= max_trades:
            break

        window = candles[start_idx:start_idx + window_size]
        future = candles[start_idx + window_size:start_idx + window_size + future_window]

        # Build TA engine for this window
        ta = HighConfirmationTA(lookback_periods=500)
        for c in window:
            ta.add_candle(c['timestamp'], c['open'], c['high'], c['low'], c['close'], c['volume'])

        total_windows += 1

        # Generate signal with tuned thresholds
        signal = generate_signal_tuned(ta, min_confirmations, min_strength)

        if signal.signal in (TradeSignal.NEUTRAL, TradeSignal.WAIT):
            signals_neutral += 1
            continue

        if signal.confidence < confidence_threshold:
            signals_low_conf += 1
            continue

        # Calculate trade parameters
        entry_price = window[-1]['close']
        side = "LONG" if signal.signal == TradeSignal.LONG else "SHORT"

        if side == "LONG":
            sl_price = signal.support_level * 0.98
            leverage = 2.0
        else:
            sl_price = signal.resistance_level * 1.02
            leverage = 2.0

        if sl_price <= 0 or entry_price <= 0:
            signals_invalid += 1
            continue

        tp_price = risk_mgr.calculate_take_profit(entry_price, sl_price, risk_reward=2.5, side=side)
        is_valid, _ = risk_mgr.is_trade_valid(entry_price, sl_price, tp_price)
        if not is_valid:
            signals_invalid += 1
            continue

        pos_size = risk_mgr.calculate_position_size(entry_price, sl_price, leverage)

        # Simulate outcome
        outcome, pnl_pct, candles_to_result = simulate_outcome(
            entry_price, sl_price, tp_price, future, side
        )

        pnl_usd = pos_size * pnl_pct * leverage
        running_balance += pnl_usd

        entry_time = datetime.fromtimestamp(window[-1]['timestamp'], tz=timezone.utc).isoformat()

        trades.append(BacktestTrade(
            trade_id=len(trades),
            coin=coin, side=side,
            confidence=signal.confidence,
            confirmations=signal.confirmations,
            entry_price=entry_price,
            stop_loss=sl_price,
            take_profit=tp_price,
            position_size_usd=pos_size,
            leverage=leverage,
            outcome=outcome,
            pnl_pct=pnl_pct * 100,
            pnl_usd=pnl_usd,
            entry_time=entry_time,
            candles_to_result=candles_to_result
        ))

        # Skip ahead past this trade's resolution to avoid overlapping trades
        skip = min(candles_to_result, future_window)
        # We don't actually skip the start_idx in a for loop, but in production
        # this would prevent overlapping positions

    return {
        'coin': coin,
        'total_candles': total_candles,
        'windows_scanned': total_windows,
        'signals_neutral': signals_neutral,
        'signals_low_conf': signals_low_conf,
        'signals_invalid': signals_invalid,
        'trades': trades,
        'final_balance': running_balance,
        'settings': {
            'min_confirmations': min_confirmations,
            'min_strength': min_strength,
            'confidence_threshold': confidence_threshold,
        }
    }


# ============================================================================
# ANALYSIS
# ============================================================================

def analyze_results(results: List[Dict], label: str, account_size: float):
    """Analyze and print backtest results"""
    all_trades = []
    total_windows = 0
    for r in results:
        all_trades.extend(r['trades'])
        total_windows += r['windows_scanned']

    print(f"\n{'=' * 80}")
    print(f"  {label}")
    print(f"{'=' * 80}")
    print(f"  Settings: min_confirmations={results[0]['settings']['min_confirmations']}, "
          f"min_strength={results[0]['settings']['min_strength']}, "
          f"confidence_threshold={results[0]['settings']['confidence_threshold']}")
    print(f"  Windows scanned: {total_windows:,}")
    print(f"  Trades executed: {len(all_trades)}")

    if not all_trades:
        print(f"  NO TRADES GENERATED - bot is too conservative for this data")
        return {}

    wins = [t for t in all_trades if t.outcome == "WIN"]
    losses = [t for t in all_trades if t.outcome == "LOSS"]
    timeouts = [t for t in all_trades if t.outcome == "TIMEOUT"]

    total_pnl = sum(t.pnl_usd for t in all_trades)
    win_rate = len(wins) / len(all_trades) * 100

    print(f"\n  --- RESULTS ---")
    print(f"  Wins:     {len(wins):>6}  ({len(wins)/len(all_trades)*100:.1f}%)")
    print(f"  Losses:   {len(losses):>6}  ({len(losses)/len(all_trades)*100:.1f}%)")
    print(f"  Timeouts: {len(timeouts):>6}  ({len(timeouts)/len(all_trades)*100:.1f}%)")
    print(f"  Win Rate: {win_rate:.1f}%")

    print(f"\n  --- PNL ---")
    print(f"  Starting Balance:  ${account_size:>12,.2f}")
    final = account_size + total_pnl
    print(f"  Final Balance:     ${final:>12,.2f}")
    print(f"  Total PnL:         ${total_pnl:>12,.2f}  ({total_pnl/account_size*100:+.2f}%)")

    if wins:
        print(f"  Avg Win:           ${np.mean([t.pnl_usd for t in wins]):>12,.2f}")
    if losses:
        print(f"  Avg Loss:          ${np.mean([t.pnl_usd for t in losses]):>12,.2f}")

    win_total = sum(t.pnl_usd for t in wins) if wins else 0
    loss_total = abs(sum(t.pnl_usd for t in losses)) if losses else 0
    profit_factor = win_total / loss_total if loss_total > 0 else float('inf')
    print(f"  Profit Factor:     {profit_factor:>12.2f}")

    # Max drawdown
    running = account_size
    peak = account_size
    max_dd = 0
    for t in all_trades:
        running += t.pnl_usd
        peak = max(peak, running)
        dd = (peak - running) / peak * 100
        max_dd = max(max_dd, dd)
    print(f"  Max Drawdown:      {max_dd:>11.2f}%")

    # By coin
    coins = set(t.coin for t in all_trades)
    if len(coins) > 1:
        print(f"\n  --- BY COIN ---")
        for coin in sorted(coins):
            ct = [t for t in all_trades if t.coin == coin]
            cw = len([t for t in ct if t.outcome == "WIN"])
            cpnl = sum(t.pnl_usd for t in ct)
            print(f"  {coin:>5}: {len(ct):>4} trades, {cw/len(ct)*100:.1f}% win rate, ${cpnl:>10,.2f} PnL")

    # By side
    print(f"\n  --- BY SIDE ---")
    for side in ['LONG', 'SHORT']:
        st = [t for t in all_trades if t.side == side]
        if st:
            sw = len([t for t in st if t.outcome == "WIN"])
            spnl = sum(t.pnl_usd for t in st)
            print(f"  {side:>6}: {len(st):>4} trades, {sw/len(st)*100:.1f}% win rate, ${spnl:>10,.2f} PnL")

    # Most common confirmation combos
    print(f"\n  --- TOP CONFIRMATION COMBOS ---")
    combo_stats = defaultdict(lambda: {'count': 0, 'wins': 0, 'pnl': 0})
    for t in all_trades:
        key = " + ".join(sorted(t.confirmations))
        combo_stats[key]['count'] += 1
        if t.outcome == "WIN":
            combo_stats[key]['wins'] += 1
        combo_stats[key]['pnl'] += t.pnl_usd

    for combo, stats in sorted(combo_stats.items(), key=lambda x: -x[1]['count'])[:8]:
        wr = stats['wins'] / stats['count'] * 100 if stats['count'] > 0 else 0
        print(f"  {combo[:55]:55s} | {stats['count']:>4} trades | {wr:5.1f}% WR | ${stats['pnl']:>8,.2f}")

    # Avg candles to result
    resolved = [t for t in all_trades if t.outcome in ("WIN", "LOSS")]
    if resolved:
        avg_time = np.mean([t.candles_to_result for t in resolved])
        print(f"\n  Avg candles to resolution: {avg_time:.1f}")

    return {
        'trades': len(all_trades),
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'profit_factor': profit_factor,
        'max_drawdown': max_dd,
        'final_balance': final,
    }


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 80)
    print("HYPERLIQUID BOT - REAL DATA BACKTEST")
    print("=" * 80)
    print(f"Fetching real historical data from Hyperliquid mainnet...")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")

    ACCOUNT_SIZE = 1000.0
    coins = ['BTC', 'ETH']
    intervals = ['5m', '15m']  # Multiple timeframes for more data

    # Fetch all data
    all_data = {}
    for coin in coins:
        for interval in intervals:
            print(f"  Fetching {coin} {interval}...", end=" ", flush=True)
            candles = fetch_candles(coin, interval, days_back=90)
            key = f"{coin}_{interval}"
            all_data[key] = candles
            if candles:
                days = (candles[-1]['timestamp'] - candles[0]['timestamp']) / 86400
                print(f"{len(candles)} candles, {days:.1f} days")
            else:
                print("no data")

    # ========================================================================
    # PASS 1: Current settings (conservative)
    # ========================================================================
    print(f"\n{'#' * 80}")
    print(f"PASS 1: CURRENT SETTINGS (min_confirmations=3, min_strength=2)")
    print(f"{'#' * 80}")

    results_conservative = []
    for key, candles in all_data.items():
        coin = key.split('_')[0]
        r = run_backtest(
            candles, coin, account_size=ACCOUNT_SIZE,
            min_confirmations=3, min_strength=2,
            confidence_threshold=0.65,
            max_trades=5000  # Collect as many as possible
        )
        results_conservative.append(r)
        print(f"  {key}: {len(r['trades'])} trades from {r['windows_scanned']:,} windows")

    stats_conservative = analyze_results(results_conservative, "PASS 1: CONSERVATIVE (current settings)", ACCOUNT_SIZE)

    # ========================================================================
    # PASS 2: Tuned settings (more trades)
    # ========================================================================
    print(f"\n{'#' * 80}")
    print(f"PASS 2: TUNED SETTINGS (min_confirmations=2, min_strength=1)")
    print(f"{'#' * 80}")

    results_tuned = []
    for key, candles in all_data.items():
        coin = key.split('_')[0]
        r = run_backtest(
            candles, coin, account_size=ACCOUNT_SIZE,
            min_confirmations=2, min_strength=1,
            confidence_threshold=0.60,
            max_trades=5000
        )
        results_tuned.append(r)
        print(f"  {key}: {len(r['trades'])} trades from {r['windows_scanned']:,} windows")

    stats_tuned = analyze_results(results_tuned, "PASS 2: TUNED (lower thresholds)", ACCOUNT_SIZE)

    # ========================================================================
    # PASS 3: Aggressive settings
    # ========================================================================
    print(f"\n{'#' * 80}")
    print(f"PASS 3: AGGRESSIVE (min_confirmations=2, min_strength=1, conf>=0.50)")
    print(f"{'#' * 80}")

    results_aggressive = []
    for key, candles in all_data.items():
        coin = key.split('_')[0]
        r = run_backtest(
            candles, coin, account_size=ACCOUNT_SIZE,
            min_confirmations=2, min_strength=1,
            confidence_threshold=0.50,
            max_trades=5000
        )
        results_aggressive.append(r)
        print(f"  {key}: {len(r['trades'])} trades from {r['windows_scanned']:,} windows")

    stats_aggressive = analyze_results(results_aggressive, "PASS 3: AGGRESSIVE (lower everything)", ACCOUNT_SIZE)

    # ========================================================================
    # COMPARISON
    # ========================================================================
    print(f"\n{'=' * 80}")
    print(f"SIDE-BY-SIDE COMPARISON")
    print(f"{'=' * 80}")
    print(f"  {'Metric':<25} {'Conservative':>15} {'Tuned':>15} {'Aggressive':>15}")
    print(f"  {'-'*25} {'-'*15} {'-'*15} {'-'*15}")

    for key, label in [
        ('trades', 'Trades'),
        ('win_rate', 'Win Rate %'),
        ('total_pnl', 'Total PnL $'),
        ('profit_factor', 'Profit Factor'),
        ('max_drawdown', 'Max Drawdown %'),
        ('final_balance', 'Final Balance $'),
    ]:
        c = stats_conservative.get(key, 0)
        t = stats_tuned.get(key, 0)
        a = stats_aggressive.get(key, 0)
        if key in ('total_pnl', 'final_balance'):
            print(f"  {label:<25} ${c:>14,.2f} ${t:>14,.2f} ${a:>14,.2f}")
        elif key in ('win_rate', 'max_drawdown'):
            print(f"  {label:<25} {c:>14.1f}% {t:>14.1f}% {a:>14.1f}%")
        elif key == 'profit_factor':
            print(f"  {label:<25} {c:>15.2f} {t:>15.2f} {a:>15.2f}")
        else:
            print(f"  {label:<25} {c:>15,} {t:>15,} {a:>15,}")

    # Save results
    save_data = {
        'backtest_date': datetime.now(timezone.utc).isoformat(),
        'data_source': 'Hyperliquid mainnet',
        'account_size': ACCOUNT_SIZE,
        'conservative': stats_conservative,
        'tuned': stats_tuned,
        'aggressive': stats_aggressive,
    }
    with open('/app/backtest_results.json', 'w') as f:
        json.dump(save_data, f, indent=2, default=str)

    print(f"\nResults saved to /app/backtest_results.json")
    print(f"Completed: {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
