"""
Hummingbot 管理器
负责生成策略配置、启动/停止 Bot、监控状态
"""
import os
import yaml
import subprocess
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

from database import get_db
from database.models import Bot, BotStatus, Tenant, ExchangeConnection, StrategyTemplate
from core.encryption import EncryptionManager


class HummingbotManager:
    """
    Hummingbot 管理器

    核心功能：
    1. 生成 Hummingbot 配置文件
    2. 生成策略脚本
    3. 启动/停止 Bot
    4. 监控 Bot 状态
    """

    def __init__(self):
        self.encryptor = EncryptionManager()

    def start_bot(self, bot_id: str) -> bool:
        """
        启动 Bot

        流程：
        1. 获取 Bot 配置
        2. 解密交易所凭证
        3. 生成 Hummingbot 配置文件
        4. 生成策略脚本
        5. 启动 Hummingbot Bot
        """
        with get_db() as db:
            bot = db.query(Bot).filter(Bot.id == bot_id).first()
            if not bot:
                raise ValueError(f"Bot {bot_id} not found")

            tenant = db.query(Tenant).filter(Tenant.id == bot.tenant_id).first()
            exchange_conn = db.query(ExchangeConnection).filter(
                ExchangeConnection.id == bot.exchange_connection_id
            ).first()

            try:
                # 1. 解密交易所凭证
                credentials = self.encryptor.decrypt_api_credentials({
                    "encrypted_api_key": exchange_conn.encrypted_api_key,
                    "encrypted_api_secret": exchange_conn.encrypted_api_secret,
                    "nonce_key": exchange_conn.nonce_key,
                    "nonce_secret": exchange_conn.nonce_secret,
                })

                # 2. 生成配置文件
                tenant_path = Path(tenant.deployment_path)

                # 生成全局配置
                self._generate_global_config(tenant_path, exchange_conn, credentials)

                # 生成策略脚本
                strategy_script = self._generate_strategy_script(bot, exchange_conn.exchange_name)
                script_path = tenant_path / "scripts" / f"{bot.id}.py"
                script_path.write_text(strategy_script)

                # 3. 启动 Bot（通过 Docker exec）
                container_name = f"{tenant.tenant_code}-hummingbot"

                # 复制脚本到容器
                subprocess.run([
                    "docker", "cp",
                    str(script_path),
                    f"{container_name}:/home/hummingbot/scripts/{bot.id}.py"
                ], check=True)

                # 启动策略
                result = subprocess.run([
                    "docker", "exec", "-d", container_name,
                    "python", f"/home/hummingbot/scripts/{bot.id}.py"
                ], capture_output=True, text=True)

                if result.returncode == 0:
                    bot.status = BotStatus.RUNNING
                    bot.started_at = datetime.utcnow()
                    bot.container_id = container_name
                    db.commit()
                    return True
                else:
                    bot.status = BotStatus.ERROR
                    bot.last_error = result.stderr
                    db.commit()
                    return False

            except Exception as e:
                bot.status = BotStatus.ERROR
                bot.last_error = str(e)
                db.commit()
                raise

    def stop_bot(self, bot_id: str) -> bool:
        """停止 Bot"""
        with get_db() as db:
            bot = db.query(Bot).filter(Bot.id == bot_id).first()
            if not bot:
                raise ValueError(f"Bot {bot_id} not found")

            tenant = db.query(Tenant).filter(Tenant.id == bot.tenant_id).first()

            try:
                # 停止 Hummingbot 策略进程
                container_name = f"{tenant.tenant_code}-hummingbot"

                # 通过文件系统发送停止信号
                stop_file = Path(tenant.deployment_path) / "scripts" / f"{bot.id}.stop"
                stop_file.write_text("STOP")

                bot.status = BotStatus.STOPPED
                bot.stopped_at = datetime.utcnow()
                db.commit()
                return True

            except Exception as e:
                bot.last_error = str(e)
                db.commit()
                raise

    def _generate_global_config(
        self,
        tenant_path: Path,
        exchange_conn: ExchangeConnection,
        credentials: dict
    ):
        """
        生成 Hummingbot 全局配置文件

        conf_global.yml 包含交易所凭证等全局设置
        """
        config_path = tenant_path / "configs" / "conf_global.yml"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        global_config = {
            # 交易所配置
            f"{exchange_conn.exchange_name}_api_key": credentials["api_key"],
            f"{exchange_conn.exchange_name}_secret_key": credentials["api_secret"],

            # 如果有 passphrase（OKX 等）
            **({f"{exchange_conn.exchange_name}_passphrase": credentials["passphrase"]}
               if "passphrase" in credentials else {}),

            # 其他全局设置
            "kill_switch_enabled": True,
            "kill_switch_rate": -0.20,  # -20% 触发紧急停止
            "telegram_enabled": False,
            "send_error_logs": False,
            "pmm_script_enabled": True,
            "gateway_enabled": False,
        }

        with config_path.open('w') as f:
            yaml.dump(global_config, f, default_flow_style=False)

    def _generate_strategy_script(self, bot: Bot, exchange: str) -> str:
        """
        生成策略执行脚本

        根据不同的策略模板生成对应的 Python 脚本
        """
        if bot.strategy_template == StrategyTemplate.GRID:
            return self._generate_grid_strategy(bot, exchange)
        elif bot.strategy_template == StrategyTemplate.DCA:
            return self._generate_dca_strategy(bot, exchange)
        elif bot.strategy_template == StrategyTemplate.SIGNAL_WEBHOOK:
            return self._generate_webhook_strategy(bot, exchange)
        else:
            raise ValueError(f"Unknown strategy template: {bot.strategy_template}")

    def _generate_grid_strategy(self, bot: Bot, exchange: str) -> str:
        """生成网格策略脚本"""
        config = bot.strategy_config

        return f'''#!/usr/bin/env python3
"""
Grid Trading Strategy - {bot.bot_name}
Generated at: {datetime.utcnow().isoformat()}
"""
import asyncio
import os
from decimal import Decimal
from typing import Dict
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase

class GridStrategy(ScriptStrategyBase):
    """
    网格交易策略

    参数：
    - exchange: {exchange}
    - trading_pair: {bot.trading_pair}
    - grid_count: {config['grid_count']}
    - lower_bound: {config['lower_bound']}
    - upper_bound: {config['upper_bound']}
    - order_amount: {config['order_amount']}
    """

    # 市场配置
    exchange = "{exchange}"
    trading_pair = "{bot.trading_pair}"

    # 网格参数
    grid_count = {config['grid_count']}
    lower_bound = Decimal("{config['lower_bound']}")
    upper_bound = Decimal("{config['upper_bound']}")
    order_amount = Decimal("{config['order_amount']}")

    # 风控参数
    max_position_usd = Decimal("{bot.risk_config.get('max_position_usd', 10000)}")
    max_loss_daily = Decimal("{bot.risk_config.get('max_loss_daily_usd', 100)}")
    circuit_breaker_enabled = {bot.risk_config.get('circuit_breaker_enabled', True)}

    # 运行状态
    markets = {{exchange: {{trading_pair}}}}
    grid_levels = []
    active_orders = {{}}
    initial_balance = None

    def on_tick(self):
        """每个时钟周期执行"""
        # 检查停止信号
        if self._should_stop():
            self.logger().info("Stop signal received, shutting down...")
            self.stop()
            return

        # 检查风控
        if self.circuit_breaker_enabled and not self._check_risk_limits():
            self.logger().warning("Risk limits breached, stopping strategy")
            self.stop()
            return

        # 初始化网格
        if not self.grid_levels:
            self._initialize_grid()

        # 维护网格订单
        self._maintain_grid_orders()

    def _initialize_grid(self):
        """初始化网格价格水平"""
        price_range = self.upper_bound - self.lower_bound
        grid_step = price_range / self.grid_count

        for i in range(self.grid_count + 1):
            price = self.lower_bound + (grid_step * i)
            self.grid_levels.append({{
                "price": price,
                "buy_order": None,
                "sell_order": None
            }})

        self.logger().info(f"Grid initialized with {{len(self.grid_levels)}} levels")
        self.logger().info(f"Price range: {{self.lower_bound}} - {{self.upper_bound}}")

    def _maintain_grid_orders(self):
        """维护网格订单"""
        # 获取当前价格
        mid_price = self.connectors[self.exchange].get_mid_price(self.trading_pair)

        if mid_price is None:
            return

        # 遍历每个网格水平
        for level in self.grid_levels:
            grid_price = level["price"]

            # 当前价格以下放买单
            if grid_price < mid_price:
                if level["buy_order"] is None or not self._is_order_active(level["buy_order"]):
                    # 下买单
                    order_id = self.buy(
                        connector_name=self.exchange,
                        trading_pair=self.trading_pair,
                        amount=self.order_amount,
                        order_type=OrderType.LIMIT,
                        price=grid_price
                    )
                    level["buy_order"] = order_id
                    self.logger().info(f"Placed buy order at {{grid_price}}")

            # 当前价格以上放卖单
            elif grid_price > mid_price:
                if level["sell_order"] is None or not self._is_order_active(level["sell_order"]):
                    # 下卖单
                    order_id = self.sell(
                        connector_name=self.exchange,
                        trading_pair=self.trading_pair,
                        amount=self.order_amount,
                        order_type=OrderType.LIMIT,
                        price=grid_price
                    )
                    level["sell_order"] = order_id
                    self.logger().info(f"Placed sell order at {{grid_price}}")

    def _is_order_active(self, order_id: str) -> bool:
        """检查订单是否仍然活跃"""
        if order_id is None:
            return False

        orders = self.get_active_orders(connector_name=self.exchange)
        return any(order.client_order_id == order_id for order in orders)

    def _check_risk_limits(self) -> bool:
        """检查风控限制"""
        # 检查仓位
        balance = self.connectors[self.exchange].get_balance(self.trading_pair.split("-")[0])
        mid_price = self.connectors[self.exchange].get_mid_price(self.trading_pair)

        if balance and mid_price:
            position_value = Decimal(str(balance)) * mid_price
            if position_value > self.max_position_usd:
                self.logger().error(f"Position {{position_value}} exceeds max {{self.max_position_usd}}")
                return False

        # 检查每日亏损（简化版，实际需要持久化）
        # TODO: 实现每日 PnL 跟踪

        return True

    def _should_stop(self) -> bool:
        """检查是否应该停止（通过文件系统信号）"""
        stop_file = Path("/home/hummingbot/scripts/{bot.id}.stop")
        return stop_file.exists()

    def format_status(self) -> str:
        """格式化状态信息"""
        return f"""
Grid Strategy Status - {bot.bot_name}
====================================
Exchange: {{self.exchange}}
Trading Pair: {{self.trading_pair}}
Grid Levels: {{len(self.grid_levels)}}
Active Orders: {{len([o for o in self.get_active_orders(self.exchange)])}}
"""

# 运行策略
if __name__ == "__main__":
    strategy = GridStrategy()
    asyncio.run(strategy.run())
'''

    def _generate_dca_strategy(self, bot: Bot, exchange: str) -> str:
        """生成 DCA（定投）策略脚本"""
        config = bot.strategy_config

        return f'''#!/usr/bin/env python3
"""
DCA (Dollar Cost Averaging) Strategy - {bot.bot_name}
"""
import asyncio
from decimal import Decimal
from datetime import datetime, timedelta
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase
from hummingbot.core.data_type.common import OrderType

class DCAStrategy(ScriptStrategyBase):
    """
    定投策略

    按固定间隔买入固定金额的资产
    """

    exchange = "{exchange}"
    trading_pair = "{bot.trading_pair}"

    # DCA 参数
    order_amount_usd = Decimal("{config['order_amount']}")
    interval_seconds = {config.get('order_interval_seconds', 3600)}
    max_orders = {config.get('max_orders', 10)}

    # 状态
    markets = {{exchange: {{trading_pair}}}}
    last_order_time = None
    order_count = 0

    def on_tick(self):
        """每个时钟周期执行"""
        if self._should_stop():
            self.stop()
            return

        # 检查是否到了下单时间
        now = datetime.utcnow()

        if self.last_order_time is None or \\
           (now - self.last_order_time).total_seconds() >= self.interval_seconds:

            # 检查是否达到最大订单数
            if self.order_count >= self.max_orders:
                self.logger().info(f"Reached max orders ({{self.max_orders}}), stopping")
                self.stop()
                return

            # 执行买入
            self._place_dca_order()
            self.last_order_time = now
            self.order_count += 1

    def _place_dca_order(self):
        """下 DCA 订单"""
        mid_price = self.connectors[self.exchange].get_mid_price(self.trading_pair)

        if mid_price:
            # 计算买入数量
            amount = self.order_amount_usd / mid_price

            self.buy(
                connector_name=self.exchange,
                trading_pair=self.trading_pair,
                amount=amount,
                order_type=OrderType.MARKET
            )

            self.logger().info(f"DCA order placed: {{amount}} at ~{{mid_price}}")

    def _should_stop(self) -> bool:
        from pathlib import Path
        return Path("/home/hummingbot/scripts/{bot.id}.stop").exists()

if __name__ == "__main__":
    strategy = DCAStrategy()
    asyncio.run(strategy.run())
'''

    def _generate_webhook_strategy(self, bot: Bot, exchange: str) -> str:
        """生成 Webhook 信号策略脚本"""
        # TODO: 实现 Webhook 策略
        return "# Webhook strategy not implemented yet"

    def get_bot_status(self, bot_id: str) -> Dict:
        """
        获取 Bot 运行状态

        从 Hummingbot 日志中提取状态信息
        """
        with get_db() as db:
            bot = db.query(Bot).filter(Bot.id == bot_id).first()
            if not bot:
                raise ValueError(f"Bot {bot_id} not found")

            tenant = db.query(Tenant).filter(Tenant.id == bot.tenant_id).first()

            # 读取最新日志
            log_path = Path(tenant.deployment_path) / "logs" / "hummingbot.log"

            if log_path.exists():
                # 解析日志获取状态
                # TODO: 实现日志解析
                pass

            return {
                "bot_id": bot_id,
                "status": bot.status.value,
                "started_at": bot.started_at.isoformat() if bot.started_at else None,
                "uptime_seconds": bot.running_time_seconds,
                "total_trades": bot.total_trades,
                "total_pnl": float(bot.total_pnl),
            }


# ==================== 使用示例 ====================

if __name__ == "__main__":
    manager = HummingbotManager()

    # 启动 Bot
    # manager.start_bot("bot-id-here")

    # 停止 Bot
    # manager.stop_bot("bot-id-here")

    # 获取状态
    # status = manager.get_bot_status("bot-id-here")
    # print(status)
