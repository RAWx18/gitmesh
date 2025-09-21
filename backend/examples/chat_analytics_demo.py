"""
Chat Analytics Demo
Demonstrates the monitoring and analytics functionality for Cosmos Web Chat.
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any

# Mock Redis client for demo purposes
class MockRedisClient:
    """Mock Redis client for demonstration."""
    
    def __init__(self):
        self.data = {}
        self.sets = {}
    
    def hset(self, key: str, mapping: Dict[str, Any]) -> None:
        """Set hash fields."""
        if key not in self.data:
            self.data[key] = {}
        self.data[key].update(mapping)
    
    def hgetall(self, key: str) -> Dict[str, Any]:
        """Get all hash fields."""
        return self.data.get(key, {})
    
    def expire(self, key: str, ttl: int) -> None:
        """Set expiration (mock - no actual expiration)."""
        pass
    
    def sadd(self, key: str, *values) -> None:
        """Add to set."""
        if key not in self.sets:
            self.sets[key] = set()
        self.sets[key].update(values)
    
    def smembers(self, key: str) -> set:
        """Get set members."""
        return self.sets.get(key, set())
    
    def keys(self, pattern: str) -> list:
        """Get keys matching pattern."""
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return [k for k in self.data.keys() if k.startswith(prefix)]
        return []
    
    def pipeline(self):
        """Return pipeline (mock)."""
        return MockPipeline(self)
    
    def info(self) -> Dict[str, Any]:
        """Get Redis info."""
        return {
            'connected_clients': 10,
            'used_memory': 1024 * 1024 * 100  # 100MB
        }


class MockPipeline:
    """Mock Redis pipeline."""
    
    def __init__(self, client):
        self.client = client
        self.commands = []
    
    def hset(self, key: str, mapping: Dict[str, Any]) -> None:
        self.commands.append(('hset', key, mapping))
        return self
    
    def expire(self, key: str, ttl: int) -> None:
        self.commands.append(('expire', key, ttl))
        return self
    
    def sadd(self, key: str, *values) -> None:
        self.commands.append(('sadd', key, values))
        return self
    
    def execute(self) -> None:
        """Execute all commands."""
        for cmd, *args in self.commands:
            if cmd == 'hset':
                self.client.hset(args[0], args[1])
            elif cmd == 'expire':
                self.client.expire(args[0], args[1])
            elif cmd == 'sadd':
                self.client.sadd(args[0], *args[1])


class MockAnalyticsService:
    """Mock analytics service for demonstration."""
    
    def __init__(self):
        self.redis_client = MockRedisClient()
        self.session_prefix = "analytics:session:"
        self.user_metrics_prefix = "analytics:user:"
        self.model_metrics_prefix = "analytics:model:"
        self.error_metrics_prefix = "analytics:error:"
        
        # Model cost estimates (USD per 1K tokens)
        self.model_costs = {
            "gpt-4": {"input": 0.03, "output": 0.06},
            "gpt-3.5-turbo": {"input": 0.001, "output": 0.002},
            "claude-3-opus": {"input": 0.015, "output": 0.075},
            "claude-3-sonnet": {"input": 0.003, "output": 0.015},
            "gemini-pro": {"input": 0.0005, "output": 0.0015},
            "deepseek-coder": {"input": 0.00014, "output": 0.00028},
        }
    
    async def track_session_metrics(
        self,
        session_id: str,
        user_id: str,
        model_used: str,
        **kwargs
    ) -> None:
        """Track session metrics."""
        session_key = f"{self.session_prefix}{session_id}"
        
        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
            "last_activity": datetime.now().isoformat(),
            "model_used": model_used,
            "message_count": kwargs.get("message_count", 0),
            "context_files_count": kwargs.get("context_files_count", 0),
            "conversion_operations": kwargs.get("conversion_operations", 0),
            "error_count": kwargs.get("error_count", 0),
            "is_active": kwargs.get("is_active", True)
        }
        
        self.redis_client.hset(session_key, session_data)
        print(f"✅ Tracked session metrics for {session_id}")
    
    async def track_model_usage(
        self,
        model_name: str,
        canonical_name: str,
        provider: str,
        session_id: str,
        user_id: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        response_time: float = 0.0,
        success: bool = True
    ) -> None:
        """Track model usage metrics."""
        date_str = datetime.now().strftime('%Y-%m-%d')
        model_key = f"{self.model_metrics_prefix}{model_name}:{date_str}"
        
        # Calculate estimated cost
        cost_config = self.model_costs.get(canonical_name, {"input": 0.001, "output": 0.002})
        estimated_cost = (
            (input_tokens / 1000) * cost_config["input"] +
            (output_tokens / 1000) * cost_config["output"]
        )
        
        model_data = {
            "model_name": model_name,
            "canonical_name": canonical_name,
            "provider": provider,
            "date": date_str,
            "request_count": 1,
            "total_tokens": input_tokens + output_tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost": estimated_cost,
            "avg_response_time": response_time,
            "error_count": 0 if success else 1,
            "success_rate": 100.0 if success else 0.0
        }
        
        self.redis_client.hset(model_key, model_data)
        print(f"✅ Tracked model usage for {model_name}: {input_tokens + output_tokens} tokens, ${estimated_cost:.4f}")
    
    async def track_error(
        self,
        error_type: str,
        error_message: str,
        component: str,
        **kwargs
    ) -> str:
        """Track error occurrence."""
        error_id = f"error-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        error_key = f"{self.error_metrics_prefix}{error_id}"
        
        error_data = {
            "error_id": error_id,
            "timestamp": datetime.now().isoformat(),
            "error_type": error_type,
            "error_message": error_message,
            "component": component,
            "severity": kwargs.get("severity", "medium"),
            "session_id": kwargs.get("session_id", ""),
            "user_id": kwargs.get("user_id", ""),
            "resolved": False
        }
        
        self.redis_client.hset(error_key, error_data)
        print(f"❌ Tracked error: {error_type} in {component}")
        return error_id
    
    async def get_realtime_metrics(self) -> Dict[str, Any]:
        """Get real-time metrics."""
        # Mock real-time data
        return {
            "timestamp": datetime.now().isoformat(),
            "active_sessions": 5,
            "active_users": 3,
            "messages_per_minute": 12.5,
            "errors_per_minute": 0.1,
            "avg_response_time": 2.3,
            "redis_connections": 10,
            "memory_usage_mb": 256.0,
            "cpu_usage_percent": 15.0
        }
    
    async def get_session_analytics(self) -> Dict[str, Any]:
        """Get session analytics."""
        sessions = []
        session_keys = self.redis_client.keys(f"{self.session_prefix}*")
        
        for key in session_keys:
            session_data = self.redis_client.hgetall(key)
            if session_data:
                sessions.append(session_data)
        
        # Calculate summary
        total_sessions = len(sessions)
        total_messages = sum(int(s.get("message_count", 0)) for s in sessions)
        unique_users = len(set(s.get("user_id") for s in sessions))
        
        return {
            "sessions": sessions,
            "summary": {
                "total_sessions": total_sessions,
                "total_messages": total_messages,
                "unique_users": unique_users,
                "avg_messages_per_session": total_messages / total_sessions if total_sessions > 0 else 0
            }
        }
    
    async def get_model_usage_analytics(self) -> Dict[str, Any]:
        """Get model usage analytics."""
        usage_data = []
        total_cost = 0.0
        
        model_keys = self.redis_client.keys(f"{self.model_metrics_prefix}*")
        
        for key in model_keys:
            model_data = self.redis_client.hgetall(key)
            if model_data:
                cost = float(model_data.get("estimated_cost", 0))
                total_cost += cost
                usage_data.append(model_data)
        
        return {
            "usage": usage_data,
            "total_cost": total_cost,
            "summary": {
                "total_requests": sum(int(u.get("request_count", 0)) for u in usage_data),
                "total_tokens": sum(int(u.get("total_tokens", 0)) for u in usage_data),
                "models_count": len(usage_data)
            }
        }


async def demo_analytics_workflow():
    """Demonstrate the complete analytics workflow."""
    print("🚀 Starting Chat Analytics Demo")
    print("=" * 50)
    
    # Initialize analytics service
    analytics = MockAnalyticsService()
    
    # Simulate chat session activity
    print("\n📊 Simulating Chat Session Activity...")
    
    # Create multiple sessions
    sessions = [
        {"session_id": "session-001", "user_id": "user-alice", "model": "gemini"},
        {"session_id": "session-002", "user_id": "user-bob", "model": "claude-3-sonnet"},
        {"session_id": "session-003", "user_id": "user-charlie", "model": "gpt-4"},
        {"session_id": "session-004", "user_id": "user-alice", "model": "gemini"},
    ]
    
    for session in sessions:
        await analytics.track_session_metrics(
            session_id=session["session_id"],
            user_id=session["user_id"],
            model_used=session["model"],
            message_count=10 + hash(session["session_id"]) % 20,  # Random 10-30 messages
            context_files_count=hash(session["session_id"]) % 5,  # Random 0-4 files
            conversion_operations=hash(session["session_id"]) % 3,  # Random 0-2 conversions
            is_active=True
        )
    
    print("\n💰 Simulating Model Usage and Cost Tracking...")
    
    # Simulate model usage with different token counts
    model_usage_scenarios = [
        {"model": "gemini", "canonical": "gemini-pro", "provider": "google", "input": 1000, "output": 500, "time": 2.1},
        {"model": "claude", "canonical": "claude-3-sonnet", "provider": "anthropic", "input": 1500, "output": 800, "time": 3.2},
        {"model": "gpt-4", "canonical": "gpt-4", "provider": "openai", "input": 800, "output": 400, "time": 4.5},
        {"model": "deepseek", "canonical": "deepseek-coder", "provider": "deepseek", "input": 2000, "output": 1000, "time": 1.8},
    ]
    
    for usage in model_usage_scenarios:
        await analytics.track_model_usage(
            model_name=usage["model"],
            canonical_name=usage["canonical"],
            provider=usage["provider"],
            session_id="session-001",
            user_id="user-alice",
            input_tokens=usage["input"],
            output_tokens=usage["output"],
            response_time=usage["time"],
            success=True
        )
    
    print("\n⚠️ Simulating Error Tracking...")
    
    # Simulate various errors
    error_scenarios = [
        {"type": "ValidationError", "message": "Invalid model selection", "component": "cosmos_web_service"},
        {"type": "ConnectionError", "message": "Redis connection timeout", "component": "redis_client"},
        {"type": "RateLimitError", "message": "API rate limit exceeded", "component": "model_api"},
    ]
    
    for error in error_scenarios:
        await analytics.track_error(
            error_type=error["type"],
            error_message=error["message"],
            component=error["component"],
            severity="high" if "connection" in error["message"].lower() else "medium",
            session_id="session-001",
            user_id="user-alice"
        )
    
    print("\n📈 Generating Analytics Reports...")
    
    # Get real-time metrics
    realtime = await analytics.get_realtime_metrics()
    print(f"\n🔴 Real-time Metrics:")
    print(f"   Active Sessions: {realtime['active_sessions']}")
    print(f"   Active Users: {realtime['active_users']}")
    print(f"   Messages/min: {realtime['messages_per_minute']}")
    print(f"   Errors/min: {realtime['errors_per_minute']}")
    print(f"   Avg Response Time: {realtime['avg_response_time']}s")
    print(f"   Memory Usage: {realtime['memory_usage_mb']} MB")
    
    # Get session analytics
    session_analytics = await analytics.get_session_analytics()
    print(f"\n📊 Session Analytics:")
    print(f"   Total Sessions: {session_analytics['summary']['total_sessions']}")
    print(f"   Total Messages: {session_analytics['summary']['total_messages']}")
    print(f"   Unique Users: {session_analytics['summary']['unique_users']}")
    print(f"   Avg Messages/Session: {session_analytics['summary']['avg_messages_per_session']:.1f}")
    
    # Get model usage analytics
    model_analytics = await analytics.get_model_usage_analytics()
    print(f"\n💰 Model Usage Analytics:")
    print(f"   Total Cost: ${model_analytics['total_cost']:.4f}")
    print(f"   Total Requests: {model_analytics['summary']['total_requests']}")
    print(f"   Total Tokens: {model_analytics['summary']['total_tokens']:,}")
    print(f"   Models Used: {model_analytics['summary']['models_count']}")
    
    print("\n📋 Model Usage Breakdown:")
    for usage in model_analytics['usage']:
        print(f"   {usage['model_name']} ({usage['provider']}):")
        print(f"     Requests: {usage['request_count']}")
        print(f"     Tokens: {usage['total_tokens']:,}")
        print(f"     Cost: ${float(usage['estimated_cost']):.4f}")
        print(f"     Avg Response: {float(usage['avg_response_time']):.1f}s")
    
    print("\n🎯 Key Performance Indicators:")
    
    # Calculate KPIs
    total_requests = model_analytics['summary']['total_requests']
    total_cost = model_analytics['total_cost']
    total_tokens = model_analytics['summary']['total_tokens']
    
    if total_requests > 0:
        avg_cost_per_request = total_cost / total_requests
        avg_tokens_per_request = total_tokens / total_requests
        
        print(f"   Cost per Request: ${avg_cost_per_request:.4f}")
        print(f"   Tokens per Request: {avg_tokens_per_request:.0f}")
        print(f"   Cost per 1K Tokens: ${(total_cost / total_tokens * 1000):.4f}")
    
    # User engagement metrics
    sessions_per_user = session_analytics['summary']['total_sessions'] / session_analytics['summary']['unique_users']
    messages_per_user = session_analytics['summary']['total_messages'] / session_analytics['summary']['unique_users']
    
    print(f"   Sessions per User: {sessions_per_user:.1f}")
    print(f"   Messages per User: {messages_per_user:.1f}")
    
    print("\n✅ Analytics Demo Complete!")
    print("=" * 50)
    
    return {
        "realtime": realtime,
        "sessions": session_analytics,
        "models": model_analytics,
        "kpis": {
            "avg_cost_per_request": avg_cost_per_request if total_requests > 0 else 0,
            "avg_tokens_per_request": avg_tokens_per_request if total_requests > 0 else 0,
            "sessions_per_user": sessions_per_user,
            "messages_per_user": messages_per_user
        }
    }


async def demo_alerting_system():
    """Demonstrate the alerting system."""
    print("\n🚨 Alerting System Demo")
    print("-" * 30)
    
    # Mock alert rules
    alert_rules = [
        {
            "rule_id": "high_error_rate",
            "name": "High Error Rate",
            "metric": "error_rate",
            "threshold": 5.0,
            "condition": ">",
            "severity": "high"
        },
        {
            "rule_id": "slow_response",
            "name": "Slow Response Time",
            "metric": "avg_response_time",
            "threshold": 10.0,
            "condition": ">",
            "severity": "medium"
        },
        {
            "rule_id": "high_cost",
            "name": "High Daily Cost",
            "metric": "daily_cost",
            "threshold": 100.0,
            "condition": ">",
            "severity": "medium"
        }
    ]
    
    # Mock current metrics
    current_metrics = {
        "error_rate": 2.5,  # Below threshold
        "avg_response_time": 12.0,  # Above threshold
        "daily_cost": 150.0,  # Above threshold
    }
    
    print("Alert Rules:")
    for rule in alert_rules:
        print(f"  {rule['name']}: {rule['metric']} {rule['condition']} {rule['threshold']} ({rule['severity']})")
    
    print("\nCurrent Metrics:")
    for metric, value in current_metrics.items():
        print(f"  {metric}: {value}")
    
    print("\nTriggered Alerts:")
    triggered_alerts = []
    
    for rule in alert_rules:
        metric_value = current_metrics.get(rule['metric'], 0)
        threshold = rule['threshold']
        condition = rule['condition']
        
        triggered = False
        if condition == ">" and metric_value > threshold:
            triggered = True
        elif condition == "<" and metric_value < threshold:
            triggered = True
        elif condition == "==" and metric_value == threshold:
            triggered = True
        
        if triggered:
            alert = {
                "rule_id": rule['rule_id'],
                "rule_name": rule['name'],
                "metric": rule['metric'],
                "current_value": metric_value,
                "threshold": threshold,
                "severity": rule['severity'],
                "timestamp": datetime.now().isoformat()
            }
            triggered_alerts.append(alert)
            
            severity_emoji = "🔴" if rule['severity'] == "high" else "🟡"
            print(f"  {severity_emoji} {rule['name']}: {metric_value} {condition} {threshold}")
    
    if not triggered_alerts:
        print("  ✅ No alerts triggered")
    
    return triggered_alerts


async def demo_performance_monitoring():
    """Demonstrate performance monitoring."""
    print("\n⚡ Performance Monitoring Demo")
    print("-" * 35)
    
    # Mock performance metrics over time
    performance_data = []
    base_time = datetime.now() - timedelta(hours=1)
    
    for i in range(12):  # 12 data points over 1 hour (5-minute intervals)
        timestamp = base_time + timedelta(minutes=i * 5)
        
        # Simulate varying performance metrics
        response_time = 2.0 + (i % 3) * 0.5 + (0.1 if i > 8 else 0)  # Slight degradation
        memory_usage = 200 + (i * 5) + (i % 2) * 10  # Gradual increase
        cpu_usage = 15 + (i % 4) * 5 + (20 if i > 9 else 0)  # Spike at end
        
        performance_data.append({
            "timestamp": timestamp,
            "response_time": response_time,
            "memory_usage_mb": memory_usage,
            "cpu_usage_percent": cpu_usage,
            "active_sessions": 3 + (i % 2),
            "requests_per_minute": 50 + (i * 2) + (i % 3) * 5
        })
    
    print("Performance Metrics (Last Hour):")
    print("Time        | Response | Memory  | CPU   | Sessions | Req/min")
    print("-" * 65)
    
    for data in performance_data[-6:]:  # Show last 6 data points (30 minutes)
        time_str = data["timestamp"].strftime("%H:%M")
        print(f"{time_str}       | {data['response_time']:.1f}s     | {data['memory_usage_mb']:.0f} MB | {data['cpu_usage_percent']:.0f}%   | {data['active_sessions']}        | {data['requests_per_minute']}")
    
    # Calculate trends
    recent_data = performance_data[-3:]  # Last 3 data points
    older_data = performance_data[-6:-3]  # Previous 3 data points
    
    avg_recent_response = sum(d['response_time'] for d in recent_data) / len(recent_data)
    avg_older_response = sum(d['response_time'] for d in older_data) / len(older_data)
    
    avg_recent_memory = sum(d['memory_usage_mb'] for d in recent_data) / len(recent_data)
    avg_older_memory = sum(d['memory_usage_mb'] for d in older_data) / len(older_data)
    
    print(f"\nTrends (Last 15 min vs Previous 15 min):")
    
    response_trend = "📈" if avg_recent_response > avg_older_response else "📉"
    memory_trend = "📈" if avg_recent_memory > avg_older_memory else "📉"
    
    print(f"  Response Time: {avg_recent_response:.1f}s vs {avg_older_response:.1f}s {response_trend}")
    print(f"  Memory Usage: {avg_recent_memory:.0f} MB vs {avg_older_memory:.0f} MB {memory_trend}")
    
    # Performance recommendations
    print(f"\n💡 Performance Recommendations:")
    
    if avg_recent_response > 3.0:
        print("  • Response time is elevated - consider scaling or optimization")
    
    if avg_recent_memory > 300:
        print("  • Memory usage is high - monitor for memory leaks")
    
    latest_cpu = performance_data[-1]['cpu_usage_percent']
    if latest_cpu > 50:
        print("  • CPU usage is high - check for resource-intensive operations")
    
    if all(d['response_time'] < 2.5 for d in recent_data):
        print("  • Performance is optimal ✅")
    
    return performance_data


async def main():
    """Run the complete analytics demo."""
    print("🎯 Cosmos Web Chat Analytics System Demo")
    print("=" * 60)
    
    # Run main analytics workflow
    analytics_results = await demo_analytics_workflow()
    
    # Run alerting demo
    alerts = await demo_alerting_system()
    
    # Run performance monitoring demo
    performance_data = await demo_performance_monitoring()
    
    print(f"\n📊 Demo Summary:")
    print(f"   Sessions Tracked: {analytics_results['sessions']['summary']['total_sessions']}")
    print(f"   Total Cost: ${analytics_results['models']['total_cost']:.4f}")
    print(f"   Alerts Triggered: {len(alerts)}")
    print(f"   Performance Data Points: {len(performance_data)}")
    
    print(f"\n🎉 Demo completed successfully!")
    print(f"   The analytics system provides comprehensive monitoring")
    print(f"   for chat sessions, model usage, errors, and performance.")


if __name__ == "__main__":
    asyncio.run(main())