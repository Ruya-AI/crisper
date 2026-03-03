"""Core data types for Crisper Context."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Decision:
    """A decision extracted from conversation history."""
    summary: str
    rationale: str = ""
    turn_index: int = 0


@dataclass
class FileChange:
    """A file modification in the artifact trail."""
    path: str
    action: str  # "created" | "modified" | "deleted"
    summary: str = ""
    turn_index: int = 0


@dataclass
class ErrorChain:
    """A causal chain: error → investigation → resolution."""
    error: str
    cause: str = ""
    fix: str = ""
    turn_index: int = 0


@dataclass
class Reference:
    """A URL, doc path, or external reference worth preserving."""
    url: str
    context: str = ""
    turn_index: int = 0


@dataclass
class FailedAttempt:
    """A failed approach — preserved to prevent repetition."""
    what: str
    why_failed: str = ""
    turn_index: int = 0


@dataclass
class TopicSegment:
    """A segment of conversation grouped by topic."""
    topic: str
    start_index: int
    end_index: int
    summary: str = ""
    message_indices: list[int] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


@dataclass
class MessageScore:
    """Importance score for a single message."""
    line_index: int
    score: float  # 0.0 - 1.0
    category: str
    reason: str = ""
    is_sacred: bool = False


@dataclass
class AnalysisResult:
    """Structured extraction from Phase 1 (Analyze)."""
    session_intent: str = ""
    decisions: list[Decision] = field(default_factory=list)
    file_changes: list[FileChange] = field(default_factory=list)
    error_chains: list[ErrorChain] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)
    failed_attempts: list[FailedAttempt] = field(default_factory=list)
    topics: list[TopicSegment] = field(default_factory=list)
    current_state: str = ""
    current_task: str = ""
    next_steps: list[str] = field(default_factory=list)
    agent_team_state: str = ""
    total_turns: int = 0
    recent_turn_start: int = 0
    token_count: int = 0
    model: str = ""
    context_window: int = 200_000
    session_id: str = ""


@dataclass
class ValidationCheck:
    """A single validation check result."""
    name: str
    passed: bool
    detail: str = ""


@dataclass
class ValidationResult:
    """Result of validating a restructured session against the original."""
    is_valid: bool
    checks: list[ValidationCheck] = field(default_factory=list)
    missing_decisions: list[str] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)
    missing_references: list[str] = field(default_factory=list)
    orphaned_tool_results: list[str] = field(default_factory=list)
    broken_uuid_chains: list[str] = field(default_factory=list)
    recent_turns_match: bool = True
    original_tokens: int = 0
    restructured_tokens: int = 0


@dataclass
class WriteResult:
    """Result of writing a restructured session."""
    success: bool
    original_path: str
    backup_path: str = ""
    bytes_before: int = 0
    bytes_after: int = 0
    error: str = ""


@dataclass
class QualityScore:
    """Context quality assessment."""
    overall: float = 0.0
    structure: float = 0.0
    density: float = 0.0
    recency: float = 0.0
    completeness: float = 0.0
    cache_friendliness: float = 0.0
