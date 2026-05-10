# Algo orchestrator Lambda package
# Re-export the main orchestrator module so "from algo_orchestrator import Orchestrator" works
import sys
import os

# Add parent directory to path so we can import the root algo_orchestrator module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from algo_orchestrator import Orchestrator

__all__ = ['Orchestrator']
