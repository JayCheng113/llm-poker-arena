"""Session orchestrator (multi-hand loop + audit + event emission).

Replaces Phase-1 `engine._internal.rebuy.run_single_hand` for end-to-end runs.
Phase 2a: mock-agent sessions. Phase 3 will widen to async ReAct + censored
hand handling per spec §3.6 / BR2-01.
"""
