# SAT Validation Report - AWS — SFE

**Generated:** 2026-04-01 13:56:36  
**SAT Run ID:** 23  
**Cloud:** aws — sfe  
**Total checks validated:** 1

## Summary

| Status | Count | Description |
|--------|-------|-------------|
| AGREE | 1 | API ground truth matches SAT result |
| DISAGREE | 0 | API and SAT disagree on pass/fail |
| SAT_MISSING | 0 | Check not found in SAT output for this run |
| API_ERROR | 0 | Could not call the API to verify |
| **Total** | **1** | |

## Full Results

| Check ID | Name | Category | Severity | API | SAT | Verdict |
|----------|------|----------|----------|-----|-----|---------|
| GOV-45 | Jobs not granting CAN_MANAGE to non-admin principals | Governance | High | FAIL | FAIL | AGREE |
