# Restore points

Named states of the factory to go back to if a change does not work out. Tags cannot be pushed from
the cloud sessions, so each point is a commit on the branch.

| Point | Commit | What came after it |
|---|---|---|
| pre-golden-disc | 7c166bc | reference handbook, cord type, screen-error triangle budgets, per-corner view weights, back-plate placement |
| pre-human-scale | f1a6f8c | human scale: body table, contacts instead of looked-up sizes, scale solved from the drawing |

To undo everything after a point (keeps history; safest):

    git revert --no-edit 7c166bc..HEAD

To undo only human scale: `git revert --no-edit f1a6f8c..HEAD`, or give an order `"body_width_m"`: it then
builds at that size and the contacts are not used.

To undo only one feature: every handbook-driven behaviour is opt-in through an order's `"handbook"` field;
removing that field from an order builds it the old way (parts list, body width and mounting in the order,
area/detail triangle sharing, swept or hull cord). The fixtures in factory/fixtures/ have no handbook and
are built the old way by tools/diag/regress_assets.py.
