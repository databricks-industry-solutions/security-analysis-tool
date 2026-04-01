# SAT Validation Report - AWS — FOGHORN

**Generated:** 2026-04-01 13:56:43  
**SAT Run ID:** 23  
**Cloud:** aws — foghorn  
**Total checks validated:** 1

## Summary

| Status | Count | Description |
|--------|-------|-------------|
| AGREE | 0 | API ground truth matches SAT result |
| DISAGREE | 0 | API and SAT disagree on pass/fail |
| SAT_MISSING | 1 | Check not found in SAT output for this run |
| API_ERROR | 0 | Could not call the API to verify |
| **Total** | **1** | |

## Missing from SAT Output

These checks have validators but no corresponding result was found in the SAT `security_checks` table for run_id=23.

- **GOV-45**: Jobs not granting CAN_MANAGE to non-admin principals

## Full Results

| Check ID | Name | Category | Severity | API | SAT | Verdict |
|----------|------|----------|----------|-----|-----|---------|
| GOV-45 | Jobs not granting CAN_MANAGE to non-admin principals | Governance | High | PASS | N/A | SAT_MISSING |
