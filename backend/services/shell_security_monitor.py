"""
Shell Security Monitoring Service

Monitors and alerts on shell command blocking attempts for security analysis.
"""

import os
import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from collections import defaultdict, deque

from services.shell_command_blocker import shell_blocker
from utils.audit_logging import audit_logger

logger = logging.getLogger(__name__)


@dataclass
class SecurityAlert:
    """Security alert for suspicious shell command activity."""
    alert_id: str
    alert_type: str
    severity: str
    user_id: Optional[str]
    session_id: Optional[str]
    timestamp: datetime
    description: str
    blocked_commands: List[str]
    metadata: Dict[str, Any]


@dataclass
class SecurityMetrics:
    """Security metrics for shell command blocking."""
    total_blocked_commands: int
    unique_users_blocked: int
    unique_sessions_blocked: int
    most_blocked_commands: List[Dict[str, Any]]
    alerts_generated: int
    high_severity_alerts: int
    time_period: str


class ShellSecurityMonitor:
    """
    Monitor shell command blocking attempts and generate security alerts.
    
    This service analyzes blocked shell commands to detect:
    - Repeated attack attempts
    - Suspicious command patterns
    - Potential security breaches
    - Unusual user behavior
    """
    
    def __init__(self):
        """Initialize the security monitor."""
        self.alerts: List[SecurityAlert] = []
        self.metrics_cache: Dict[str, SecurityMetrics] = {}
        self.user_activity: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self.command_patterns: Dict[str, int] = defaultdict(int)
        self.alert_thresholds = {
            'rapid_attempts': 10,  # Commands per minute
            'suspicious_patterns': 5,  # Suspicious commands per session
            'repeated_user': 20,  # Commands per user per hour
        }
        
        logger.info("Shell Security Monitor initialized")
    
    async def start_monitoring(self):
        """Start continuous security monitoring."""
        logger.info("Starting shell security monitoring")
        
        while True:
            try:
                await self._analyze_blocked_commands()
                await self._generate_alerts()
                await self._update_metrics()
                
                # Sleep for monitoring interval
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in security monitoring: {e}")
                await asyncio.sleep(60)  # Wait longer on error
    
    async def _analyze_blocked_commands(self):
        """Analyze recently blocked commands for security threats."""
        try:
            # Get recent blocked commands
            blocked_commands = shell_blocker.get_blocked_commands(limit=1000)
            
            if not blocked_commands:
                return
            
            # Analyze for different threat patterns
            await self._analyze_rapid_attempts(blocked_commands)
            await self._analyze_suspicious_patterns(blocked_commands)
            await self._analyze_repeated_users(blocked_commands)
            await self._analyze_command_evolution(blocked_commands)
            
        except Exception as e:
            logger.error(f"Error analyzing blocked commands: {e}")
    
    async def _analyze_rapid_attempts(self, blocked_commands: List[Dict]):
        """Analyze for rapid command execution attempts."""
        try:
            # Group commands by user and time window
            now = datetime.now()
            one_minute_ago = now - timedelta(minutes=1)
            
            user_attempts = defaultdict(list)
            
            for cmd in blocked_commands:
                cmd_time = datetime.fromisoformat(cmd['timestamp'].replace('Z', '+00:00'))
                if cmd_time >= one_minute_ago:
                    user_id = cmd.get('user_id', 'unknown')
                    user_attempts[user_id].append(cmd)
            
            # Check for users exceeding rapid attempt threshold
            for user_id, attempts in user_attempts.items():
                if len(attempts) >= self.alert_thresholds['rapid_attempts']:
                    await self._create_alert(
                        alert_type="RAPID_SHELL_ATTEMPTS",
                        severity="HIGH",
                        user_id=user_id,
                        description=f"User attempted {len(attempts)} shell commands in 1 minute",
                        blocked_commands=[cmd['command'] for cmd in attempts[-10:]],  # Last 10 commands
                        metadata={
                            'attempts_count': len(attempts),
                            'time_window': '1_minute',
                            'threshold_exceeded': True
                        }
                    )
            
        except Exception as e:
            logger.error(f"Error analyzing rapid attempts: {e}")
    
    async def _analyze_suspicious_patterns(self, blocked_commands: List[Dict]):
        """Analyze for suspicious command patterns."""
        try:
            # Define suspicious patterns
            suspicious_patterns = [
                r'rm\s+-rf',  # Dangerous deletion
                r'curl.*\|.*bash',  # Download and execute
                r'wget.*\|.*bash',  # Download and execute
                r'/etc/passwd',  # System file access
                r'/etc/shadow',  # Password file access
                r'sudo',  # Privilege escalation
                r'su\s+',  # User switching
                r'chmod\s+777',  # Dangerous permissions
                r'nc\s+.*\s+-e',  # Netcat backdoor
                r'python.*-c.*os\.system',  # Python command injection
                r'eval\s*\(',  # Code evaluation
                r'exec\s*\(',  # Code execution
                r'\$\(',  # Command substitution
                r'`.*`',  # Command substitution
            ]
            
            import re
            
            # Group by session
            session_commands = defaultdict(list)
            
            for cmd in blocked_commands[-200:]:  # Check recent commands
                session_id = cmd.get('session_id', 'unknown')
                session_commands[session_id].append(cmd)
            
            # Check each session for suspicious patterns
            for session_id, commands in session_commands.items():
                suspicious_count = 0
                suspicious_commands = []
                
                for cmd in commands:
                    command_text = cmd['command'].lower()
                    
                    for pattern in suspicious_patterns:
                        if re.search(pattern, command_text, re.IGNORECASE):
                            suspicious_count += 1
                            suspicious_commands.append(cmd['command'])
                            break
                
                if suspicious_count >= self.alert_thresholds['suspicious_patterns']:
                    user_id = commands[0].get('user_id', 'unknown')
                    
                    await self._create_alert(
                        alert_type="SUSPICIOUS_COMMAND_PATTERNS",
                        severity="CRITICAL",
                        user_id=user_id,
                        session_id=session_id,
                        description=f"Session contains {suspicious_count} suspicious command patterns",
                        blocked_commands=suspicious_commands,
                        metadata={
                            'suspicious_count': suspicious_count,
                            'total_commands': len(commands),
                            'patterns_detected': True
                        }
                    )
            
        except Exception as e:
            logger.error(f"Error analyzing suspicious patterns: {e}")
    
    async def _analyze_repeated_users(self, blocked_commands: List[Dict]):
        """Analyze for users with repeated blocking attempts."""
        try:
            # Group by user and time window (1 hour)
            now = datetime.now()
            one_hour_ago = now - timedelta(hours=1)
            
            user_hourly_attempts = defaultdict(list)
            
            for cmd in blocked_commands:
                cmd_time = datetime.fromisoformat(cmd['timestamp'].replace('Z', '+00:00'))
                if cmd_time >= one_hour_ago:
                    user_id = cmd.get('user_id', 'unknown')
                    user_hourly_attempts[user_id].append(cmd)
            
            # Check for users exceeding hourly threshold
            for user_id, attempts in user_hourly_attempts.items():
                if len(attempts) >= self.alert_thresholds['repeated_user']:
                    # Check if we already alerted for this user recently
                    recent_alerts = [
                        alert for alert in self.alerts[-50:]  # Check last 50 alerts
                        if alert.user_id == user_id and 
                        alert.alert_type == "REPEATED_USER_ATTEMPTS" and
                        (now - alert.timestamp).seconds < 3600  # Within last hour
                    ]
                    
                    if not recent_alerts:  # Only alert once per hour per user
                        await self._create_alert(
                            alert_type="REPEATED_USER_ATTEMPTS",
                            severity="MEDIUM",
                            user_id=user_id,
                            description=f"User has {len(attempts)} blocked commands in 1 hour",
                            blocked_commands=[cmd['command'] for cmd in attempts[-15:]],  # Last 15 commands
                            metadata={
                                'hourly_attempts': len(attempts),
                                'threshold_exceeded': True,
                                'time_window': '1_hour'
                            }
                        )
            
        except Exception as e:
            logger.error(f"Error analyzing repeated users: {e}")
    
    async def _analyze_command_evolution(self, blocked_commands: List[Dict]):
        """Analyze how blocked commands are evolving over time."""
        try:
            # Track command patterns over time
            recent_commands = blocked_commands[-100:]  # Last 100 commands
            
            for cmd in recent_commands:
                command_text = cmd['command'].lower()
                
                # Extract command base (first word)
                command_base = command_text.split()[0] if command_text.split() else 'unknown'
                self.command_patterns[command_base] += 1
            
            # Log top command patterns for analysis
            if len(recent_commands) >= 50:  # Only analyze if we have enough data
                top_patterns = sorted(
                    self.command_patterns.items(), 
                    key=lambda x: x[1], 
                    reverse=True
                )[:10]
                
                logger.info(f"Top blocked command patterns: {top_patterns}")
                
                # Alert if we see new attack patterns emerging
                for pattern, count in top_patterns[:3]:  # Top 3 patterns
                    if count >= 10:  # Significant usage
                        await self._create_alert(
                            alert_type="EMERGING_ATTACK_PATTERN",
                            severity="LOW",
                            description=f"Command pattern '{pattern}' blocked {count} times recently",
                            blocked_commands=[pattern],
                            metadata={
                                'pattern': pattern,
                                'count': count,
                                'analysis_window': '100_commands'
                            }
                        )
            
        except Exception as e:
            logger.error(f"Error analyzing command evolution: {e}")
    
    async def _create_alert(
        self, 
        alert_type: str, 
        severity: str, 
        description: str,
        blocked_commands: List[str],
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Create a security alert."""
        try:
            alert_id = f"{alert_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.alerts)}"
            
            alert = SecurityAlert(
                alert_id=alert_id,
                alert_type=alert_type,
                severity=severity,
                user_id=user_id,
                session_id=session_id,
                timestamp=datetime.now(),
                description=description,
                blocked_commands=blocked_commands,
                metadata=metadata or {}
            )
            
            self.alerts.append(alert)
            
            # Log to audit system
            from utils.audit_logging import AuditEventType, AuditSeverity, AuditContext
            context = AuditContext(user_id=user_id, session_id=session_id)
            audit_logger.log_event(
                event_type=AuditEventType.SECURITY_VIOLATION,
                severity=AuditSeverity.HIGH,
                context=context,
                action="security_alert_generated",
                result="alert_created",
                details={
                    "alert_id": alert_id,
                    "alert_type": alert_type,
                    "severity": severity,
                    "description": description,
                    "blocked_commands_count": len(blocked_commands),
                    "metadata": metadata
                }
            )
            
            # Log based on severity
            if severity == "CRITICAL":
                logger.critical(f"SECURITY ALERT: {description} (Alert ID: {alert_id})")
            elif severity == "HIGH":
                logger.error(f"SECURITY ALERT: {description} (Alert ID: {alert_id})")
            elif severity == "MEDIUM":
                logger.warning(f"SECURITY ALERT: {description} (Alert ID: {alert_id})")
            else:
                logger.info(f"SECURITY ALERT: {description} (Alert ID: {alert_id})")
            
        except Exception as e:
            logger.error(f"Error creating security alert: {e}")
    
    async def _generate_alerts(self):
        """Generate additional alerts based on overall system state."""
        try:
            # Check if shell blocker is active
            if not shell_blocker.is_active:
                await self._create_alert(
                    alert_type="SHELL_BLOCKER_INACTIVE",
                    severity="CRITICAL",
                    description="Shell command blocker is not active - security risk!",
                    blocked_commands=[],
                    metadata={
                        'blocker_status': 'inactive',
                        'security_risk': 'high'
                    }
                )
            
            # Check for system health
            stats = shell_blocker.get_security_stats()
            if stats['total_blocked_commands'] == 0:
                # No blocked commands might indicate blocker is not working
                logger.debug("No blocked commands detected - monitoring system health")
            
        except Exception as e:
            logger.error(f"Error generating system alerts: {e}")
    
    async def _update_metrics(self):
        """Update security metrics."""
        try:
            blocked_commands = shell_blocker.get_blocked_commands(limit=10000)
            
            if not blocked_commands:
                return
            
            # Calculate metrics for different time periods
            now = datetime.now()
            time_periods = {
                'last_hour': now - timedelta(hours=1),
                'last_day': now - timedelta(days=1),
                'last_week': now - timedelta(weeks=1)
            }
            
            for period_name, start_time in time_periods.items():
                period_commands = [
                    cmd for cmd in blocked_commands
                    if datetime.fromisoformat(cmd['timestamp'].replace('Z', '+00:00')) >= start_time
                ]
                
                if period_commands:
                    metrics = SecurityMetrics(
                        total_blocked_commands=len(period_commands),
                        unique_users_blocked=len(set(cmd.get('user_id', 'unknown') for cmd in period_commands)),
                        unique_sessions_blocked=len(set(cmd.get('session_id', 'unknown') for cmd in period_commands)),
                        most_blocked_commands=self._get_top_commands(period_commands),
                        alerts_generated=len([a for a in self.alerts if a.timestamp >= start_time]),
                        high_severity_alerts=len([a for a in self.alerts if a.timestamp >= start_time and a.severity in ['HIGH', 'CRITICAL']]),
                        time_period=period_name
                    )
                    
                    self.metrics_cache[period_name] = metrics
            
        except Exception as e:
            logger.error(f"Error updating metrics: {e}")
    
    def _get_top_commands(self, commands: List[Dict], limit: int = 10) -> List[Dict[str, Any]]:
        """Get top blocked commands by frequency."""
        command_counts = defaultdict(int)
        
        for cmd in commands:
            command_text = cmd['command']
            command_counts[command_text] += 1
        
        top_commands = sorted(
            command_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]
        
        return [{'command': cmd, 'count': count} for cmd, count in top_commands]
    
    def get_alerts(self, severity: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get security alerts.
        
        Args:
            severity: Filter by severity level
            limit: Maximum number of alerts to return
            
        Returns:
            List of alert dictionaries
        """
        alerts = self.alerts
        
        if severity:
            alerts = [alert for alert in alerts if alert.severity == severity]
        
        # Return most recent alerts first
        alerts = sorted(alerts, key=lambda x: x.timestamp, reverse=True)[:limit]
        
        return [asdict(alert) for alert in alerts]
    
    def get_metrics(self, time_period: str = 'last_hour') -> Optional[Dict[str, Any]]:
        """
        Get security metrics for a time period.
        
        Args:
            time_period: Time period ('last_hour', 'last_day', 'last_week')
            
        Returns:
            Metrics dictionary or None if not available
        """
        metrics = self.metrics_cache.get(time_period)
        return asdict(metrics) if metrics else None
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive dashboard data for security monitoring."""
        try:
            return {
                'blocker_status': {
                    'is_active': shell_blocker.is_active,
                    'stats': shell_blocker.get_security_stats()
                },
                'recent_alerts': self.get_alerts(limit=20),
                'critical_alerts': self.get_alerts(severity='CRITICAL', limit=10),
                'metrics': {
                    'last_hour': self.get_metrics('last_hour'),
                    'last_day': self.get_metrics('last_day'),
                    'last_week': self.get_metrics('last_week')
                },
                'top_blocked_commands': self._get_top_commands(
                    shell_blocker.get_blocked_commands(limit=1000)
                ),
                'alert_summary': {
                    'total_alerts': len(self.alerts),
                    'critical_alerts': len([a for a in self.alerts if a.severity == 'CRITICAL']),
                    'high_alerts': len([a for a in self.alerts if a.severity == 'HIGH']),
                    'medium_alerts': len([a for a in self.alerts if a.severity == 'MEDIUM']),
                    'low_alerts': len([a for a in self.alerts if a.severity == 'LOW'])
                }
            }
        except Exception as e:
            logger.error(f"Error getting dashboard data: {e}")
            return {'error': str(e)}


# Global security monitor instance
security_monitor = ShellSecurityMonitor()


async def start_security_monitoring():
    """Start the security monitoring service."""
    await security_monitor.start_monitoring()


def get_security_monitor() -> ShellSecurityMonitor:
    """Get the global security monitor instance."""
    return security_monitor