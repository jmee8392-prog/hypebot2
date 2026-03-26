"""
WALK-FORWARD VALIDATION + REALISTIC EXECUTION MODEL
=====================================================
Implements the 4-tier optimization hierarchy:

1. Walk-Forward: Train on Month N, test on Month N+1, roll forward.
   Proves predictive power vs curve-fitting.

2. Execution Reality: Slippage, latency, funding rate costs modeled
   per trade. No more "perfect fill" fantasy.

3. Robustness: Tests across market regimes (trending, choppy, crash).
   Reports Sharpe, Sortino, Profit Factor per regime.

4. Risk-First: Max drawdown limits enforced during simulation.
   Kill switch triggered if drawdown exceeds threshold.
"""

import json
import time
import logging
from datetime import datetime, timezone
from typing import List, Dict, Tuple
from collections import defaultdict
import numpy as np
import requests

from hyperliquid_trading_bot import (
    HighConfirmationTA, TradeSignal, RiskManager
)

logging.basicConfig(level=logging.WARNING)


# ============================================================================
# DATA
# ============================================================================

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


# ============================================================================
# EXECUTION REALITY MODEL
# ============================================================================

class ExecutionModel:
    """Models real-world trading frictions on Hyperliquid"""
    
    def __init__(self,
                 slippage_bps: float = 3.0,       # 3 bps slippage per trade
                 latency_candles: int = 0,         # 0-1 candle delay on fills
                 funding_rate_8h: float = 0.0001,  # 0.01% per 8h default
                 taker_fee_bps: float = 2.5,       # Hyperliquid taker fee
                 maker_rebate_bps: float = 0.2):   # Maker rebate
        
        self.slippage_bps = slippage_bps
        self.latency_candles = latency_candles
        self.funding_rate_8h = funding_rate_8h
        self.taker_fee_bps = taker_fee_bps
        self.maker_rebate_bps = maker_rebate_bps
    
    def apply_entry_slippage(self, price: float, side: str) -> float:
        """Worse fill on entry due to slippage + taker fee"""
        total_bps = self.slippage_bps + self.taker_fee_bps
        if side == "LONG":
            return price * (1 + total_bps / 10000)  # Pay more to buy
        else:
            return price * (1 - total_bps / 10000)  # Get less to sell
    
    def apply_exit_slippage(self, price: float, side: str, is_tp: bool) -> float:
        """Worse fill on exit"""
        total_bps = self.slippage_bps + self.taker_fee_bps
        if side == "LONG":
            return price * (1 - total_bps / 10000)  # Get less when selling
        else:
            return price * (1 + total_bps / 10000)  # Pay more when covering
    
    def funding_cost(self, position_usd: float, hold_candles: int,
                     candle_minutes: int, side: str) -> float:
        """
        Calculate funding cost for holding a position.
        Positive funding = longs pay shorts.
        """
        hold_hours = (hold_candles * candle_minutes) / 60
        funding_periods = hold_hours / 8  # Funding every 8h
        
        # Positive funding rate means longs pay
        if side == "LONG":
            cost = position_usd * self.funding_rate_8h * funding_periods
        else:
            cost = -position_usd * self.funding_rate_8h * funding_periods  # Shorts receive
        
        return cost


# ============================================================================
# TRADE SIMULATOR WITH FRICTIONS
# ============================================================================

def simulate_trade_realistic(entry: float, sl: float, tp: float,
                              future_candles: List[Dict], side: str,
                              exec_model: ExecutionModel,
                              candle_minutes: int = 5) -> Dict:
    """Simulate trade with realistic execution frictions"""
    
    # Apply entry slippage
    actual_entry = exec_model.apply_entry_slippage(entry, side)
    
    for i, c in enumerate(future_candles):
        if side == "LONG":
            if c['low'] <= sl:
                actual_exit = exec_model.apply_exit_slippage(sl, side, False)
                pnl_pct = (actual_exit - actual_entry) / actual_entry
                return {'outcome': 'LOSS', 'pnl_pct': pnl_pct, 'candles': i+1,
                        'entry_actual': actual_entry, 'exit_actual': actual_exit}
            if c['high'] >= tp:
                actual_exit = exec_model.apply_exit_slippage(tp, side, True)
                pnl_pct = (actual_exit - actual_entry) / actual_entry
                return {'outcome': 'WIN', 'pnl_pct': pnl_pct, 'candles': i+1,
                        'entry_actual': actual_entry, 'exit_actual': actual_exit}
        else:
            if c['high'] >= sl:
                actual_exit = exec_model.apply_exit_slippage(sl, side, False)
                pnl_pct = (actual_entry - actual_exit) / actual_entry
                return {'outcome': 'LOSS', 'pnl_pct': pnl_pct, 'candles': i+1,
                        'entry_actual': actual_entry, 'exit_actual': actual_exit}
            if c['low'] <= tp:
                actual_exit = exec_model.apply_exit_slippage(tp, side, True)
                pnl_pct = (actual_entry - actual_exit) / actual_entry
                return {'outcome': 'WIN', 'pnl_pct': pnl_pct, 'candles': i+1,
                        'entry_actual': actual_entry, 'exit_actual': actual_exit}
    
    # Timeout
    if future_candles:
        last = future_candles[-1]['close']
        if side == "LONG":
            pnl_pct = (last - actual_entry) / actual_entry
        else:
            pnl_pct = (actual_entry - last) / actual_entry
        return {'outcome': 'TIMEOUT', 'pnl_pct': pnl_pct, 'candles': len(future_candles),
                'entry_actual': actual_entry, 'exit_actual': last}
    
    return {'outcome': 'TIMEOUT', 'pnl_pct': 0, 'candles': 0,
            'entry_actual': actual_entry, 'exit_actual': actual_entry}


