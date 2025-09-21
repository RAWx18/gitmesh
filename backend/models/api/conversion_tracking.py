"""
Conversion Tracking Models for Progressive Shell-to-Web Conversion

Models for tracking CLI operations conversion to web equivalents,
progress indicators, and conversion effectiveness metrics.
"""

from typing import List, Optional, Dict, Any, Set
from pydantic import BaseModel, Field, validator
from datetime import datetime
from enum import Enum


class ConversionType(str, Enum):
    """Types of CLI operations that can be converted."""
    SHELL_COMMAND = "shell_command"
    FILE_OPERATION = "file_operation"
    GIT_OPERATION = "git_operation"
    INTERACTIVE_PROMPT = "interactive_prompt"
    DIRECTORY_OPERATION = "directory_operation"
    SEARCH_OPERATION = "search_operation"


class ConversionStatus(str, Enum):
    """Status of conversion operations."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class ConversionPriority(str, Enum):
    """Priority levels for conversion operations."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConversionOperation(BaseModel):
    """Individual conversion operation tracking."""
    id: str = Field(..., description="Unique operation identifier")
    operation_type: ConversionType = Field(..., description="Type of operation being converted")
    original_command: str = Field(..., description="Original CLI command or operation")
    converted_equivalent: Optional[str] = Field(default=None, description="Web-safe equivalent operation")
    status: ConversionStatus = Field(default=ConversionStatus.PENDING, description="Current conversion status")
    priority: ConversionPriority = Field(default=ConversionPriority.MEDIUM, description="Conversion priority")
    
    # Timing information
    created_at: datetime = Field(default_factory=datetime.now, description="When operation was first encountered")
    started_at: Optional[datetime] = Field(default=None, description="When conversion started")
    completed_at: Optional[datetime] = Field(default=None, description="When conversion completed")
    
    # Context information
    session_id: str = Field(..., description="Chat session where operation occurred")
    user_id: str = Field(..., description="User who triggered the operation")
    context_files: List[str] = Field(default_factory=list, description="Files in context when operation occurred")
    
    # Conversion details
    conversion_notes: Optional[str] = Field(default=None, description="Notes about the conversion process")
    error_message: Optional[str] = Field(default=None, description="Error message if conversion failed")
    web_equivalent_output: Optional[str] = Field(default=None, description="Output from web equivalent operation")
    
    # Effectiveness metrics
    user_satisfaction: Optional[int] = Field(default=None, ge=1, le=5, description="User satisfaction rating (1-5)")
    conversion_accuracy: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Accuracy of conversion (0-1)")
    performance_impact: Optional[float] = Field(default=None, description="Performance impact in milliseconds")
    
    # Metadata
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional operation metadata")
    
    @validator('original_command')
    def validate_original_command(cls, v):
        if not v.strip():
            raise ValueError("Original command cannot be empty")
        return v.strip()


