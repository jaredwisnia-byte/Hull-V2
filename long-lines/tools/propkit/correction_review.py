"""Pre-application correction contracts: explain, measure, constrain, or roll back.

This supervises numerical decisions; it is not an LLM or a physical-truth oracle.
Callers supply measurements in declared units and explicit preservation budgets.
"""
import math


class Rejected(RuntimeError):
    def __init__(self, report):
        self.report = report
        super().__init__('Correction rejected: ' +
                         '; '.join(report['reasons']))


def assess(problem, action, before, after, *, improve, limits):
    """Require the named problem to improve without violating any safeguard.

    `improve` names lower-is-better measurements. `limits` maps every safeguarded
    after-measurement to an inclusive (minimum, maximum), in the recorded units.
    Missing, invalid and non-finite evidence fails closed, rather than guessing.
    """
    reasons = []
    checks = []
    for key in improve:
        a, b = before.get(key), after.get(key)
        valid = (isinstance(a, (int, float)) and isinstance(b, (int, float))
                 and math.isfinite(a) and math.isfinite(b) and b < a)
        checks.append(
            {'measurement': key, 'rule': 'strict improvement', 'passed': valid})
        if not valid:
            reasons.append(
                key + ': triggering problem did not measurably improve')
    for key, (low, high) in limits.items():
        value = after.get(key)
        valid = (isinstance(value, (int, float)) and math.isfinite(value)
                 and low <= value <= high)
        checks.append({'measurement': key, 'allowed': [
                      low, high], 'passed': valid})
        if not valid:
            reasons.append(
                key + ': missing evidence or preservation budget exceeded')
    if not improve or not limits:
        reasons.append(
            'A correction requires both a problem and preservation safeguards')
    return {'problem': problem, 'action': action, 'before': before, 'after': after,
            'accepted': not reasons, 'decision': 'apply' if not reasons else 'reject_and_rollback',
            'checks': checks, 'reasons': reasons, 'uses_llm': False,
            'physical_geometry_verified': False}