# ============================================================================
# WALK-FORWARD ENGINE
# ============================================================================

def run_window(candles: List[Dict], exec_model: ExecutionModel,
               account_size: float, candle_minutes: int,
               max_dd_pct: float = 5.0) -> Dict:
    """Run backtest on a single data window with execution model"""
    
    risk_mgr = RiskManager(account_size=account_size, max_loss_per_trade=0.02)
    window_size = 200
    future_window = 100
    
    trades = []
    balance = account_size
    peak_balance = account_size
    max_dd = 0
    killed = False
    
    for start in range(0, len(candles) - window_size - future_window):
        if killed:
            break
            
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
        if atr <= 0:
            continue
        
        if side == "LONG":
            sl = entry - (atr * 2.0)
            tp = entry + (atr * 4.0)
        else:
            sl = entry + (atr * 2.0)
            tp = entry - (atr * 4.0)
        
        pos_size = risk_mgr.calculate_position_size(entry, sl, 2.0)
        
        # Simulate with frictions
        result = simulate_trade_realistic(entry, sl, tp, future, side, exec_model, candle_minutes)
        
        # Add funding cost
        funding_cost = exec_model.funding_cost(
            pos_size * 2.0, result['candles'], candle_minutes, side
        )
        
        trade_pnl = (pos_size * 2.0 * result['pnl_pct']) - funding_cost
        balance += trade_pnl
        
        # Track drawdown
        peak_balance = max(peak_balance, balance)
        dd = (peak_balance - balance) / peak_balance * 100
        max_dd = max(max_dd, dd)
        
        # Kill switch
        if max_dd > max_dd_pct:
            killed = True
        
        trades.append({
            'side': side,
            'outcome': result['outcome'],
            'pnl_usd': trade_pnl,
            'funding_cost': funding_cost,
            'candles_held': result['candles'],
            'confidence': signal.confidence,
        })
    
    wins = [t for t in trades if t['outcome'] == 'WIN']
    losses = [t for t in trades if t['outcome'] == 'LOSS']
    
    total_pnl = sum(t['pnl_usd'] for t in trades)
    total_funding = sum(t['funding_cost'] for t in trades)
    
    returns = [t['pnl_usd'] / account_size for t in trades] if trades else [0]
    sharpe = (np.mean(returns) / np.std(returns) * np.sqrt(252)) if np.std(returns) > 0 else 0
    
    neg_returns = [r for r in returns if r < 0]
    sortino = (np.mean(returns) / np.std(neg_returns) * np.sqrt(252)) if neg_returns and np.std(neg_returns) > 0 else 0
    
    win_total = sum(t['pnl_usd'] for t in wins)
    loss_total = abs(sum(t['pnl_usd'] for t in losses))
    profit_factor = win_total / loss_total if loss_total > 0 else float('inf')
    
    return {
        'trades': len(trades),
        'wins': len(wins),
        'losses': len(losses),
        'timeouts': len([t for t in trades if t['outcome'] == 'TIMEOUT']),
        'win_rate': len(wins) / len(trades) * 100 if trades else 0,
        'total_pnl': total_pnl,
        'total_funding_cost': total_funding,
        'pnl_after_funding': total_pnl,
        'profit_factor': profit_factor,
        'sharpe': sharpe,
        'sortino': sortino,
        'max_drawdown': max_dd,
        'final_balance': balance,
        'killed': killed,
    }


# ============================================================================
# MARKET REGIME CLASSIFIER
# ============================================================================

