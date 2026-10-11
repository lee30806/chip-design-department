"""coding agent 실행기는 pipeline/agents/runner.py로 옮겼다. P0 실험 스크립트가 쓰던 이름을 그대로 내보낸다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from pipeline.agents.runner import (  # noqa: E402,F401
    KICKOFF, AgentConfig, AgentRun, load_agents, run_agent, scope_violations, snapshot)