class ConversionProgress(BaseModel):
    """Overall conversion progress for a session or system."""
    session_id: Optional[str] = Field(default=None, description="Session ID (None for system-wide)")
    
    # Overall statistics
    total_operations: int = Field(default=0, description="Total number of operations encountered")
    converted_operations: int = Field(default=0, description="Number of successfully converted operations")
    failed_operations: int = Field(default=0, description="Number of failed conversions")
    pending_operations: int = Field(default=0, description="Number of pending conversions")
    
    # Progress metrics
    conversion_percentage: float = Field(default=0.0, ge=0.0, le=100.0, description="Overall conversion percentage")
    success_rate: float = Field(default=0.0, ge=0.0, le=100.0, description="Success rate of attempted conversions")
    
    # Timing information
    last_conversion: Optional[datetime] = Field(default=None, description="Timestamp of last conversion")
    average_conversion_time: Optional[float] = Field(default=None, description="Average conversion time in seconds")
    
    # Breakdown by type
    operations_by_type: Dict[ConversionType, int] = Field(default_factory=dict, description="Operations count by type")
    success_by_type: Dict[ConversionType, int] = Field(default_factory=dict, description="Success count by type")
    
    # Priority breakdown
    operations_by_priority: Dict[ConversionPriority, int] = Field(default_factory=dict, description="Operations by priority")
    
    # Recent activity
    recent_operations: List[str] = Field(default_factory=list, description="Recent operation IDs")
    
    # Quality metrics
    average_user_satisfaction: Optional[float] = Field(default=None, ge=1.0, le=5.0, description="Average user satisfaction")
    average_accuracy: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Average conversion accuracy")
    
    def calculate_metrics(self, operations: List[ConversionOperation]):
        """Calculate metrics from a list of operations."""
        if not operations:
            return
        
        self.total_operations = len(operations)
        self.converted_operations = len([op for op in operations if op.status == ConversionStatus.COMPLETED])
        self.failed_operations = len([op for op in operations if op.status == ConversionStatus.FAILED])
        self.pending_operations = len([op for op in operations if op.status == ConversionStatus.PENDING])
        
        # Calculate percentages
        if self.total_operations > 0:
            self.conversion_percentage = (self.converted_operations / self.total_operations) * 100
            
        attempted_operations = self.converted_operations + self.failed_operations
        if attempted_operations > 0:
            self.success_rate = (self.converted_operations / attempted_operations) * 100
        
        # Calculate timing metrics
        completed_ops = [op for op in operations if op.status == ConversionStatus.COMPLETED and op.started_at and op.completed_at]
        if completed_ops:
            self.last_conversion = max(op.completed_at for op in completed_ops)
            conversion_times = [(op.completed_at - op.started_at).total_seconds() for op in completed_ops]
            self.average_conversion_time = sum(conversion_times) / len(conversion_times)
        
        # Calculate type breakdowns
        self.operations_by_type = {}
        self.success_by_type = {}
        for op_type in ConversionType:
            type_ops = [op for op in operations if op.operation_type == op_type]
            self.operations_by_type[op_type] = len(type_ops)
            self.success_by_type[op_type] = len([op for op in type_ops if op.status == ConversionStatus.COMPLETED])
        
        # Calculate priority breakdown
        self.operations_by_priority = {}
        for priority in ConversionPriority:
            self.operations_by_priority[priority] = len([op for op in operations if op.priority == priority])
        
        # Calculate quality metrics
        rated_ops = [op for op in operations if op.user_satisfaction is not None]
        if rated_ops:
            self.average_user_satisfaction = sum(op.user_satisfaction for op in rated_ops) / len(rated_ops)
        
        accurate_ops = [op for op in operations if op.conversion_accuracy is not None]
        if accurate_ops:
            self.average_accuracy = sum(op.conversion_accuracy for op in accurate_ops) / len(accurate_ops)
        
        # Set recent operations (last 10)
        recent_ops = sorted(operations, key=lambda op: op.created_at, reverse=True)[:10]
        self.recent_operations = [op.id for op in recent_ops]


class ConversionMetrics(BaseModel):
    """Detailed conversion effectiveness metrics."""
    
    # Time-based metrics
    daily_conversions: Dict[str, int] = Field(default_factory=dict, description="Conversions per day (YYYY-MM-DD)")
    hourly_conversions: Dict[int, int] = Field(default_factory=dict, description="Conversions per hour (0-23)")
    
    # Command popularity
    most_common_commands: List[Dict[str, Any]] = Field(default_factory=list, description="Most frequently converted commands")
    most_failed_commands: List[Dict[str, Any]] = Field(default_factory=list, description="Most frequently failed commands")
    
    # User engagement
    users_with_conversions: int = Field(default=0, description="Number of users with conversion activity")
    sessions_with_conversions: int = Field(default=0, description="Number of sessions with conversions")
    
    # Performance metrics
    average_response_time: Optional[float] = Field(default=None, description="Average response time for conversions")
    conversion_throughput: Optional[float] = Field(default=None, description="Conversions per minute")
    
    # Quality trends
    satisfaction_trend: List[Dict[str, Any]] = Field(default_factory=list, description="User satisfaction over time")
    accuracy_trend: List[Dict[str, Any]] = Field(default_factory=list, description="Conversion accuracy over time")
    
    # System health
    error_rate: float = Field(default=0.0, ge=0.0, le=100.0, description="Overall error rate percentage")
    system_load_impact: Optional[float] = Field(default=None, description="Impact on system load")
    
    # Conversion coverage
    command_coverage: Dict[str, float] = Field(default_factory=dict, description="Coverage percentage by command type")
    feature_completeness: float = Field(default=0.0, ge=0.0, le=100.0, description="Overall feature completeness percentage")