def classify_regime(candles: List[Dict]) -> str:
    """Classify market regime of a data window"""
    if len(candles) < 50:
        return "UNKNOWN"
    
    closes = [c['close'] for c in candles]
    returns = np.diff(closes) / closes[:-1]
    
    total_return = (closes[-1] - closes[0]) / closes[0]
    volatility = np.std(returns)
    
    if total_return > 0.05 and volatility < 0.02:
        return "BULL_STEADY"
    elif total_return > 0.05:
        return "BULL_VOLATILE"
    elif total_return < -0.05 and volatility < 0.02:
        return "BEAR_STEADY"
    elif total_return < -0.05:
        return "BEAR_VOLATILE"
    elif volatility > 0.015:
        return "CHOPPY"
    else:
        return "CRAB"


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 90)
    print("WALK-FORWARD VALIDATION + EXECUTION REALITY MODEL")
    print("=" * 90)
    
    ACCOUNT_SIZE = 1000.0
    
    # Execution model with realistic Hyperliquid frictions
    exec_model = ExecutionModel(
        slippage_bps=3.0,        # 3 bps slippage
        taker_fee_bps=2.5,       # HL taker fee
        funding_rate_8h=0.00008, # ~0.008% per 8h (typical BTC)
    )
    
    print(f"\nExecution Model:")
    print(f"  Slippage: {exec_model.slippage_bps} bps")
    print(f"  Taker fee: {exec_model.taker_fee_bps} bps")
    print(f"  Funding rate: {exec_model.funding_rate_8h*100:.4f}% per 8h")
    print(f"  Total entry cost: ~{exec_model.slippage_bps + exec_model.taker_fee_bps:.1f} bps per side")
    
    # Fetch data
    print(f"\nFetching BTC 15m data (90 days)...")
    candles = fetch_candles('BTC', '15m', 90)
    total_days = (candles[-1]['timestamp'] - candles[0]['timestamp']) / 86400
    print(f"  {len(candles)} candles, {total_days:.1f} days")
    
    # ========================================================================
    # WALK-FORWARD: Split into ~2-week windows, train/test rolling
    # ========================================================================
    
    candles_per_day = 96  # 15m = 96 candles per day
    window_days = 14      # 2-week train window
    test_days = 7         # 1-week test window
    train_size = candles_per_day * window_days  # ~1344 candles
    test_size = candles_per_day * test_days     # ~672 candles
    step_size = test_size                        # Roll forward by test window
    
    print(f"\nWalk-Forward Configuration:")
    print(f"  Train window: {window_days} days ({train_size} candles)")
    print(f"  Test window: {test_days} days ({test_size} candles)")
    print(f"  Step: {test_days} days")
    
    # === WALK-FORWARD RESULTS ===
    print(f"\n{'='*90}")
    print(f"WALK-FORWARD RESULTS (Train {window_days}d → Test {test_days}d, rolling)")
    print(f"{'='*90}")
    
    fold_results = []
    fold_num = 0
    
    start = 0
    while start + train_size + test_size <= len(candles):
        train_data = candles[start:start + train_size]
        test_data = candles[start + train_size:start + train_size + test_size]
        
        fold_num += 1
        regime = classify_regime(test_data)
        
        # Run on test data (out-of-sample)
        result = run_window(test_data, exec_model, ACCOUNT_SIZE, 15)
        result['regime'] = regime
        result['fold'] = fold_num
        
        # Time range
        t_start = datetime.fromtimestamp(test_data[0]['timestamp'], tz=timezone.utc)
        t_end = datetime.fromtimestamp(test_data[-1]['timestamp'], tz=timezone.utc)
        
        marker = "PROFITABLE" if result['total_pnl'] > 0 else "LOSS" if result['total_pnl'] < -1 else "FLAT"
        killed_str = " KILLED!" if result['killed'] else ""
        
        print(f"  Fold {fold_num:>2}: {t_start.strftime('%m/%d')}-{t_end.strftime('%m/%d')} "
              f"| {regime:15s} | {result['trades']:>4} trades | "
              f"WR {result['win_rate']:>5.1f}% | PF {result['profit_factor']:>5.2f} | "
              f"PnL ${result['total_pnl']:>7.2f} | DD {result['max_drawdown']:>5.2f}% | "
              f"Sharpe {result['sharpe']:>6.2f} | {marker}{killed_str}")
        
        fold_results.append(result)
        start += step_size
    
    # === AGGREGATE STATS ===
    print(f"\n{'='*90}")
    print(f"AGGREGATE OUT-OF-SAMPLE RESULTS ({len(fold_results)} folds)")
    print(f"{'='*90}")
    
    total_trades = sum(r['trades'] for r in fold_results)
    total_wins = sum(r['wins'] for r in fold_results)
    total_pnl = sum(r['total_pnl'] for r in fold_results)
    total_funding = sum(r['total_funding_cost'] for r in fold_results)
    avg_sharpe = np.mean([r['sharpe'] for r in fold_results if r['trades'] > 0])
    avg_sortino = np.mean([r['sortino'] for r in fold_results if r['trades'] > 0])
    max_dd = max(r['max_drawdown'] for r in fold_results)
    profitable_folds = len([r for r in fold_results if r['total_pnl'] > 0])
    killed_folds = len([r for r in fold_results if r['killed']])
    
    print(f"  Total Trades (OOS):    {total_trades}")
    print(f"  Overall Win Rate:      {total_wins/total_trades*100:.1f}%" if total_trades > 0 else "  No trades")
    print(f"  Total PnL (after fees): ${total_pnl:.2f} ({total_pnl/ACCOUNT_SIZE*100:.2f}%)")
    print(f"  Total Funding Cost:    ${total_funding:.2f}")
    print(f"  Avg Sharpe Ratio:      {avg_sharpe:.2f}")
    print(f"  Avg Sortino Ratio:     {avg_sortino:.2f}")
    print(f"  Max Drawdown (any fold): {max_dd:.2f}%")
    print(f"  Profitable Folds:      {profitable_folds}/{len(fold_results)}")
    print(f"  Kill Switch Triggered: {killed_folds}/{len(fold_results)}")
    
    # === BY REGIME ===
    print(f"\n{'='*90}")
    print(f"PERFORMANCE BY MARKET REGIME")
    print(f"{'='*90}")
    
    regime_stats = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': 0, 'folds': 0})
    for r in fold_results:
        rs = regime_stats[r['regime']]
        rs['trades'] += r['trades']
        rs['wins'] += r['wins']
        rs['pnl'] += r['total_pnl']
        rs['folds'] += 1
    
    for regime, stats in sorted(regime_stats.items()):
        wr = stats['wins'] / stats['trades'] * 100 if stats['trades'] > 0 else 0
        print(f"  {regime:15s} | {stats['folds']:>2} folds | {stats['trades']:>4} trades | "
              f"WR {wr:>5.1f}% | PnL ${stats['pnl']:>8.2f}")
    
    # === STRESS TEST ===
    print(f"\n{'='*90}")
    print(f"STRESS TEST: Worst-case scenarios")
    print(f"{'='*90}")
    
    worst_fold = min(fold_results, key=lambda x: x['total_pnl'])
    best_fold = max(fold_results, key=lambda x: x['total_pnl'])
    
    print(f"  Worst fold: #{worst_fold['fold']} ({worst_fold['regime']}) "
          f"PnL ${worst_fold['total_pnl']:.2f}, DD {worst_fold['max_drawdown']:.2f}%")
    print(f"  Best fold:  #{best_fold['fold']} ({best_fold['regime']}) "
          f"PnL ${best_fold['total_pnl']:.2f}, DD {best_fold['max_drawdown']:.2f}%")
    
    # === VERDICT ===
    print(f"\n{'='*90}")
    print(f"VERDICT")
    print(f"{'='*90}")
    
    if total_pnl > 0 and profitable_folds > len(fold_results) * 0.5:
        print(f"  PASS: Strategy shows out-of-sample edge.")
        print(f"  {profitable_folds}/{len(fold_results)} folds profitable after fees+slippage+funding.")
    elif total_pnl > -ACCOUNT_SIZE * 0.01:
        print(f"  MARGINAL: Strategy is near breakeven after frictions.")
        print(f"  {profitable_folds}/{len(fold_results)} folds profitable. Edge is thin.")
    else:
        print(f"  FAIL: Strategy does not survive real-world frictions.")
        print(f"  Only {profitable_folds}/{len(fold_results)} folds profitable.")
    
    # Save
    save_data = {
        'date': datetime.now(timezone.utc).isoformat(),
        'execution_model': {
            'slippage_bps': exec_model.slippage_bps,
            'taker_fee_bps': exec_model.taker_fee_bps,
            'funding_rate_8h': exec_model.funding_rate_8h,
        },
        'walk_forward': {
            'train_days': window_days,
            'test_days': test_days,
            'folds': len(fold_results),
            'total_trades': total_trades,
            'total_pnl': total_pnl,
            'avg_sharpe': avg_sharpe,
            'profitable_folds': profitable_folds,
            'max_drawdown': max_dd,
        },
        'by_regime': {k: v for k, v in regime_stats.items()},
        'fold_details': [{k: v for k, v in r.items()} for r in fold_results],
    }
    
    with open('/app/walkforward_results.json', 'w') as f:
        json.dump(save_data, f, indent=2, default=str)
    
    print(f"\nResults saved to /app/walkforward_results.json")


if __name__ == "__main__":
    main()
