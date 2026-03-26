"""
ATR OPTIMIZATION - Find the best SL/TP multipliers for profitability.
Tests multiple ATR combos on real BTC data to find the sweet spot.
"""

import json
import time
import logging
from datetime import datetime, timezone
from typing import List, Dict, Tuple
import numpy as np
import requests

from hyperliquid_trading_bot import (
    HighConfirmationTA, TradeSignal, RiskManager
)

logging.basicConfig(level=logging.WARNING)


def fetch_candles(coin, interval, days_back=90):
    end_time = int(time.time() * 1000)
    start_time = end_time - (days_back * 24 * 60 * 60 * 1000)
    resp = requests.post('https://api.hyperliquid.xyz/info', json={
        'type': 'candleSnapshot',
        'req': {'coin': coin, 'interval': interval, 'startTime': start_time, 'endTime': end_time}
    }, timeout=30)
    return [{'timestamp': c['t']/1000, 'open': float(c['o']), 'high': float(c['h']),
             'low': float(c['l']), 'close': float(c['c']), 'volume': float(c['v'])}
            for c in resp.json()]


def simulate_outcome(entry, sl, tp, future, side):
    for i, c in enumerate(future):
        if side == "LONG":
            if c['low'] <= sl: return "LOSS", (sl - entry)/entry, i+1
            if c['high'] >= tp: return "WIN", (tp - entry)/entry, i+1
        else:
            if c['high'] >= sl: return "LOSS", (entry - sl)/entry, i+1
            if c['low'] <= tp: return "WIN", (entry - tp)/entry, i+1
    if future:
        last = future[-1]['close']
        pnl = (last - entry)/entry if side == "LONG" else (entry - last)/entry
        return "TIMEOUT", pnl, len(future)
    return "TIMEOUT", 0, 0


def test_atr_combo(candles, sl_mult, tp_mult, account_size=1000):
    risk_mgr = RiskManager(account_size=account_size, max_loss_per_trade=0.02)
    wins = 0; losses = 0; timeouts = 0; total_pnl = 0; trades = 0
    window_size = 200; future_window = 100

    for start in range(0, len(candles) - window_size - future_window):
        window = candles[start:start + window_size]
        future = candles[start + window_size:start + window_size + future_window]

        ta = HighConfirmationTA(lookback_periods=500)
        for c in window:
            ta.add_candle(c['timestamp'], c['open'], c['high'], c['low'], c['close'], c['volume'])

        signal = ta.generate_signal()
        if signal.signal in (TradeSignal.NEUTRAL, TradeSignal.WAIT):
            continue
        if signal.confidence < 0.55:
            continue

        entry = window[-1]['close']
        side = "LONG" if signal.signal == TradeSignal.LONG else "SHORT"
        atr = ta.calculate_atr(14)
        if atr <= 0: continue

        if side == "LONG":
            sl = entry - (atr * sl_mult)
            tp = entry + (atr * tp_mult)
        else:
            sl = entry + (atr * sl_mult)
            tp = entry - (atr * tp_mult)

        pos = risk_mgr.calculate_position_size(entry, sl, 2.0)
        outcome, pnl_pct, _ = simulate_outcome(entry, sl, tp, future, side)
        pnl_usd = pos * pnl_pct * 2.0
        total_pnl += pnl_usd
        trades += 1

        if outcome == "WIN": wins += 1
        elif outcome == "LOSS": losses += 1
        else: timeouts += 1

    wr = wins / trades * 100 if trades > 0 else 0
    pf = (sum(1 for _ in range(wins)) * (tp_mult/sl_mult)) / losses if losses > 0 else 0
    # Better profit factor calc
    return {
        'sl': sl_mult, 'tp': tp_mult, 'rr': tp_mult/sl_mult,
        'trades': trades, 'wins': wins, 'losses': losses, 'timeouts': timeouts,
        'win_rate': wr, 'total_pnl': total_pnl,
        'pnl_pct': total_pnl / account_size * 100
    }


