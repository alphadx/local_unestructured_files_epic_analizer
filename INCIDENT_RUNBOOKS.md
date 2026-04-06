# Incident Runbooks & Deployment Procedures

**Versión**: 1.0  
**Fecha**: 2026-04-06  
**Audiencia**: DevOps, SRE, On-call engineers

---

## Tabla de contenidos

1. [Deployment procedures](#deployment-procedures)
2. [Common incidents & responses](#common-incidents--responses)
3. [Escalation matrix](#escalation-matrix)
4. [Rollback procedures](#rollback-procedures)
5. [Post-incident review](#post-incident-review)

---

## Deployment procedures

### Pre-deployment checklist

**Time**: ~5 minutes before deployment

```bash
# 1. Verify all services are healthy
docker-compose ps
# All should be "Up"

# 2. Backup current state
docker-compose exec chromadb tar czf /backup/pre-deploy-$(date +%s).tar.gz /data

# 3. Verify schema migrations are ready
docker-compose exec backend alembic current  # (if using)

# 4. Drain connections (optional if service hot-reloadable)
# Skip for now — Epic not yet stateless
```

---

### Standard deployment flow

**Scenario A: Configuration-only changes** (vars env)

```bash
# 1. Update .env
vi .env

# Example: Changing INGESTION_MODE
# INGESTION_MODE=whitelist
# ALLOWED_EXTENSIONS=.pdf,.docx,.msg

# 2. Rebuild (if needed)
docker-compose build backend

# 3. Restart backend only (short downtime ~10 sec)
docker-compose restart backend

# 4. Verify health
sleep 2
curl http://localhost:8000/health
# {"status": "ok"}

# 5. Test with a job
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/tmp/test",
    "group_mode": "strict",
    "ingestion_mode": "whitelist"
  }'

# 6. Monitor
docker-compose logs -f backend | grep -E "ERROR|started"
# Should see "started" and no errors
```

---

**Scenario B: Python backend changes** (new code)

```bash
# 1. Pull changes
git pull origin main

# 2. Run tests locally (or in CI)
.venv/bin/python -m pytest tests/test_document_extraction.py -xvs --tb=short

# 3. Build new image
docker-compose build backend

# 4. Deploy to staging first (if available)
# Skip this for MVP — deploy directly

# 5. Stop old container gracefully
docker-compose stop backend

# 6. Start new container
docker-compose up -d backend

# 7. Verify startup logs (no errors for 30 sec)
docker-compose logs backend | tail -20

# 8. Health check
curl http://localhost:8000/health

# 9. Run smoke test
curl -X POST http://localhost:8000/api/jobs \
  -d '{"path": "/tmp", "group_mode": "strict"}'

# 10. Monitor for 5 min
for i in {1..30}; do
  curl -s http://localhost:8000/health | jq .status
  sleep 10
done
```

---

**Scenario C: Full stack deployment** (backend + frontend + DB)

```bash
# 1. Back everything up
docker-compose exec chromadb tar czf /backup/full-backup-$(date +%s).tar.gz /data

# 2. Build all images
docker-compose build

# 3. Bring down gracefully
docker-compose down

# 4. Bring up new stack
docker-compose up -d

# 5. Wait for services (30 sec)
sleep 10

# 6. Health checks (all services)
curl http://localhost:8000/health           # Backend
curl http://localhost:3000                  # Frontend
curl http://chromadb:8000/api/v1            # ChromaDB

# 7. Test end-to-end
echo "Testing E2E..."
JOB_ID=$(curl -s -X POST http://localhost:8000/api/jobs \
  -d '{"path": "/tmp", "group_mode": "strict"}' | jq -r '.job_id')

echo "Job: $JOB_ID"
sleep 5

curl http://localhost:8000/api/jobs/$JOB_ID | jq '.status'
# Should eventually reach "completed"

# 8. Verify audit trail
curl http://localhost:8000/api/admin/filter-stats | jq '.total_files_filtered'
```

---

### Deployment with zero downtime (future)

**Note**: Currently not supported. Roadmap Q3 2026.

Future approach:
1. Run secondary backend on port 8001
2. Health-check secondary
3. Blue-green switch via load balancer
4. Graceful drain of primary

---

## Common incidents & responses

### Incident 1: Backend not starting / "Connection refused"

**Severity**: CRITICAL  
**On-call time**: Immediate  
**MTTR**: ~2 min

**Symptoms**:
```
curl http://localhost:8000/health
# curl: (7) Failed to connect to localhost port 8000
```

**Diagnosis**:
```bash
# Check if container is running
docker-compose ps backend
# If "Down" or "Exited": not running

# Check logs
docker-compose logs backend | tail -50 | grep ERROR
```

**Common causes**:
1. **Port in use**: Another service on 8000
2. **Image build failed**: Syntax error in code
3. **Config error**: Invalid .env values

**Resolution**:

*Case 1: Port in use*
```bash
lsof -i :8000
# Kill process or change EXPOSE port in docker-compose.yml
```

*Case 2: Build failed*
```bash
docker-compose build --no-cache backend
# Check for error messages

# If error in Python: fix and rebuild
```

*Case 3: Config error*
```bash
# Check .env syntax
cat .env

# If GEMINI_API_KEY is empty:
echo "GEMINI_API_KEY=<paste key>" >> .env

# Rebuild and restart
docker-compose restart backend
```

**Verification**:
```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

---

### Incident 2: Jobs hanging in "running" state (not completing)

**Severity**: HIGH  
**On-call time**: 5 min decision window  
**MTTR**: ~5 min (if graceful), ~2 min (if kill)

**Symptoms**:
```bash
curl http://localhost:8000/api/jobs/<JOB_ID>
# {"status": "running", ...}
# (same status after 30 min)
```

**Diagnosis**:
```bash
# 1. Check backend logs
docker-compose logs backend | tail -50 | grep -E "ERROR|job_id=<JOB_ID>"

# 2. Check memory usage
docker stats backend --no-stream

# 3. Check file access
docker-compose exec backend ls -la /data/scan_path/
# (Verify readable)
```

**Common causes**:
1. **Stalled extraction**: Large binary trying to process (should auto-skip, but config wrong)
2. **Memory exhausted**: Corpus too large for available RAM
3. **Disk full**: No space to write temp files or ChromaDB

**Resolution**:

*Case 1: Stalled extraction*
```bash
# Cancel current job
curl -X DELETE http://localhost:8000/api/jobs/<JOB_ID>

# Check filter-stats
curl http://localhost:8000/api/admin/filter-stats?job_id=<JOB_ID>

# If too many binaries processed:
# Update INGESTION_MODE to whitelist or increase DENIED_EXTENSIONS

# Retry with better config
curl -X POST http://localhost:8000/api/jobs \
  -d '{
    "path": "...",
    "ingestion_mode": "whitelist",
    "allowed_extensions": ".txt,.pdf,.docx"
  }'
```

*Case 2: Memory exhausted*
```bash
# Option A: Increase container memory
# Edit docker-compose.yml
# services:
#   backend:
#     mem_limit: 4g  # was 2g

docker-compose up -d backend

# Option B: Reduce SCAN_CONCURRENCY
# SCAN_CONCURRENCY=2  (was 4)
docker-compose restart backend

# Retry job with smaller corpus
```

*Case 3: Disk full*
```bash
# Free space
docker system prune -a  # Warning: removes all unused images

# Check where space is used
du -sh /var/lib/docker/volumes/*

# Expand volume (cloud-specific, depends on provider)
# AWS EBS: expand volume size, extend filesystem
# Local: varies

# Then retry
```

**Prevention**:
- Set job timeout env var (future feature)
- Monitor disk space continuously
- Use `SCAN_CONCURRENCY=1` for large files

---

### Incident 3: Filter-stats returns empty or 500 error

**Severity**: MEDIUM (monitoring impaired, not blocking ingestion)  
**On-call time**: 10 min  
**MTTR**: ~1 min

**Symptoms**:
```bash
curl http://localhost:8000/api/admin/filter-stats
# {} (empty)
# OR
# 500 Internal Server Error
```

**Diagnosis**:
```bash
# 1. Check backend health
curl http://localhost:8000/health

# 2. Check if audit database is accessible
docker-compose logs backend | grep -i "audit\|database"

# 3. Verify jobs exist
curl http://localhost:8000/api/jobs | jq 'length'
```

**Common causes**:
1. **Audit DB corrupted**: Rare, but possible if crash during write
2. **No jobs completed yet**: Endpoint returns empty (expected)
3. **Backend memory issue**: Can't query audit table

**Resolution**:

*Case 1: Audit DB corrupted*
```bash
# Restart just backend (soft reset)
docker-compose restart backend

# Verify endpoint works
curl http://localhost:8000/api/admin/filter-stats

# If still broken: reset audit DB (loses history)
# DON'T do this in production without backup!
docker-compose exec backend \
  rm /var/lib/epic-audit.db
docker-compose restart backend
```

*Case 2: No jobs yet*
```bash
# This is normal
# Create a test job first
curl -X POST http://localhost:8000/api/jobs \
  -d '{"path": "/tmp", "group_mode": "strict"}'

# Wait 5 sec, then check filter-stats again
sleep 5
curl http://localhost:8000/api/admin/filter-stats
```

**Verification**:
```bash
curl http://localhost:8000/api/admin/filter-stats | jq '.total_scans_with_filters'
# Should be number >= 0
```

---

### Incident 4: Binary files NOT being skipped (processing all files)

**Severity**: LOW (data consistency, not critical failure)  
**On-call time**: 15 min (can defer to next shift if non-urgent)  
**MTTR**: ~3 min

**Symptoms**:
```bash
# Job includes images, videos, executables in processed count
curl http://localhost:8000/api/reports/<JOB_ID>/statistics | jq '.total_files'
# Includes .exe, .jpg, .mp4, etc. (shouldn't)

# OR filter-stats shows no skipped binaries
curl http://localhost:8000/api/admin/filter-stats | \
  jq '.scans[] | select(.skipped_count < 10)'
# Should have high skip count
```

**Diagnosis**:
```bash
# 1. Check what ingestion_mode is active
docker exec <backend_id> env | grep INGESTION_MODE

# 2. Check if binary detection is enabled in code
docker-compose logs backend | grep -i "binary\|skipped"

# 3. Verify DENIED_EXTENSIONS is set
docker exec <backend_id> env | grep DENIED_EXTENSIONS
```

**Common causes**:
1. **INGESTION_MODE = whitelist** with too-broad ALLOWED_EXTENSIONS
2. **Binary detection disabled by mistake** (code change)
3. **DENIED_EXTENSIONS/MIME_TYPES not set** in .env

**Resolution**:

*Case 1: Too-broad whitelist*
```bash
# Current config
echo $ALLOWED_EXTENSIONS
# ".exe,.txt,.pdf"  (oops, includes .exe)

# Fix .env
ALLOWED_EXTENSIONS=".txt,.pdf,.docx"

# Restart
docker-compose restart backend

# Verify with new job
curl -X POST http://localhost:8000/api/jobs \
  -d '{"ingestion_mode": "whitelist", "allowed_extensions": ".pdf,.txt"}'
```

*Case 2: Binary detection disabled*
```bash
# Check code in document_extraction_service.py
docker-compose exec backend \
  grep -n "_is_binary_file" /app/services/document_extraction_service.py

# If missing: revert to previous commit
git log --oneline | head -5
git revert <commit_hash>

# Rebuild and deploy
docker-compose build backend && docker-compose up -d backend
```

---

## Escalation matrix

| Issue | Severity | Who | Escalate to | Timeout |
|-------|----------|-----|-------------|---------|
| Service down | CRITICAL | On-call | Platform team | 15 min |
| Data corruption | CRITICAL | On-call | Data team + Backup ops | 5 min |
| Memory leak | HIGH | On-call | SRE team | 30 min |
| Slow query | MEDIUM | On-call | DB team | 1 hour |
| Config error | LOW | On-call | (resolve locally) | N/A |

---

## Rollback procedures

### Rollback scenario: Recently deployed bad code

**Trigger**: Job failures > 50%, or E2E test failures

**Steps**:

```bash
# 1. Verify current version
docker-compose logs backend | grep "version\|running"

# 2. Check last commit
git log --oneline -5

# 3. Identify last-known-good commit
git log --oneline | grep "✅ TESTED"

# 4. Revert to last-good commit
git revert --no-commit HEAD~1  # or cherry-pick if partial rollback

# 5. Rebuild and test
docker-compose build backend
.venv/bin/python -m pytest tests/test_api.py -xvs -k "health"

# 6. Deploy
docker-compose up -d backend

# 7. Monitor
docker-compose logs -f backend | grep -E "ERROR|started"

# 8. Run smoke test
curl http://localhost:8000/api/jobs | jq '.[] | .status' | sort | uniq -c
# Count of job statuses — should be stable
```

### Rollback scenario: ChromaDB data corruption

**Triggers**: Index errors, query failures on working clusters

**Steps**:

```bash
# 1. Stop backend (prevents writes)
docker-compose stop backend

# 2. Restore from backup (select most recent)
ls -la /backup/
# chroma-2026-04-06-*.tar.gz

# 3. Extract on fresh volume
docker volume rm epic_chromadb_data  # WARNING: destructive
docker volume create epic_chromadb_data

docker run --rm \
  -v epic_chromadb_data:/restore \
  -v /backup:/backup \
  alpine tar xzf /backup/chroma-2026-04-06-*.tar.gz -C /restore

# 4. Start backend
docker-compose up -d backend

# 5. Verify
curl http://localhost:8000/api/reports | jq '.[] | .job_id' | wc -l
# Should show count of recovered jobs
```

---

## Post-incident review

### Template

**Incident ID**: INC-2026-04-06-001  
**Date**: April 6, 2026  
**Duration**: 15 min (14:45-15:00 UTC)  
**Severity**: HIGH

**Impact**:
- Jobs stuck in "running" state
- 3 in-flight jobs affected
- No data loss

**Root cause**:
- Binary file (.exe) attempted processing due to misconfigured DENIED_EXTENSIONS
- Memory exhausted during unstructured extraction
- Fallback to LabelPropagation never triggered (bug in fallback chain)

**Timeline**:
- 14:45: Alert auto-skip binary detection not working
- 14:47: On-call starts investigation
- 14:50: Root cause identified (config + code)
- 14:55: Code deployed (fix fallback chain)
- 15:00: Incident resolved

**Actions**:
1. **Immediate** (done): Deploy fallback chain fix + restart backend
2. **Short-term** (24h): Add unit test for binary fallback (avoid regression)
3. **Medium-term** (1 week): Add configuration validation on startup
4. **Long-term** (Q3): Add proactive monitoring for stuck jobs

**Follow-up**:
- Review: Dev team (30 min sync)
- Document: Add binary detection FAQ to OPERATOR_GUIDE.md
- Monitor: Alert on job > 10 min without progress

---

## Appendix: Useful commands

### Monitoring

```bash
# Real-time logs
docker-compose logs -f backend

# Job status distribution
curl http://localhost:8000/api/jobs | \
  jq '[.[] | .status] | group_by(.) | map({status: .[0], count: length})'

# Memory usage
docker stats backend --no-stream

# Filter stats
curl http://localhost:8000/api/admin/filter-stats | jq \
  '{total_scans_with_filters, total_files_filtered}'
```

### Debugging

```bash
# SSH into backend container
docker-compose exec backend sh

# Check file extraction for a specific document
curl http://localhost:8000/api/reports/<JOB_ID>/documents | \
  jq '.[] | select(.name | contains("binary")) | {name, extraction_method, text_length: (.text | length)}'

# Find slow queries
docker-compose logs backend | grep "took.*ms" | sort -k2 -nr | head
```

### Cleanup

```bash
# Remove old audit logs (archive first!)
tar czf /backup/audit-archive-$(date +%Y%m%d).tar.gz /var/lib/epic-audit.db
rm /var/lib/epic-audit.db
docker-compose restart backend

# Prune unused Docker resources
docker system prune -a

# Clear old job data (DESTRUCTIVE — backup first)
docker-compose exec chromadb sqlite3 /data/chroma.db \
  "DELETE FROM documents WHERE created_at < datetime('now', '-30 days');"
```

