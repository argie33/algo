"""
yfinance Circuit Breaker - Prevent runaway API costs
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

class YFinanceCircuitBreaker:
    """Prevents excessive yfinance calls that could cause runaway AWS costs"""
    
    STATE_FILE = "/tmp/yfinance_state.json"  # Local in Lambda/ECS
    
    # Thresholds (daily)
    MAX_CALLS_PER_DAY = 1000  # Roughly 500 stocks * 2 calls
    MAX_FAILURES_PER_DAY = 100
    MAX_TIMEOUTS_PER_DAY = 50
    
    def __init__(self):
        self.state = self._load_state()
    
    def _load_state(self):
        """Load or create state file"""
        if os.path.exists(self.STATE_FILE):
            try:
                with open(self.STATE_FILE) as f:
                    state = json.load(f)
                    # Reset if new day
                    if self._is_new_day(state.get('date')):
                        return self._new_state()
                    return state
            except:
                return self._new_state()
        return self._new_state()
    
    def _new_state(self):
        """Create fresh state for new day"""
        return {
            'date': datetime.now().isoformat(),
            'calls': 0,
            'failures': 0,
            'timeouts': 0,
            'circuit_open': False
        }
    
    def _is_new_day(self, date_str):
        """Check if state is from a different day"""
        if not date_str:
            return True
        try:
            state_date = datetime.fromisoformat(date_str).date()
            return state_date != datetime.now().date()
        except:
            return True
    
    def _save_state(self):
        """Persist state to file"""
        with open(self.STATE_FILE, 'w') as f:
            json.dump(self.state, f)
    
    def check(self):
        """Check if circuit breaker allows operations"""
        if self.state['circuit_open']:
            raise RuntimeError(
                f"Circuit breaker OPEN - daily limits exceeded:\n"
                f"  Calls: {self.state['calls']}/{self.MAX_CALLS_PER_DAY}\n"
                f"  Failures: {self.state['failures']}/{self.MAX_FAILURES_PER_DAY}\n"
                f"  Timeouts: {self.state['timeouts']}/{self.MAX_TIMEOUTS_PER_DAY}\n"
                f"Reset at midnight UTC"
            )
        
        # Check individual limits
        if self.state['calls'] >= self.MAX_CALLS_PER_DAY:
            self.state['circuit_open'] = True
            self._save_state()
            raise RuntimeError(f"yfinance daily call limit ({self.MAX_CALLS_PER_DAY}) exceeded")
        
        if self.state['failures'] >= self.MAX_FAILURES_PER_DAY:
            self.state['circuit_open'] = True
            self._save_state()
            raise RuntimeError(f"Too many yfinance failures ({self.state['failures']}) - circuit open")
        
        if self.state['timeouts'] >= self.MAX_TIMEOUTS_PER_DAY:
            self.state['circuit_open'] = True
            self._save_state()
            raise RuntimeError(f"Too many yfinance timeouts ({self.state['timeouts']}) - circuit open")
    
    def record_call(self):
        """Record a yfinance call"""
        self.check()
        self.state['calls'] += 1
        self._save_state()
    
    def record_failure(self):
        """Record a yfinance failure"""
        self.state['failures'] += 1
        self._save_state()
    
    def record_timeout(self):
        """Record a yfinance timeout"""
        self.state['timeouts'] += 1
        self._save_state()
    
    def status(self):
        """Return current status"""
        return {
            'date': self.state['date'],
            'calls': f"{self.state['calls']}/{self.MAX_CALLS_PER_DAY}",
            'failures': f"{self.state['failures']}/{self.MAX_FAILURES_PER_DAY}",
            'timeouts': f"{self.state['timeouts']}/{self.MAX_TIMEOUTS_PER_DAY}",
            'circuit': 'OPEN' if self.state['circuit_open'] else 'CLOSED'
        }

# Example usage in loaders:
# breaker = YFinanceCircuitBreaker()
# try:
#     breaker.check()
#     data = yf.download(...)
#     breaker.record_call()
# except Exception as e:
#     if 'timeout' in str(e).lower():
#         breaker.record_timeout()
#     else:
#         breaker.record_failure()
