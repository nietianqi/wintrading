"""
告警和通知系统
支持邮件和 Telegram 通知
"""
import os
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from collections import defaultdict

from database import get_db
from database.models import Alert, AlertSeverity, User, Bot, Tenant


class NotificationManager:
    """
    通知管理器

    功能：
    1. 发送邮件通知
    2. 发送 Telegram 通知
    3. 告警去重（同类告警 5 分钟内只发一次）
    4. 批量通知
    """

    def __init__(self):
        # 邮件配置
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.from_email = os.getenv("FROM_EMAIL", self.smtp_user)

        # Telegram 配置
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_api_url = f"https://api.telegram.org/bot{self.telegram_bot_token}"

        # 去重缓存（生产环境应使用 Redis）
        self._dedup_cache = defaultdict(datetime)

    def create_alert(
        self,
        user_id: str,
        title: str,
        message: str,
        severity: AlertSeverity,
        alert_type: str,
        tenant_id: Optional[str] = None,
        bot_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        send_notification: bool = True,
    ) -> Alert:
        """
        创建告警

        Args:
            user_id: 用户 ID
            title: 告警标题
            message: 告警消息
            severity: 告警级别
            alert_type: 告警类型
            tenant_id: 租户 ID（可选）
            bot_id: Bot ID（可选）
            metadata: 额外信息（可选）
            send_notification: 是否发送通知

        Returns:
            Alert 对象
        """
        with get_db() as db:
            # 检查去重
            dedup_key = f"{user_id}:{alert_type}:{bot_id or tenant_id or 'global'}"
            last_alert_time = self._dedup_cache.get(dedup_key)

            # 5 分钟内相同告警不重复发送
            if last_alert_time and datetime.utcnow() - last_alert_time < timedelta(minutes=5):
                print(f"⚠️  Alert deduplicated: {alert_type}")
                return None

            # 创建告警记录
            alert = Alert(
                user_id=user_id,
                tenant_id=tenant_id,
                bot_id=bot_id,
                severity=severity,
                title=title,
                message=message,
                alert_type=alert_type,
                metadata=metadata or {},
                dedup_key=dedup_key,
            )

            db.add(alert)
            db.commit()
            db.refresh(alert)

            # 更新去重缓存
            self._dedup_cache[dedup_key] = datetime.utcnow()

            # 发送通知
            if send_notification:
                user = db.query(User).filter(User.id == user_id).first()
                if user:
                    self.send_notification(user, alert)

            return alert

    def send_notification(self, user: User, alert: Alert):
        """
        发送通知

        根据用户偏好选择通知渠道
        """
        notification_channels = []

        # 邮件通知
        if user.notification_email:
            success = self.send_email_notification(user, alert)
            if success:
                notification_channels.append("email")

        # Telegram 通知
        if user.notification_telegram and user.telegram_chat_id:
            success = self.send_telegram_notification(user, alert)
            if success:
                notification_channels.append("telegram")

        # 更新告警状态
        with get_db() as db:
            alert.is_sent = len(notification_channels) > 0
            alert.sent_at = datetime.utcnow()
            alert.notification_channels = notification_channels
            db.commit()

    def send_email_notification(self, user: User, alert: Alert) -> bool:
        """
        发送邮件通知

        Returns:
            是否成功
        """
        if not self.smtp_user or not self.smtp_password:
            print("⚠️  Email not configured")
            return False

        try:
            # 创建邮件
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[{alert.severity.value.upper()}] {alert.title}"
            msg["From"] = self.from_email
            msg["To"] = user.email

            # HTML 邮件内容
            html_content = self._generate_email_html(user, alert)
            html_part = MIMEText(html_content, "html")
            msg.attach(html_part)

            # 发送邮件
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            print(f"✓ Email sent to {user.email}")
            return True

        except Exception as e:
            print(f"✗ Failed to send email: {e}")
            return False

    def send_telegram_notification(self, user: User, alert: Alert) -> bool:
        """
        发送 Telegram 通知

        Returns:
            是否成功
        """
        if not self.telegram_bot_token:
            print("⚠️  Telegram not configured")
            return False

        try:
            # 生成 Telegram 消息
            text = self._generate_telegram_message(user, alert)

            # 发送消息
            url = f"{self.telegram_api_url}/sendMessage"
            payload = {
                "chat_id": user.telegram_chat_id,
                "text": text,
                "parse_mode": "Markdown",
            }

            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()

            print(f"✓ Telegram message sent to {user.telegram_chat_id}")
            return True

        except Exception as e:
            print(f"✗ Failed to send Telegram message: {e}")
            return False

    def _generate_email_html(self, user: User, alert: Alert) -> str:
        """生成邮件 HTML 内容"""
        severity_colors = {
            AlertSeverity.INFO: "#17a2b8",
            AlertSeverity.WARNING: "#ffc107",
            AlertSeverity.ERROR: "#dc3545",
            AlertSeverity.CRITICAL: "#6f42c1",
        }

        color = severity_colors.get(alert.severity, "#6c757d")

        # 获取 Dashboard 链接
        dashboard_url = "#"
        if alert.tenant_id:
            with get_db() as db:
                tenant = db.query(Tenant).filter(Tenant.id == alert.tenant_id).first()
                if tenant:
                    dashboard_url = tenant.dashboard_url

        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: {color}; color: white; padding: 20px; border-radius: 5px 5px 0 0; }}
        .content {{ background: #f9f9f9; padding: 20px; border: 1px solid #ddd; border-top: none; }}
        .footer {{ background: #f1f1f1; padding: 15px; text-align: center; font-size: 12px; color: #666; }}
        .button {{ display: inline-block; padding: 10px 20px; background: {color}; color: white; text-decoration: none; border-radius: 5px; }}
        .metadata {{ background: white; padding: 10px; margin-top: 10px; border-left: 3px solid {color}; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>🚨 {alert.title}</h2>
            <p>Severity: {alert.severity.value.upper()}</p>
        </div>
        <div class="content">
            <p>Hi {user.full_name or user.username},</p>
            <p>{alert.message}</p>

            <div class="metadata">
                <strong>Details:</strong><br>
                Type: {alert.alert_type}<br>
                Time: {alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}<br>
            </div>

            <p style="margin-top: 20px;">
                <a href="{dashboard_url}" class="button">Open Dashboard</a>
            </p>
        </div>
        <div class="footer">
            <p>Hummingbot SaaS Platform | <a href="#">Manage Notifications</a></p>
        </div>
    </div>
</body>
</html>
"""

    def _generate_telegram_message(self, user: User, alert: Alert) -> str:
        """生成 Telegram 消息"""
        severity_emoji = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.ERROR: "❌",
            AlertSeverity.CRITICAL: "🚨",
        }

        emoji = severity_emoji.get(alert.severity, "📢")

        message = f"""
{emoji} *{alert.title}*

{alert.message}

📊 *Details*
• Type: `{alert.alert_type}`
• Severity: *{alert.severity.value.upper()}*
• Time: {alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}
"""

        # 添加 Bot 信息
        if alert.bot_id:
            with get_db() as db:
                bot = db.query(Bot).filter(Bot.id == alert.bot_id).first()
                if bot:
                    message += f"\n• Bot: `{bot.bot_name}`"

        return message


# ==================== 预定义告警类型 ====================

class AlertTemplates:
    """告警模板"""

    @staticmethod
    def bot_stopped(bot_name: str, reason: str = "Unknown") -> Dict:
        """Bot 停止告警"""
        return {
            "title": f"Bot Stopped: {bot_name}",
            "message": f"Your bot '{bot_name}' has stopped. Reason: {reason}",
            "severity": AlertSeverity.WARNING,
            "alert_type": "bot_stopped",
        }

    @staticmethod
    def bot_error(bot_name: str, error_message: str) -> Dict:
        """Bot 错误告警"""
        return {
            "title": f"Bot Error: {bot_name}",
            "message": f"Your bot '{bot_name}' encountered an error: {error_message}",
            "severity": AlertSeverity.ERROR,
            "alert_type": "bot_error",
        }

    @staticmethod
    def exchange_disconnected(exchange_name: str) -> Dict:
        """交易所断线告警"""
        return {
            "title": f"Exchange Disconnected: {exchange_name}",
            "message": f"Connection to {exchange_name} was lost. Please check your API credentials.",
            "severity": AlertSeverity.ERROR,
            "alert_type": "exchange_disconnected",
        }

    @staticmethod
    def order_failed(bot_name: str, trading_pair: str, reason: str) -> Dict:
        """下单失败告警"""
        return {
            "title": f"Order Failed: {bot_name}",
            "message": f"Failed to place order for {trading_pair}. Reason: {reason}",
            "severity": AlertSeverity.WARNING,
            "alert_type": "order_failed",
        }

    @staticmethod
    def circuit_breaker_triggered(bot_name: str, reason: str) -> Dict:
        """熔断触发告警"""
        return {
            "title": f"Circuit Breaker Triggered: {bot_name}",
            "message": f"Bot '{bot_name}' has been stopped by circuit breaker. Reason: {reason}",
            "severity": AlertSeverity.CRITICAL,
            "alert_type": "circuit_breaker_triggered",
        }

    @staticmethod
    def subscription_expiring(days_left: int) -> Dict:
        """订阅即将到期告警"""
        return {
            "title": "Subscription Expiring Soon",
            "message": f"Your subscription will expire in {days_left} days. Please renew to avoid service interruption.",
            "severity": AlertSeverity.WARNING,
            "alert_type": "subscription_expiring",
        }

    @staticmethod
    def subscription_expired() -> Dict:
        """订阅已到期告警"""
        return {
            "title": "Subscription Expired",
            "message": "Your subscription has expired. All bots have been stopped. Please renew to continue.",
            "severity": AlertSeverity.CRITICAL,
            "alert_type": "subscription_expired",
        }

    @staticmethod
    def high_loss_alert(bot_name: str, loss_amount: float, loss_percent: float) -> Dict:
        """高额亏损告警"""
        return {
            "title": f"High Loss Alert: {bot_name}",
            "message": f"Bot '{bot_name}' has lost ${loss_amount:.2f} ({loss_percent:.2f}%). Consider reviewing your strategy.",
            "severity": AlertSeverity.ERROR,
            "alert_type": "high_loss",
        }

    @staticmethod
    def tenant_unhealthy(tenant_code: str, reason: str) -> Dict:
        """租户不健康告警"""
        return {
            "title": f"Tenant Unhealthy: {tenant_code}",
            "message": f"Your tenant stack is experiencing issues. Reason: {reason}",
            "severity": AlertSeverity.ERROR,
            "alert_type": "tenant_unhealthy",
        }


# ==================== 使用示例 ====================

if __name__ == "__main__":
    notifier = NotificationManager()

    # 创建告警
    # alert_data = AlertTemplates.bot_stopped("My Grid Bot", "User manually stopped")
    # alert = notifier.create_alert(
    #     user_id="user-id",
    #     **alert_data,
    #     bot_id="bot-id"
    # )
