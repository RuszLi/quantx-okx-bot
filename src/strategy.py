import asyncio
import logging
import time
import numpy as np
from collections import deque
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class VultureStrategy:
    def __init__(self, client, instId: str, global_trade_lock: asyncio.Lock,
                 contract_val: float, lot_sz: float, min_sz: float, initial_balance: float,
                 leverage: int = 20):
        self.client = client
        self.instId = instId
        self.global_trade_lock = global_trade_lock

        # 策略参数
        self.window_size_sec = 10
        self.long_window_size_sec = 300
        self.oi_drop_threshold = 0.001
        self.leverage = leverage

        # 合约规格 (从 instruments API 获取)
        self.contract_val = contract_val
        self.lot_sz = lot_sz
        self.min_sz = min_sz

        # 动态计算的参数
        self.trade_size: Optional[str] = None  # None = 尚未计算，首次收到价格后计算
        self.current_balance = initial_balance
        self.dynamic_vd_threshold = float('inf')
        self._last_threshold_update = 0.0

        # 内存数据结构 (Ring Buffers)
        self.trades_buffer = deque()
        self.long_trades_buffer = deque()
        self.oi_buffer = deque()

        # 状态管理
        self.position = 0  # 0: 无仓位, 1: 多头, -1: 空头
        self.entry_time = 0.0
        self.entry_price = 0.0
        self.best_bid = 0.0
        self.best_ask = 0.0
        self.has_pending_exit_order = False
        self.exit_order_time = 0.0
        self.last_ws_time = 0.0

        self.is_trading = False
        self.sl_pct = 0.02
        self.tp_pct = 0.04
        self.is_initialized = True

    def update_balance(self, new_balance: float):
        """更新余额，触发下次下单前重新计算仓位大小"""
        self.current_balance = new_balance
        self.trade_size = None

    def set_position_from_exchange(self, pos_side: str, avg_px: float):
        """启动时从交易所同步仓位，防止重启后状态不一致 (BUG 5)"""
        self.position = 1 if pos_side == "long" else -1
        self.entry_price = avg_px
        self.entry_time = time.time()
        logger.warning(f"[{self.instId}] Synced existing {pos_side} position from exchange @ {avg_px}")

    def _compute_trade_size(self, price: float) -> str:
        """按 lotSz 步进计算仓位大小，修正原来强制取整到 10 的错误 (BUG 3)"""
        if price <= 0 or self.contract_val <= 0:
            return str(self.min_sz)
        max_contracts = (self.current_balance * self.leverage * 0.95) / (price * self.contract_val)
        n_lots = int(max_contracts / self.lot_sz)
        rounded = n_lots * self.lot_sz
        result = max(self.min_sz, rounded)
        logger.info(f"[{self.instId}] Position sizing: balance={self.current_balance:.4f}, "
                    f"px={price}, ctVal={self.contract_val}, lev={self.leverage}x "
                    f"-> {result:.8g} contracts")
        return f"{result:.8g}"

    async def _watchdog(self):
        """独立守护协程：持仓超时强制平仓，防止全局锁永久锁死 (BUG 4)"""
        MAX_HOLD_SEC = 60
        while True:
            await asyncio.sleep(5)
            if self.position == 0 or self.entry_time == 0:
                continue
            hold = time.time() - self.entry_time
            if hold > MAX_HOLD_SEC and not self.is_trading:
                logger.error(f"[{self.instId}] WATCHDOG: position held {hold:.0f}s, forcing market exit")
                self.has_pending_exit_order = False
                side = "sell" if self.position == 1 else "buy"
                price = (self.best_bid if self.position == 1 else self.best_ask) or self.entry_price
                await self._execute_trade(side, price, is_exit=True, ordType="market")

    def _update_dynamic_threshold(self):
        """计算动态 VD 阈值，5 秒更新一次 (BUG 7: 原来每 tick 都算)"""
        now = time.time()
        if now - self._last_threshold_update < 5:
            return
        self._last_threshold_update = now

        if len(self.long_trades_buffer) < 50:
            return

        vols = [item[1] for item in self.long_trades_buffer]
        std_vol = np.std(vols)
        n_trades_10s = len(self.long_trades_buffer) / (self.long_window_size_sec / 10)
        window_std = std_vol * np.sqrt(max(1, n_trades_10s))
        self.dynamic_vd_threshold = max(3 * window_std, self.contract_val * 1000)

    def _clean_old_data(self, current_time: float):
        """清理超过窗口期的数据，并处理断线重连导致的数据断层"""
        # 检查是否存在数据断层 (网络断线或品种极度冷清导致超过 15 秒没有任何数据推送)
        gap = current_time - self.last_ws_time
        if self.last_ws_time > 0 and gap > 15:
            # 降低日志级别为 debug，因为对于某些山寨币，十几秒没有交易是正常的
            logger.debug(f"[{self.instId}] Data gap detected (No WS data for {gap:.1f}s). Clearing short-term buffers.")
            self.trades_buffer.clear()
            self.oi_buffer.clear()
            self.last_ws_time = current_time # 重置时间，防止连续触发
            return

        cutoff_time = current_time - self.window_size_sec
        long_cutoff_time = current_time - self.long_window_size_sec
        
        while self.trades_buffer and self.trades_buffer[0][0] < cutoff_time:
            self.trades_buffer.popleft()
            
        while self.long_trades_buffer and self.long_trades_buffer[0][0] < long_cutoff_time:
            self.long_trades_buffer.popleft()
            
        while self.oi_buffer and self.oi_buffer[0][0] < cutoff_time:
            self.oi_buffer.popleft()

    async def handle_ws_data(self, data: dict):
        """处理来自 WebSocket 的实时数据"""
        if not self.is_initialized:
            return
            
        if "arg" not in data or "data" not in data:
            return
            
        channel = data["arg"]["channel"]
        current_time = time.time()
        
        if channel == "trades":
            for trade in data["data"]:
                sz = float(trade["sz"])
                side = trade["side"]
                px = float(trade["px"])
                
                directed_vol = sz if side == "buy" else -sz
                self.trades_buffer.append((current_time, directed_vol, px))
                self.long_trades_buffer.append((current_time, directed_vol, px))
                
        elif channel == "open-interest":
            for oi_data in data["data"]:
                oi = float(oi_data["oi"])
                self.oi_buffer.append((current_time, oi))
                
        elif channel == "bbo-tbt":
            for bbo in data["data"]:
                self.best_bid = float(bbo["bids"][0][0]) if bbo["bids"] else self.best_bid
                self.best_ask = float(bbo["asks"][0][0]) if bbo["asks"] else self.best_ask
                
        self._clean_old_data(current_time)
        self.last_ws_time = current_time
        self._update_dynamic_threshold()  # 内部有 5 秒门控，直接调用即可 (BUG 7)
        await self._evaluate_signals(current_time)

    async def _evaluate_signals(self, current_time: float):
        """评估微观结构信号"""
        if self.is_trading:
            return
            
        # 如果没有仓位，寻找入场信号
        if self.position == 0:
            await self._check_entry_signals(current_time)
        # 如果有仓位，寻找出场信号 (逃顶/止损)
        else:
            await self._check_exit_signals(current_time)

    async def _check_entry_signals(self, current_time: float):
        if not self.trades_buffer or not self.oi_buffer:
            return
            
        # 如果全局锁被占用（说明当前有其他品种正在持仓或正在开仓），直接跳过入场检查
        if self.global_trade_lock.locked():
            return
            
        # 1. 计算 10 秒内的 Volume Delta
        vd = sum(item[1] for item in self.trades_buffer)
        
        # 2. 计算 10 秒内的 OI 变化率
        oldest_oi = self.oi_buffer[0][1]
        newest_oi = self.oi_buffer[-1][1]
        if oldest_oi == 0: return
        oi_change_pct = (newest_oi - oldest_oi) / oldest_oi
        
        # 3. 计算价格变化
        oldest_px = self.trades_buffer[0][2]
        newest_px = self.trades_buffer[-1][2]
        px_change_pct = (newest_px - oldest_px) / oldest_px
        
        # 首次收到价格时（或 update_balance 后），按 lotSz 步进计算仓位 (BUG 3)
        if self.trade_size is None:
            self.trade_size = self._compute_trade_size(newest_px)
        
        # 信号 A: 多头点火 (空头爆仓踩踏)
        # 增加手续费覆盖检查：瞬间涨幅必须大于 0.1% (覆盖一进一出的 Taker 成本)
        if vd > self.dynamic_vd_threshold and oi_change_pct < -self.oi_drop_threshold and px_change_pct > 0.001:
            logger.warning(f"🔥 LONG SIGNAL TRIGGERED! VD: {vd:.2f} (Thresh: {self.dynamic_vd_threshold:.2f}), OI Drop: {oi_change_pct*100:.4f}%")
            await self._execute_trade("buy", newest_px, ordType="market")
            
        # 信号 B: 空头踩踏 (多头爆仓踩踏)
        elif vd < -self.dynamic_vd_threshold and oi_change_pct < -self.oi_drop_threshold and px_change_pct < -0.001:
            logger.warning(f"🩸 SHORT SIGNAL TRIGGERED! VD: {vd:.2f} (Thresh: {-self.dynamic_vd_threshold:.2f}), OI Drop: {oi_change_pct*100:.4f}%")
            await self._execute_trade("sell", newest_px, ordType="market")

    async def _check_exit_signals(self, current_time: float):
        """
        出场逻辑优化 (降低摩擦成本)：
        1. 动量停滞 (持仓超过 10 秒)：尝试挂 Post-Only Maker 单出场。
        2. 动量反转 (VD 变号) 或 极窄止损：撤销所有挂单，直接市价 Taker 逃命。
        """
        if self.has_pending_exit_order:
            if current_time - self.exit_order_time > 5: # 5秒超时追单
                logger.warning(f"[{self.instId}] Maker exit timeout (>5s). Canceling and market closing.")
                await self.client.cancel_all_orders(self.instId)
                self.has_pending_exit_order = False
                await asyncio.sleep(0.2) # 等待撤单生效
                side = "sell" if self.position == 1 else "buy"
                current_px = self.trades_buffer[-1][2] if self.trades_buffer else self.entry_price
                await self._execute_trade(side, current_px, is_exit=True, ordType="market")
            return # 等待成交或超时
            
        hold_time = current_time - self.entry_time
        current_px = self.trades_buffer[-1][2] if self.trades_buffer else self.entry_price
        
        vd = sum(item[1] for item in self.trades_buffer)
        
        exit_reason = None
        ordType = "market"
        exit_px = ""
        
        if self.position == 1: # 多头持仓
            if vd < 0: # 动量反转，主动卖盘开始主导
                exit_reason = "Momentum Reversal (VD < 0)"
            elif hold_time > 5 and current_px <= self.entry_price: # 极窄止损
                exit_reason = "Micro-Stoploss (No follow through)"
            elif hold_time > 10 and not self.has_pending_exit_order: # 动量停滞，尝试 Maker 出场
                exit_reason = "Momentum Stalled (>10s) - Trying Maker Exit"
                ordType = "post_only"
                exit_px = str(self.best_ask) # 挂在卖一价
                
        elif self.position == -1: # 空头持仓
            if vd > 0:
                exit_reason = "Momentum Reversal (VD > 0)"
            elif hold_time > 5 and current_px >= self.entry_price:
                exit_reason = "Micro-Stoploss (No follow through)"
            elif hold_time > 10 and not self.has_pending_exit_order:
                exit_reason = "Momentum Stalled (>10s) - Trying Maker Exit"
                ordType = "post_only"
                exit_px = str(self.best_bid) # 挂在买一价
                
        if exit_reason:
            if ordType == "market" and self.has_pending_exit_order:
                # 如果之前挂了 Maker 单但没成交，现在情况紧急，先撤单
                await self.client.cancel_all_orders(self.instId)
                self.has_pending_exit_order = False
                await asyncio.sleep(0.1) # 等待撤单生效
                
            logger.warning(f"🏃 EXITING POSITION: {exit_reason}. Hold time: {hold_time:.1f}s")
            side = "sell" if self.position == 1 else "buy"
            await self._execute_trade(side, current_px, is_exit=True, ordType=ordType, px=exit_px)

    async def _execute_trade(self, side: str, price: float, is_exit: bool = False, ordType: str = "market", px: str = ""):
        self.is_trading = True

        # BUG 1: 对冲模式 posSide 规则
        # 入场: buy→long, sell→short
        # 出场: 平多(sell)→long, 平空(buy)→short  （与持仓方向一致，不是下单方向）
        if is_exit:
            posSide = "long" if self.position == 1 else "short"
        else:
            posSide = "long" if side == "buy" else "short"

        if not is_exit:
            if self.global_trade_lock.locked():
                logger.warning(f"[{self.instId}] Missed entry: global lock held by another symbol.")
                self.is_trading = False
                return
            await self.global_trade_lock.acquire()

        try:
            slTriggerPx = ""
            slOrdPx = ""
            tpTriggerPx = ""
            tpOrdPx = ""
            if not is_exit:
                if side == "buy":
                    slTriggerPx = str(round(price * (1 - self.sl_pct), 4))
                    slOrdPx = "-1"
                    tpTriggerPx = str(round(price * (1 + self.tp_pct), 4))
                    tpOrdPx = "-1"
                else:
                    slTriggerPx = str(round(price * (1 + self.sl_pct), 4))
                    slOrdPx = "-1"
                    tpTriggerPx = str(round(price * (1 - self.tp_pct), 4))
                    tpOrdPx = "-1"

            logger.info(f"[{self.instId}] Placing {ordType} {side} {self.trade_size} posSide={posSide} SL={slTriggerPx} TP={tpTriggerPx}")
            await self.client.place_order(
                self.instId, side, self.trade_size,
                ordType=ordType, px=px,
                posSide=posSide,    # BUG 1 fix
                tdMode="isolated",  # BUG 2 fix
                slTriggerPx=slTriggerPx, slOrdPx=slOrdPx,
                tpTriggerPx=tpTriggerPx, tpOrdPx=tpOrdPx,
            )

            if is_exit and ordType == "post_only":
                self.has_pending_exit_order = True
                self.exit_order_time = time.time()

            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"[{self.instId}] Error executing trade: {e}")
            self.has_pending_exit_order = False  # BUG 9: 异常时同步重置
            if not is_exit and self.global_trade_lock.locked():
                self.global_trade_lock.release()
        finally:
            self.is_trading = False

    def handle_order_error(self):
        """处理下单被交易所拒绝的情况"""
        logger.warning(f"[{self.instId}] Order rejected by exchange. Resetting state.")
        self.is_trading = False
        if self.position == 0 and self.global_trade_lock.locked():
            self.global_trade_lock.release()
        self.has_pending_exit_order = False

    async def handle_order_update(self, order: dict):
        """处理订单状态更新 (由 WebSocket orders 频道推送)"""
        state = order.get("state")
        side = order.get("side")
        ordType = order.get("ordType")
        
        if state == "filled":
            if self.position == 0: # 入场单成交
                self.position = 1 if side == "buy" else -1
                self.entry_time = time.time()
                self.entry_price = float(order.get("avgPx", 0))
                logger.info(f"[{self.instId}] 🟢 ENTRY FILLED: {side} at {self.entry_price}")
            else: # 出场单成交
                self.position = 0
                self.entry_time = 0
                self.entry_price = 0.0
                self.has_pending_exit_order = False
                if self.global_trade_lock.locked():
                    self.global_trade_lock.release()
                logger.info(f"[{self.instId}] 🔴 EXIT FILLED: {side}")
                
        elif state in ["canceled", "mmp_canceled"]:
            if self.has_pending_exit_order:
                self.has_pending_exit_order = False
                logger.info(f"[{self.instId}] Exit order canceled.")
            elif self.position == 0:
                if self.global_trade_lock.locked():
                    self.global_trade_lock.release()
                logger.info(f"[{self.instId}] Entry order canceled.")
