"""
Alerting Service

Implements comprehensive alerting system for performance degradation, resource usage patterns,
and error rate tracking with multiple notification channels.
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict, deque
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    # Try relative imports first (when used as module)
    from .performance_monitoring_service import get_performance_monitoring_service, MetricType
    from .monitoring_integration_service import get_monitoring_integration_service
    from .error_monitoring import get_monitoring_service
    from ..config.settings import get_settings
except ImportError:
    # Fall back to absolute imports (when used directly)
    from services.performance_monitoring_service import get_performance_monitoring_service, MetricType
    from services.monitoring_integration_service import get_monitoring_integration_service
    from services.error_monitoring import get_monitoring_service
    from config.settings import get_settings

# Configure logging
logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AlertChannel(Enum):
    """Alert notification channels."""
    LOG = "log"
    EMAIL = "email"
    WEBHOOK = "webhook"
    SLACK = "slack"
    DATABASE = "database"


class AlertStatus(Enum):
    """Alert status."""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


@dataclass
class AlertRule:
    """Alert rule definition."""
    name: str
    description: str
    condition: Callable[[Dict[str, Any]], bool]
    severity: AlertSeverity
    channels: List[AlertChannel]
    cooldown_minutes: int = 5
    max_alerts_per_hour: int = 10
    auto_resolve_minutes: Optional[int] = None
    tags: List[str] = field(default_factory=list)
    
    # State tracking
    last_triggered: Optional[datetime] = None
    alerts_this_hour: int = 0
    hour_reset_time: Optional[datetime] = None
    
    def should_trigger(self, metrics: Dict[str, Any]) -> bool:
        """Check if alert should trigger."""
        now = datetime.now()
        
        # Reset hourly counter if needed
        if not self.hour_reset_time or now - self.hour_reset_time >= timedelta(hours=1):
            self.alerts_this_hour = 0
            self.hour_reset_time = now
        
        # Check rate limiting
        if self.alerts_this_hour >= self.max_alerts_per_hour:
            return False
        
        # Check cooldown
        if self.last_triggered:
            cooldown_end = self.last_triggered + timedelta(minutes=self.cooldown_minutes)
            if now < cooldown_end:
                return False
        
        # Check condition
        return self.condition(metrics)
    
    def trigger(self) -> None:
        """Mark rule as triggered."""
        self.last_triggered = datetime.now()
        self.alerts_this_hour += 1


@dataclass
class Alert:
    """Alert instance."""
    alert_id: str
    rule_name: str
    title: str
    description: str
    severity: AlertSeverity
    status: AlertStatus
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolution_note: Optional[str] = None
    metrics_snapshot: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary."""
        return {
            "alert_id": self.alert_id,
            "rule_name": self.rule_name,
            "title": self.title,
            "description": self.description,
            "severity": self.severity.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "acknowledged_by": self.acknowledged_by,
            "resolution_note": self.resolution_note,
            "metrics_snapshot": self.metrics_snapshot,
            "tags": self.tags
        }


class NotificationChannel:
    """Base class for notification channels."""
    
    def __init__(self, channel_type: AlertChannel, config: Dict[str, Any]):
        """Initialize notification channel."""
        self.channel_type = channel_type
        self.config = config
    
    async def send_notification(self, alert: Alert) -> bool:
        """Send notification for alert."""
        raise NotImplementedError


class LogNotificationChannel(NotificationChannel):
    """Log-based notification channel."""
    
    async def send_notification(self, alert: Alert) -> bool:
        """Send log notification."""
        try:
            log_level = {
                AlertSeverity.INFO: logging.INFO,
                AlertSeverity.WARNING: logging.WARNING,
                AlertSeverity.CRITICAL: logging.CRITICAL,
                AlertSeverity.EMERGENCY: logging.CRITICAL
            }.get(alert.severity, logging.INFO)
            
            logger.log(
                log_level,
                f"ALERT [{alert.severity.value.upper()}] {alert.title}: {alert.description}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending log notification: {e}")
            return False


