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
class AnalysisResult:
    """Structured extraction from Phase 1 (Analyze)."""
    session_intent: str = ""
    decisions: list[Decision] = field(default_factory=list)
    file_changes: list[FileChange] = field(default_factory=list)
    error_chains: list[ErrorChain] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)
    failed_attempts: list[FailedAttempt] = field(default_factory=list)
    current_state: str = ""
    current_task: str = ""
    next_steps: list[str] = field(default_factory=list)
    agent_team_state: str = ""
    total_turns: int = 0
    recent_turn_start: int = 0  # index where "recent 10" begins
    token_count: int = 0
    model: str = ""
    context_window: int = 200_000


@dataclass
class QualityScore:
    """Context quality assessment."""
    overall: float  # 0-10
    structure: float  # how well organized
    density: float  # information per token
    recency: float  # critical info in attention-favorable positions
    completeness: float  # all decisions/state captured
    cache_friendliness: float  # stable prefix for KV-cache


@dataclass
class EngineerResult:
    """Result of the full engineering pipeline."""
    original_tokens: int
    engineered_tokens: int
    quality_before: QualityScore
    quality_after: QualityScore
    sections_generated: int
    llm_model_used: str
    llm_cost_usd: float
    backup_path: str = ""
