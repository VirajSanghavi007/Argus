"""
Backward-compatible client to separate database service.
Delegates all operations to src.database.service.
"""

from ...database import service

# Expose service functions as module-level functions for backward compatibility
init_db = service.init_db
replace_alerts = service.replace_alerts
load_alerts = service.load_alerts
has_alerts = service.has_alerts
record_decision = service.record_decision
current_decisions = service.current_decisions
decision_history = service.decision_history
decision_counts = service.decision_counts
