"""
Issue 4.1: Orchestrator Runtime Profiling

Measures execution time of each orchestrator phase.
Identifies bottlenecks and ensures trading window is met (must complete by 4:00 PM ET).

Usage:
  python orchestrator_profiler.py --mode paper --dry-run --profile
"""

import sys
import time
import json
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from algo_orchestrator import Orchestrator


class OrchestratorProfiler:
    """Measures and profiles orchestrator execution time."""

    def __init__(self):
        self.timings = {}
        self.phase_order = [
            'Phase 1: Data Load & Validation',
            'Phase 2: Technical Indicators & Signals',
            'Phase 3: Risk & Filter Pipeline',
            'Phase 4: Position Sizing & Entry',
            'Phase 5: Exit Management & Risk',
            'Phase 6: Logging & Snapshots',
            'Phase 7: Performance Analysis'
        ]

    def profile_orchestrator(self, mode='paper', dry_run=True):
        """Run orchestrator with timing on each phase."""

        print("\n" + "="*70)
        print(f"ORCHESTRATOR PROFILER - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*70)
        print(f"Mode: {mode} | Dry-run: {dry_run}\n")

        # Create orchestrator
        orchestrator = Orchestrator()

        # Override phase execution to add timing
        original_run = orchestrator.run

        def timed_run():
            """Wrapper to time the orchestrator run."""
            start_time = time.time()

            try:
                original_run()
            except Exception as e:
                print(f"\n❌ Orchestrator failed: {e}")
                raise

            total_time = time.time() - start_time
            return total_time

        # Run with timing
        print("Starting orchestrator...")
        start = time.time()
        try:
            orchestrator.run()
        except Exception as e:
            print(f"Error: {e}")
            return

        total_duration = time.time() - start

        # Extract phase timings from orchestrator results
        self._extract_phase_timings(orchestrator)

        # Generate report
        self._generate_report(total_duration)

    def _extract_phase_timings(self, orchestrator):
        """Extract timing information from orchestrator execution."""

        # Look for phase_results in orchestrator state
        if hasattr(orchestrator, 'phase_results') and orchestrator.phase_results:
            for phase_num, result in orchestrator.phase_results.items():
                if isinstance(result, dict) and 'duration_seconds' in result:
                    phase_name = self.phase_order[phase_num - 1] if phase_num <= 7 else f"Phase {phase_num}"
                    self.timings[phase_name] = result['duration_seconds']

        # If no phase timings, provide measurement guidance
        if not self.timings:
            print("\n⚠️  Phase timings not captured (orchestrator doesn't track them yet)")
            print("   Recommendation: Add timing instrumentation to algo_orchestrator.py")

    def _generate_report(self, total_duration):
        """Generate profiling report."""

        print("\n" + "="*70)
        print("ORCHESTRATOR PROFILING REPORT")
        print("="*70)

        if not self.timings:
            print(f"\n📊 Total Execution Time: {total_duration:.2f} seconds")
            print("\n⚠️  Phase-level timing not available")
            print("   (orchestrator doesn't instrument timing internally)")
            self._print_recommendations(total_duration)
            return

        print("\n📊 Phase Execution Times:")
        print("-" * 70)
        print(f"{'Phase':<40} {'Duration':>15} {'% Total':>10}")
        print("-" * 70)

        for phase_name, duration in sorted(self.timings.items()):
            pct = (duration / total_duration * 100) if total_duration > 0 else 0
            print(f"{phase_name:<40} {duration:>14.2f}s {pct:>9.1f}%")

        print("-" * 70)
        print(f"{'TOTAL':<40} {total_duration:>14.2f}s {100.0:>9.1f}%")
        print("=" * 70)

        self._print_analysis(total_duration)
        self._print_recommendations(total_duration)

    def _print_analysis(self, total_duration):
        """Analyze profiling results."""

        print("\n📈 Analysis:")

        # Find slowest phase
        if self.timings:
            slowest = max(self.timings.items(), key=lambda x: x[1])
            print(f"\n  Slowest Phase: {slowest[0]} ({slowest[1]:.2f}s)")

            # Find fastest phase
            fastest = min(self.timings.items(), key=lambda x: x[1])
            print(f"  Fastest Phase: {fastest[0]} ({fastest[1]:.2f}s)")

        # Trading window check
        trading_deadline = datetime.now().replace(hour=16, minute=0, second=0, microsecond=0)  # 4:00 PM ET
        execution_time = timedelta(seconds=total_duration)

        print(f"\n  Total Execution: {total_duration:.2f} seconds")
        print(f"  Trading Deadline: 4:00 PM ET (must finish before positions execute)")

        if total_duration < 300:  # < 5 minutes
            print(f"  ✅ PASS: Completes in {total_duration:.0f}s (plenty of time)")
        elif total_duration < 600:  # < 10 minutes
            print(f"  ⚠️  WARNING: Takes {total_duration:.0f}s (tight but acceptable)")
        else:  # > 10 minutes
            print(f"  ❌ FAIL: Takes {total_duration:.0f}s (TOO SLOW - must optimize)")

    def _print_recommendations(self, total_duration):
        """Print optimization recommendations."""

        print("\n💡 Recommendations:")

        if total_duration > 300:
            print("\n  🔴 Critical: Orchestrator is too slow!")
            print("     Recommended optimizations:")
            print("     1. Profile individual queries (see slowest SQL)")
            print("     2. Add database indexes on frequently-queried columns")
            print("     3. Consider caching repeated queries")
            print("     4. Parallelize independent loader operations")

        if self.timings and 'Phase 2' in str(list(self.timings.keys())):
            slowest_phase = max(self.timings.items(), key=lambda x: x[1])
            if 'Phase 2' in slowest_phase[0]:
                print("\n  ⚠️  Phase 2 (Technical Indicators) is slow:")
                print("     - Check if indicator calculations are unoptimized")
                print("     - Consider vectorizing with NumPy/Pandas")

        print("\n  General optimizations:")
        print("  - Run `ANALYZE` on PostgreSQL to update query planner stats")
        print("  - Check CloudWatch metrics for Lambda cold start duration")
        print("  - Monitor RDS CPU usage during execution")

    def save_report(self, output_file='profiling_results.json'):
        """Save profiling results to JSON."""

        report = {
            'timestamp': datetime.now().isoformat(),
            'total_duration_seconds': sum(self.timings.values()),
            'phase_timings': self.timings,
            'status': 'profiling_complete'
        }

        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)

        print(f"\n✅ Results saved to: {output_file}")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Profile orchestrator execution time')
    parser.add_argument('--mode', default='paper', choices=['paper', 'live', 'backtest'],
                      help='Orchestrator mode')
    parser.add_argument('--dry-run', action='store_true', help='Dry run without executing trades')
    parser.add_argument('--save', default='profiling_results.json', help='Save results to file')

    args = parser.parse_args()

    profiler = OrchestratorProfiler()
    try:
        profiler.profile_orchestrator(mode=args.mode, dry_run=args.dry_run)
        profiler.save_report(args.save)
    except Exception as e:
        print(f"\n❌ Profiling failed: {e}")
        sys.exit(1)
