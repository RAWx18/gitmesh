"""
Data models for Cosmos response and repository context.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional


@dataclass
class FileLocation:
    """Location information for indexed files."""
    start_offset: int
    end_offset: int
    size: int
    checksum: str


@dataclass
class RepositoryContext:
    """Complete repository context for Cosmos processing."""
    repo_url: str
    repo_name: str
    summary: str
    content: str
    tree_structure: str
    metadata: Dict[str, Any]
    file_index: Dict[str, FileLocation]
    total_files: int
    total_size: int


@dataclass
class VirtualFile:
    """Virtual file representation for the intelligent VFS."""
    path: str
    content: str
    size: int
    last_modified: datetime
    file_type: str
    encoding: str = "utf-8"


@dataclass
class ModelInfo:
    """Information about available AI models."""
    name: str
    provider: str
    max_tokens: int
    supports_streaming: bool = False


@dataclass
class PerformanceMetrics:
    """Performance metrics for monitoring."""
    response_time: float
    memory_usage: float
    redis_operations: int
    file_accesses: int
    timestamp: datetime