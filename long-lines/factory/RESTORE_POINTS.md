# Restore points

Named states of the factory to go back to if a change does not work out. Tags cannot be pushed from
the cloud sessions, so each point is a commit on the branch.

| Point | Commit | What came after it |
|---|---|---|
| pre-golden-disc | 7c166bc | reference handbook, cord type, screen-error triangle budgets, per-corner view weights, back-plate placement |

To undo everything after a point (keeps history; safest):

    git revert --no-edit 7c166bc..HEAD

To undo only one feature: every handbook-driven behaviour is opt-in through an order's `"handbook"` field;
removing that field from an order builds it the old way (parts list, body width and mounting in the order,
area/detail triangle sharing, swept or hull cord). The fixtures in factory/fixtures/ have no handbook and
are built the old way by tools/diag/regress_assets.py.
