# Unit Test Failures Analysis

**Total**: 29 failed, 41 passed  
**Target**: Fix all groups to reach 70 passed, 0 failed

## Group A: Config Validation (3 tests)

Tests expect `ConfigError` or `ValidationError` when required fields are missing, but `ConfigDict(extra='ignore')` silently drops validation.

```
FAILED tests/unit/test_config.py::test_settings_missing_openai_key - Failed: DID NOT RAISE
FAILED tests/unit/test_config.py::test_settings_missing_database_url - Failed: DID NOT RAISE
FAILED tests/unit/test_config.py::test_deepseek_missing_key - Failed: DID NOT RAISE
```

**Root Cause**: `ConfigDict(extra='ignore')` in `src/core/config.py` bypasses field validation.

**Fix**: Change `extra='ignore'` to `extra='forbid'` and ensure required field validators raise on missing values.

---

## Group B: Database Pool Not Initialized (25 tests)

Tests attempt to use the database pool without initialization. No PostgreSQL instance running in test environment.

### Checkpointer Tests (6 tests)
```
FAILED tests/unit/test_checkpointer.py::test_checkpointer_put - RuntimeError: Database pool not initialized
FAILED tests/unit/test_checkpointer.py::test_checkpointer_get - RuntimeError: Database pool not initialized
FAILED tests/unit/test_checkpointer.py::test_checkpointer_get_nonexistent - RuntimeError: Database pool not initialized
FAILED tests/unit/test_checkpointer.py::test_checkpointer_list - RuntimeError: Database pool not initialized
FAILED tests/unit/test_checkpointer.py::test_checkpointer_get_latest - RuntimeError: Database pool not initialized
FAILED tests/unit/test_checkpointer.py::test_checkpointer_update_existing - RuntimeError: Database pool not initialized
```

### Memory Tests (11 tests)
```
FAILED tests/unit/test_memory.py::test_create_thread - RuntimeError: Database pool not initialized
FAILED tests/unit/test_memory.py::test_create_thread_with_metadata - RuntimeError: Database pool not initialized
FAILED tests/unit/test_memory.py::test_get_thread - RuntimeError: Database pool not initialized
FAILED tests/unit/test_memory.py::test_get_nonexistent_thread - RuntimeError: Database pool not initialized
FAILED tests/unit/test_memory.py::test_add_message - RuntimeError: Database pool not initialized
FAILED tests/unit/test_memory.py::test_get_history - RuntimeError: Database pool not initialized
FAILED tests/unit/test_memory.py::test_get_history_empty - RuntimeError: Database pool not initialized
FAILED tests/unit/test_memory.py::test_get_history_limit - RuntimeError: Database pool not initialized
FAILED tests/unit/test_memory.py::test_add_message_with_metadata - RuntimeError: Database pool not initialized
FAILED tests/unit/test_memory.py::test_thread_update_time - RuntimeError: Database pool not initialized
FAILED tests/unit/test_memory.py::test_delete_thread - RuntimeError: Database pool not initialized
```

### Routes Tests (8 tests)
All returning HTTP 500 with "Database pool not initialized" error:
```
FAILED tests/unit/test_routes.py::TestPlanningEndpoints::test_plan_trip_accepts_minimal_request
FAILED tests/unit/test_routes.py::TestPlanningEndpoints::test_plan_trip_with_user_id
FAILED tests/unit/test_routes.py::TestPlanningEndpoints::test_plan_trip_with_thread_id
FAILED tests/unit/test_routes.py::TestPlanningEndpoints::test_get_nonexistent_thread_returns_404
FAILED tests/unit/test_routes.py::TestApprovalEndpoints::test_approve_nonexistent_thread_returns_404
FAILED tests/unit/test_routes.py::TestApprovalEndpoints::test_approve_accepts_feedback
FAILED tests/unit/test_routes.py::TestApprovalEndpoints::test_approve_accepts_rejection
FAILED tests/unit/test_routes.py::TestErrorHandling::test_api_returns_json_errors
```

**Root Cause**: Unit tests use real database pool from `src/memory/db.py`, which is not initialized in test environment.

**Fix**: Add `mock_db_pool` fixture in `tests/unit/conftest.py` that patches the pool globally for all tests.

---

## Group C: Async Coroutine Not Awaited (1 test)

```
FAILED tests/unit/test_evals.py::TestEvalGate::test_eval_gate_passes_all_judges
  RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited
```

Error at line 228:
```python
verdict = await run_eval_gate(response, {"budget": 2000})
```

**Root Cause**: Mock judges are returning AsyncMock coroutines instead of mock values. The mock is not properly configured.

**Fix**: Ensure mock judges return actual values, not coroutines. May also need to check if `build_graph()` is async (it shouldn't be).

---

## Summary

| Group | Count | Type | Fix Complexity |
|-------|-------|------|-----------------|
| A | 3 | Config validation | Low |
| B | 25 | Database pool mock | Medium |
| C | 1 | Async/await | Low |

**Total Effort**: 2-3 hours with parallel fixing possible for groups A and C