class ConversionNote(BaseModel):
    """Documentation note for conversion processes."""
    id: str = Field(..., description="Unique note identifier")
    operation_id: str = Field(..., description="Related operation ID")
    note_type: str = Field(..., description="Type of note (info, warning, error, success)")
    title: str = Field(..., description="Note title")
    content: str = Field(..., description="Note content")
    author: str = Field(..., description="Note author (user or system)")
    created_at: datetime = Field(default_factory=datetime.now, description="Note creation time")
    tags: List[str] = Field(default_factory=list, description="Note tags for categorization")
    is_public: bool = Field(default=True, description="Whether note is visible to other users")
    
    @validator('note_type')
    def validate_note_type(cls, v):
        allowed_types = ["info", "warning", "error", "success", "tip", "documentation"]
        if v not in allowed_types:
            raise ValueError(f"Note type must be one of {allowed_types}")
        return v


class ConversionReport(BaseModel):
    """Comprehensive conversion tracking report."""
    report_id: str = Field(..., description="Unique report identifier")
    generated_at: datetime = Field(default_factory=datetime.now, description="Report generation time")
    report_period: Dict[str, datetime] = Field(..., description="Start and end dates for report")
    
    # Summary statistics
    summary: ConversionProgress = Field(..., description="Overall progress summary")
    metrics: ConversionMetrics = Field(..., description="Detailed metrics")
    
    # Detailed breakdowns
    operations: List[ConversionOperation] = Field(default_factory=list, description="All operations in period")
    notes: List[ConversionNote] = Field(default_factory=list, description="All notes in period")
    
    # Insights and recommendations
    insights: List[str] = Field(default_factory=list, description="Generated insights")
    recommendations: List[str] = Field(default_factory=list, description="Improvement recommendations")
    
    # Export metadata
    generated_by: str = Field(..., description="User or system that generated report")
    export_format: str = Field(default="json", description="Report export format")
    
    def add_insight(self, insight: str):
        """Add an insight to the report."""
        if insight not in self.insights:
            self.insights.append(insight)
    
    def add_recommendation(self, recommendation: str):
        """Add a recommendation to the report."""
        if recommendation not in self.recommendations:
            self.recommendations.append(recommendation)


class ConversionRequest(BaseModel):
    """Request to track a new conversion operation."""
    operation_type: ConversionType = Field(..., description="Type of operation to convert")
    original_command: str = Field(..., description="Original CLI command")
    session_id: str = Field(..., description="Chat session ID")
    user_id: str = Field(..., description="User ID")
    priority: ConversionPriority = Field(default=ConversionPriority.MEDIUM, description="Conversion priority")
    context_files: List[str] = Field(default_factory=list, description="Files in context")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


class ConversionUpdateRequest(BaseModel):
    """Request to update an existing conversion operation."""
    operation_id: str = Field(..., description="Operation ID to update")
    status: Optional[ConversionStatus] = Field(default=None, description="New status")
    converted_equivalent: Optional[str] = Field(default=None, description="Web equivalent operation")
    conversion_notes: Optional[str] = Field(default=None, description="Conversion notes")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
    web_equivalent_output: Optional[str] = Field(default=None, description="Output from web operation")
    user_satisfaction: Optional[int] = Field(default=None, ge=1, le=5, description="User satisfaction rating")
    conversion_accuracy: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Conversion accuracy")
    performance_impact: Optional[float] = Field(default=None, description="Performance impact in ms")


class ConversionListResponse(BaseModel):
    """Response for listing conversion operations."""
    operations: List[ConversionOperation] = Field(..., description="List of operations")
    total_count: int = Field(..., description="Total number of operations")
    page: int = Field(default=1, description="Current page number")
    page_size: int = Field(default=50, description="Number of items per page")
    has_next: bool = Field(default=False, description="Whether there are more pages")
    progress: ConversionProgress = Field(..., description="Overall progress summary")


class ConversionStatsResponse(BaseModel):
    """Response for conversion statistics."""
    progress: ConversionProgress = Field(..., description="Progress summary")
    metrics: ConversionMetrics = Field(..., description="Detailed metrics")
    recent_operations: List[ConversionOperation] = Field(..., description="Recent operations")
    top_commands: List[Dict[str, Any]] = Field(..., description="Most common commands")
    conversion_trends: Dict[str, Any] = Field(..., description="Conversion trends over time")