def main():
    print("=" * 90)
    print("ATR MULTIPLIER OPTIMIZATION — BTC ONLY")
    print("=" * 90)

    print("Fetching BTC data...")
    btc_5m = fetch_candles('BTC', '5m', 90)
    btc_15m = fetch_candles('BTC', '15m', 90)
    print(f"  5m: {len(btc_5m)} candles | 15m: {len(btc_15m)} candles")

    combos = [
        (1.0, 1.5),  # 1.5:1 R:R (tight)
        (1.0, 2.0),  # 2:1 R:R
        (1.0, 2.5),  # 2.5:1 R:R
        (1.0, 3.0),  # 3:1 R:R
        (1.2, 2.0),  # 1.67:1
        (1.2, 2.4),  # 2:1
        (1.2, 3.0),  # 2.5:1
        (1.5, 2.0),  # 1.33:1
        (1.5, 2.5),  # 1.67:1 (current)
        (1.5, 3.0),  # 2:1
        (1.5, 3.75), # 2.5:1
        (2.0, 3.0),  # 1.5:1 (wide)
        (2.0, 4.0),  # 2:1 (wide)
    ]

    all_results = []

    print(f"\n{'SL':>5} {'TP':>5} {'R:R':>6} | {'Trades':>7} {'WR%':>7} {'Wins':>5} {'Loss':>5} {'TO':>4} | {'PnL $':>10} {'PnL%':>7}")
    print("-" * 90)

    for sl_m, tp_m in combos:
        # Run on both timeframes
        r5 = test_atr_combo(btc_5m, sl_m, tp_m)
        r15 = test_atr_combo(btc_15m, sl_m, tp_m)

        combined = {
            'sl': sl_m, 'tp': tp_m, 'rr': tp_m/sl_m,
            'trades': r5['trades'] + r15['trades'],
            'wins': r5['wins'] + r15['wins'],
            'losses': r5['losses'] + r15['losses'],
            'timeouts': r5['timeouts'] + r15['timeouts'],
            'total_pnl': r5['total_pnl'] + r15['total_pnl'],
        }
        combined['win_rate'] = combined['wins'] / combined['trades'] * 100 if combined['trades'] > 0 else 0
        combined['pnl_pct'] = combined['total_pnl'] / 1000 * 100

        all_results.append(combined)

        marker = " <<< PROFITABLE" if combined['total_pnl'] > 0 else ""
        print(f"{sl_m:>5.1f} {tp_m:>5.1f} {tp_m/sl_m:>5.1f}:1 | "
              f"{combined['trades']:>7} {combined['win_rate']:>6.1f}% {combined['wins']:>5} {combined['losses']:>5} {combined['timeouts']:>4} | "
              f"${combined['total_pnl']:>9.2f} {combined['pnl_pct']:>6.2f}%{marker}")

    # Find best
    profitable = [r for r in all_results if r['total_pnl'] > 0]
    if profitable:
        best = max(profitable, key=lambda x: x['total_pnl'])
        print(f"\n{'='*90}")
        print(f"BEST: SL={best['sl']}x ATR, TP={best['tp']}x ATR ({best['rr']:.1f}:1 R:R)")
        print(f"  {best['trades']} trades, {best['win_rate']:.1f}% WR, ${best['total_pnl']:.2f} PnL ({best['pnl_pct']:.2f}%)")
    else:
        best = min(all_results, key=lambda x: abs(x['total_pnl']))
        print(f"\n{'='*90}")
        print(f"CLOSEST TO BREAKEVEN: SL={best['sl']}x ATR, TP={best['tp']}x ATR")
        print(f"  {best['trades']} trades, {best['win_rate']:.1f}% WR, ${best['total_pnl']:.2f} PnL")

    with open('/app/atr_optimization.json', 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"\nSaved to /app/atr_optimization.json")


if __name__ == "__main__":
    main()