class EmailNotificationChannel(NotificationChannel):
    """Email notification channel."""
    
    async def send_notification(self, alert: Alert) -> bool:
        """Send email notification."""
        try:
            smtp_config = self.config.get("smtp", {})
            if not smtp_config:
                logger.warning("SMTP configuration not found for email notifications")
                return False
            
            # Create email message
            msg = MIMEMultipart()
            msg['From'] = smtp_config.get("from_email", "alerts@gitmeshtool.com")
            msg['To'] = ", ".join(self.config.get("recipients", []))
            msg['Subject'] = f"[{alert.severity.value.upper()}] {alert.title}"
            
            # Email body
            body = self._create_email_body(alert)
            msg.attach(MIMEText(body, 'html'))
            
            # Send email
            server = smtplib.SMTP(smtp_config.get("host"), smtp_config.get("port", 587))
            if smtp_config.get("use_tls", True):
                server.starttls()
            
            if smtp_config.get("username") and smtp_config.get("password"):
                server.login(smtp_config["username"], smtp_config["password"])
            
            server.send_message(msg)
            server.quit()
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending email notification: {e}")
            return False
    
    def _create_email_body(self, alert: Alert) -> str:
        """Create HTML email body."""
        severity_colors = {
            AlertSeverity.INFO: "#17a2b8",
            AlertSeverity.WARNING: "#ffc107",
            AlertSeverity.CRITICAL: "#dc3545",
            AlertSeverity.EMERGENCY: "#6f42c1"
        }
        
        color = severity_colors.get(alert.severity, "#6c757d")
        
        return f"""
        <html>
        <body>
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background-color: {color}; color: white; padding: 20px; border-radius: 5px 5px 0 0;">
                    <h2 style="margin: 0;">{alert.title}</h2>
                    <p style="margin: 5px 0 0 0;">Severity: {alert.severity.value.upper()}</p>
                </div>
                
                <div style="background-color: #f8f9fa; padding: 20px; border: 1px solid #dee2e6; border-top: none;">
                    <h3>Description</h3>
                    <p>{alert.description}</p>
                    
                    <h3>Details</h3>
                    <ul>
                        <li><strong>Alert ID:</strong> {alert.alert_id}</li>
                        <li><strong>Rule:</strong> {alert.rule_name}</li>
                        <li><strong>Created:</strong> {alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}</li>
                        <li><strong>Status:</strong> {alert.status.value.upper()}</li>
                    </ul>
                    
                    {self._format_metrics_snapshot(alert.metrics_snapshot)}
                </div>
                
                <div style="background-color: #e9ecef; padding: 15px; border-radius: 0 0 5px 5px; text-align: center;">
                    <p style="margin: 0; font-size: 12px; color: #6c757d;">
                        This alert was generated by GitMesh Cosmos Monitoring System
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _format_metrics_snapshot(self, metrics: Dict[str, Any]) -> str:
        """Format metrics snapshot for email."""
        if not metrics:
            return ""
        
        html = "<h3>Metrics Snapshot</h3><ul>"
        for key, value in metrics.items():
            if isinstance(value, dict):
                html += f"<li><strong>{key}:</strong><ul>"
                for sub_key, sub_value in value.items():
                    html += f"<li>{sub_key}: {sub_value}</li>"
                html += "</ul></li>"
            else:
                html += f"<li><strong>{key}:</strong> {value}</li>"
        html += "</ul>"
        
        return html


class WebhookNotificationChannel(NotificationChannel):
    """Webhook notification channel."""
    
    async def send_notification(self, alert: Alert) -> bool:
        """Send webhook notification."""
        try:
            import aiohttp
            
            webhook_url = self.config.get("url")
            if not webhook_url:
                logger.warning("Webhook URL not configured")
                return False
            
            # Prepare payload
            payload = {
                "alert": alert.to_dict(),
                "timestamp": datetime.now().isoformat(),
                "source": "gitmeshtool-cosmos-monitoring"
            }
            
            # Add custom fields if configured
            custom_fields = self.config.get("custom_fields", {})
            payload.update(custom_fields)
            
            # Send webhook
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    webhook_url,
                    json=payload,
                    headers=self.config.get("headers", {})
                ) as response:
                    if response.status < 400:
                        return True
                    else:
                        logger.error(f"Webhook returned status {response.status}")
                        return False
            
        except Exception as e:
            logger.error(f"Error sending webhook notification: {e}")
            return False


class SlackNotificationChannel(NotificationChannel):
    """Slack notification channel."""
    
    async def send_notification(self, alert: Alert) -> bool:
        """Send Slack notification."""
        try:
            import aiohttp
            
            webhook_url = self.config.get("webhook_url")
            if not webhook_url:
                logger.warning("Slack webhook URL not configured")
                return False
            
            # Create Slack message
            color = {
                AlertSeverity.INFO: "#36a64f",
                AlertSeverity.WARNING: "#ff9500",
                AlertSeverity.CRITICAL: "#ff0000",
                AlertSeverity.EMERGENCY: "#800080"
            }.get(alert.severity, "#808080")
            
            payload = {
                "username": "GitMesh Monitoring",
                "icon_emoji": ":warning:",
                "attachments": [
                    {
                        "color": color,
                        "title": alert.title,
                        "text": alert.description,
                        "fields": [
                            {
                                "title": "Severity",
                                "value": alert.severity.value.upper(),
                                "short": True
                            },
                            {
                                "title": "Rule",
                                "value": alert.rule_name,
                                "short": True
                            },
                            {
                                "title": "Alert ID",
                                "value": alert.alert_id,
                                "short": True
                            },
                            {
                                "title": "Status",
                                "value": alert.status.value.upper(),
                                "short": True
                            }
                        ],
                        "footer": "GitMesh Cosmos Monitoring",
                        "ts": int(alert.created_at.timestamp())
                    }
                ]
            }
            
            # Send to Slack
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(webhook_url, json=payload) as response:
                    if response.status == 200:
                        return True
                    else:
                        logger.error(f"Slack webhook returned status {response.status}")
                        return False
            
        except Exception as e:
            logger.error(f"Error sending Slack notification: {e}")
            return False


class AlertingService:
    """Main alerting service."""
    
    def __init__(self):
        """Initialize alerting service."""
        self.settings = get_settings()
        
        # Alert rules and active alerts
        self.alert_rules: List[AlertRule] = []
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: deque = deque(maxlen=1000)  # Keep last 1000 alerts
        
        # Notification channels
        self.notification_channels: Dict[AlertChannel, NotificationChannel] = {}
        self._setup_notification_channels()
        
        # Default alert rules
        self._setup_default_alert_rules()
        
        # Background tasks
        self._alerting_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # Alert ID counter
        self._alert_counter = 0
    
    def _setup_notification_channels(self) -> None:
        """Setup notification channels."""
        # Log channel (always available)
        self.notification_channels[AlertChannel.LOG] = LogNotificationChannel(
            AlertChannel.LOG, {}
        )
        
        # Email channel
        email_config = getattr(self.settings, 'email_alerts', {})
        if email_config:
            self.notification_channels[AlertChannel.EMAIL] = EmailNotificationChannel(
                AlertChannel.EMAIL, email_config
            )
        
        # Webhook channel
        webhook_config = getattr(self.settings, 'webhook_alerts', {})
        if webhook_config:
            self.notification_channels[AlertChannel.WEBHOOK] = WebhookNotificationChannel(
                AlertChannel.WEBHOOK, webhook_config
            )
        
        # Slack channel
        slack_config = getattr(self.settings, 'slack_alerts', {})
        if slack_config:
            self.notification_channels[AlertChannel.SLACK] = SlackNotificationChannel(
                AlertChannel.SLACK, slack_config
            )
    
    def _setup_default_alert_rules(self) -> None:
        """Setup default alert rules."""
        # High response time alert
        self.alert_rules.append(AlertRule(
            name="high_response_time",
            description="Chat response time is consistently high",
            condition=lambda m: (
                m.get("response_times", {}).get("p95_1h_ms", 0) > 5000 and
                m.get("response_times", {}).get("avg_1h_ms", 0) > 3000
            ),
            severity=AlertSeverity.WARNING,
            channels=[AlertChannel.LOG, AlertChannel.EMAIL],
            cooldown_minutes=10,
            max_alerts_per_hour=3,
            tags=["performance", "response_time"]
        ))
        
        # Critical response time alert
        self.alert_rules.append(AlertRule(
            name="critical_response_time",
            description="Chat response time is critically high",
            condition=lambda m: m.get("response_times", {}).get("p95_1h_ms", 0) > 10000,
            severity=AlertSeverity.CRITICAL,
            channels=[AlertChannel.LOG, AlertChannel.EMAIL, AlertChannel.SLACK],
            cooldown_minutes=5,
            max_alerts_per_hour=6,
            tags=["performance", "response_time", "critical"]
        ))
        
        # High memory usage alert
        self.alert_rules.append(AlertRule(
            name="high_memory_usage",
            description="System memory usage is high",
            condition=lambda m: m.get("memory", {}).get("avg_1h_percent", 0) > 80,
            severity=AlertSeverity.WARNING,
            channels=[AlertChannel.LOG, AlertChannel.EMAIL],
            cooldown_minutes=15,
            max_alerts_per_hour=2,
            tags=["system", "memory"]
        ))
        
        # Critical memory usage alert
        self.alert_rules.append(AlertRule(
            name="critical_memory_usage",
            description="System memory usage is critically high",
            condition=lambda m: m.get("memory", {}).get("max_1h_percent", 0) > 90,
            severity=AlertSeverity.CRITICAL,
            channels=[AlertChannel.LOG, AlertChannel.EMAIL, AlertChannel.SLACK],
            cooldown_minutes=5,
            max_alerts_per_hour=4,
            tags=["system", "memory", "critical"]
        ))
        
        # Redis connectivity alert
        self.alert_rules.append(AlertRule(
            name="redis_connectivity",
            description="Redis connectivity issues detected",
            condition=lambda m: (
                m.get("health_checks", {}).get("redis", {}).get("status") == "critical"
            ),
            severity=AlertSeverity.CRITICAL,
            channels=[AlertChannel.LOG, AlertChannel.EMAIL, AlertChannel.SLACK],
            cooldown_minutes=2,
            max_alerts_per_hour=10,
            auto_resolve_minutes=5,
            tags=["redis", "connectivity", "critical"]
        ))
        
        # Low cache hit rate alert
        self.alert_rules.append(AlertRule(
            name="low_cache_hit_rate",
            description="File cache hit rate is low",
            condition=lambda m: m.get("cache", {}).get("hit_rate_1h", 1.0) < 0.7,
            severity=AlertSeverity.WARNING,
            channels=[AlertChannel.LOG],
            cooldown_minutes=30,
            max_alerts_per_hour=1,
            tags=["cache", "performance"]
        ))
        
        # Error rate alert
        self.alert_rules.append(AlertRule(
            name="high_error_rate",
            description="Error rate is elevated",
            condition=lambda m: self._calculate_error_rate(m) > 0.05,  # 5% error rate
            severity=AlertSeverity.WARNING,
            channels=[AlertChannel.LOG, AlertChannel.EMAIL],
            cooldown_minutes=10,
            max_alerts_per_hour=3,
            tags=["errors", "reliability"]
        ))
        
        # System health degradation alert
        self.alert_rules.append(AlertRule(
            name="system_health_degradation",
            description="Multiple system components are unhealthy",
            condition=lambda m: self._count_unhealthy_components(m) >= 2,
            severity=AlertSeverity.CRITICAL,
            channels=[AlertChannel.LOG, AlertChannel.EMAIL, AlertChannel.SLACK],
            cooldown_minutes=5,
            max_alerts_per_hour=4,
            tags=["system", "health", "critical"]
        ))
    
    def _calculate_error_rate(self, metrics: Dict[str, Any]) -> float:
        """Calculate error rate from metrics."""
        try:
            cosmos_metrics = metrics.get("cosmos_metrics", {})
            total_requests = cosmos_metrics.get("total_requests", 0)
            failed_requests = cosmos_metrics.get("failed_requests", 0)
            
            if total_requests == 0:
                return 0.0
            
            return failed_requests / total_requests
            
        except Exception:
            return 0.0
    
    def _count_unhealthy_components(self, metrics: Dict[str, Any]) -> int:
        """Count unhealthy components."""
        try:
            health_checks = metrics.get("health_checks", {})
            unhealthy_count = 0
            
            for component, health in health_checks.items():
                if health.get("status") in ["critical", "warning"]:
                    unhealthy_count += 1
            
            return unhealthy_count
            
        except Exception:
            return 0
    
    async def start_alerting(self) -> None:
        """Start alerting service."""
        self._alerting_task = asyncio.create_task(self._alerting_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info("Alerting service started")
    
    async def stop_alerting(self) -> None:
        """Stop alerting service."""
        if self._alerting_task:
            self._alerting_task.cancel()
            try:
                await self._alerting_task
            except asyncio.CancelledError:
                pass
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Alerting service stopped")
    
    async def _alerting_loop(self) -> None:
        """Main alerting loop."""
        while True:
            try:
                # Get current metrics
                monitoring_service = get_performance_monitoring_service()
                metrics = await monitoring_service.get_performance_summary()
                
                # Check all alert rules
                for rule in self.alert_rules:
                    if rule.should_trigger(metrics):
                        await self._trigger_alert(rule, metrics)
                
                # Check for auto-resolve conditions
                await self._check_auto_resolve(metrics)
                
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in alerting loop: {e}")
                await asyncio.sleep(60)
    
    async def _cleanup_loop(self) -> None:
        """Cleanup old alerts and reset counters."""
        while True:
            try:
                # Clean up resolved alerts older than 24 hours
                cutoff_time = datetime.now() - timedelta(hours=24)
                
                alerts_to_remove = []
                for alert_id, alert in self.active_alerts.items():
                    if (alert.status == AlertStatus.RESOLVED and 
                        alert.resolved_at and 
                        alert.resolved_at < cutoff_time):
                        alerts_to_remove.append(alert_id)
                
                for alert_id in alerts_to_remove:
                    removed_alert = self.active_alerts.pop(alert_id)
                    self.alert_history.append(removed_alert)
                
                if alerts_to_remove:
                    logger.info(f"Cleaned up {len(alerts_to_remove)} old resolved alerts")
                
                await asyncio.sleep(3600)  # Run every hour
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(3600)
    
    async def _trigger_alert(self, rule: AlertRule, metrics: Dict[str, Any]) -> None:
        """Trigger an alert."""
        try:
            rule.trigger()
            
            # Generate alert ID
            self._alert_counter += 1
            alert_id = f"alert_{int(datetime.now().timestamp())}_{self._alert_counter}"
            
            # Create alert
            alert = Alert(
                alert_id=alert_id,
                rule_name=rule.name,
                title=f"Alert: {rule.name.replace('_', ' ').title()}",
                description=rule.description,
                severity=rule.severity,
                status=AlertStatus.ACTIVE,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                metrics_snapshot=metrics.copy(),
                tags=rule.tags.copy()
            )
            
            # Store alert
            self.active_alerts[alert_id] = alert
            
            # Send notifications
            await self._send_notifications(alert, rule.channels)
            
            logger.info(f"Alert triggered: {alert.title} (ID: {alert_id})")
            
        except Exception as e:
            logger.error(f"Error triggering alert for rule {rule.name}: {e}")
    
    async def _send_notifications(self, alert: Alert, channels: List[AlertChannel]) -> None:
        """Send notifications through specified channels."""
        for channel in channels:
            if channel in self.notification_channels:
                try:
                    success = await self.notification_channels[channel].send_notification(alert)
                    if success:
                        logger.debug(f"Notification sent via {channel.value} for alert {alert.alert_id}")
                    else:
                        logger.warning(f"Failed to send notification via {channel.value} for alert {alert.alert_id}")
                except Exception as e:
                    logger.error(f"Error sending notification via {channel.value}: {e}")
    
    async def _check_auto_resolve(self, metrics: Dict[str, Any]) -> None:
        """Check for auto-resolve conditions."""
        for alert in list(self.active_alerts.values()):
            if alert.status != AlertStatus.ACTIVE:
                continue
            
            # Find the rule for this alert
            rule = next((r for r in self.alert_rules if r.name == alert.rule_name), None)
            if not rule or not rule.auto_resolve_minutes:
                continue
            
            # Check if condition is no longer met
            if not rule.condition(metrics):
                # Check if enough time has passed
                time_since_created = datetime.now() - alert.created_at
                if time_since_created.total_seconds() >= rule.auto_resolve_minutes * 60:
                    await self.resolve_alert(
                        alert.alert_id, 
                        "Auto-resolved: condition no longer met"
                    )
    
    async def acknowledge_alert(self, alert_id: str, acknowledged_by: str, note: Optional[str] = None) -> bool:
        """Acknowledge an alert."""
        try:
            if alert_id not in self.active_alerts:
                return False
            
            alert = self.active_alerts[alert_id]
            if alert.status != AlertStatus.ACTIVE:
                return False
            
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.acknowledged_at = datetime.now()
            alert.acknowledged_by = acknowledged_by
            alert.updated_at = datetime.now()
            
            if note:
                alert.resolution_note = note
            
            logger.info(f"Alert acknowledged: {alert_id} by {acknowledged_by}")
            return True
            
        except Exception as e:
            logger.error(f"Error acknowledging alert {alert_id}: {e}")
            return False
    
    async def resolve_alert(self, alert_id: str, resolution_note: Optional[str] = None) -> bool:
        """Resolve an alert."""
        try:
            if alert_id not in self.active_alerts:
                return False
            
            alert = self.active_alerts[alert_id]
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = datetime.now()
            alert.updated_at = datetime.now()
            
            if resolution_note:
                alert.resolution_note = resolution_note
            
            logger.info(f"Alert resolved: {alert_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error resolving alert {alert_id}: {e}")
            return False
    
    def get_active_alerts(self) -> List[Alert]:
        """Get all active alerts."""
        return [alert for alert in self.active_alerts.values() 
                if alert.status == AlertStatus.ACTIVE]
    
    def get_alert_history(self, hours: int = 24) -> List[Alert]:
        """Get alert history."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        # Get recent active alerts
        recent_alerts = [
            alert for alert in self.active_alerts.values()
            if alert.created_at >= cutoff_time
        ]
        
        # Get recent historical alerts
        recent_history = [
            alert for alert in self.alert_history
            if alert.created_at >= cutoff_time
        ]
        
        # Combine and sort by creation time
        all_alerts = recent_alerts + recent_history
        return sorted(all_alerts, key=lambda a: a.created_at, reverse=True)
    
    def get_alert_statistics(self) -> Dict[str, Any]:
        """Get alert statistics."""
        now = datetime.now()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)
        
        # Get all alerts from last 7 days
        recent_alerts = self.get_alert_history(hours=168)  # 7 days
        
        # Calculate statistics
        stats = {
            "total_active": len(self.get_active_alerts()),
            "total_24h": len([a for a in recent_alerts if a.created_at >= last_24h]),
            "total_7d": len(recent_alerts),
            "by_severity": defaultdict(int),
            "by_rule": defaultdict(int),
            "resolution_times": [],
            "acknowledgment_rate": 0
        }
        
        acknowledged_count = 0
        for alert in recent_alerts:
            stats["by_severity"][alert.severity.value] += 1
            stats["by_rule"][alert.rule_name] += 1
            
            if alert.acknowledged_at:
                acknowledged_count += 1
            
            if alert.resolved_at and alert.created_at:
                resolution_time = (alert.resolved_at - alert.created_at).total_seconds() / 60
                stats["resolution_times"].append(resolution_time)
        
        if recent_alerts:
            stats["acknowledgment_rate"] = acknowledged_count / len(recent_alerts)
        
        if stats["resolution_times"]:
            stats["avg_resolution_time_minutes"] = sum(stats["resolution_times"]) / len(stats["resolution_times"])
        else:
            stats["avg_resolution_time_minutes"] = 0
        
        return dict(stats)
    
    def add_alert_rule(self, rule: AlertRule) -> None:
        """Add a custom alert rule."""
        self.alert_rules.append(rule)
        logger.info(f"Added alert rule: {rule.name}")
    
    def remove_alert_rule(self, rule_name: str) -> bool:
        """Remove an alert rule."""
        for i, rule in enumerate(self.alert_rules):
            if rule.name == rule_name:
                del self.alert_rules[i]
                logger.info(f"Removed alert rule: {rule_name}")
                return True
        return False


# Global service instance
alerting_service = AlertingService()


def get_alerting_service() -> AlertingService:
    """Get the global alerting service."""
    return alerting_service