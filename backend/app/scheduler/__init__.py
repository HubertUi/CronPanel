"""Internal scheduler (Phase 5).

The scheduler decides *when* a run should happen and hands off to the Phase 4
execution service, which decides *whether* it is allowed. This package never
spawns a process itself: ``subprocess`` stays confined to ``app.execution``.
"""