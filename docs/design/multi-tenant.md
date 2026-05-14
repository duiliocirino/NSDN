# Multi-Tenant Architecture

## Overview

NSDN supports two operating modes:
1. **Standalone** — single user, CLI-driven (current, backward compatible)
2. **Service** — multi-tenant, user isolation, API-driven (future)

All user data is scoped via `user_id`. The default user is `"default"` for backward compatibility.

## Data Model

### Database Schema Changes

```sql
-- Add user_id to existing tables
ALTER TABLE sources ADD COLUMN user_id TEXT DEFAULT 'default';
ALTER TABLE entries ADD COLUMN user_id TEXT DEFAULT 'default';
ALTER TABLE editions ADD COLUMN user_id TEXT DEFAULT 'default';

-- Indexes for filtering
CREATE INDEX idx_entries_user ON entries(user_id);
CREATE INDEX idx_editions_user ON editions(user_id);
CREATE INDEX idx_sources_user ON sources(user_id);
```

### User Config Resolution

```
config/nsdn.yaml                    ← global defaults (LLM, Weaviate, shared)
  ↓ overridden by
config/users/{user_id}/nsdn.yaml    ← user-specific (sources, interests, newspaper)
```

Override files are optional. Missing keys inherit from global config.

### Weaviate Namespace

Each user gets a separate collection:
```
NSDNEntries_{user_id}
```

### Output Structure

```
output/
  {user_id}/
    journal/
      {edition_slug}/
        cover.html
        edition.pdf
        topics/
```

## Implementation Phases

### Phase 1: DB + Config (standalone, no service)

**Files to modify:**
- `src/nsdn/db.py` — Add `user_id` column, filter all queries
- `src/nsdn/config.py` — Add `UserConfig` model, resolution logic
- `src/nsdn/loader.py` — Load global + user override configs
- `src/nsdn/cli.py` — Add `user` commands (add/list/delete)

**New files:**
- `src/nsdn/users.py` — User management (CRUD, config scaffolding)

**Key changes:**
1. Database queries accept `user_id` parameter (default: `"default"`)
2. Config loader merges global → user override
3. CLI: `nsdn user add <id>` creates `config/users/<id>/nsdn.yaml`
4. All pipeline stages scoped to `user_id`

### Phase 2: Weaviate + Output Isolation

**Files to modify:**
- `src/nsdn/vector.py` — Namespaced collections
- `src/nsdn/extract.py` — Per-user output directories
- `src/nsdn/newspaper/component.py` — User-scoped assembly

**Key changes:**
1. Weaviate collection: `NSDNEntries_{user_id}`
2. Output dir: `output/{user_id}/journal/`
3. Dedup per-user (no cross-user dedup)

### Phase 3: API Layer (service mode)

**New files:**
- `src/nsdn/api/app.py` — FastAPI application
- `src/nsdn/api/auth.py` — JWT authentication
- `src/nsdn/api/routes.py` — REST endpoints

**Endpoints:**
```
POST /api/users              # Register
POST /api/auth/login         # Login
GET  /api/editions           # User's editions
POST /api/run                # Trigger pipeline
GET  /api/config             # Get/set user config
```

## Backward Compatibility

- Existing `data/feeds.db` entries get `user_id = 'default'` via migration
- `config/nsdn.yaml` becomes global defaults
- CLI commands default to `--user default`
- No breaking changes to existing workflows

## User Lifecycle

```
nsdn user add alice           # Create user, scaffold config
nsdn user list                # Verify
nsdn run --user alice         # Run pipeline for alice
nsdn user delete alice        # Remove (optionally keep data)
```

## Security Considerations (Phase 3)

- User IDs are not user-facing (UUIDs internally, friendly names externally)
- Config files contain secrets (API keys) — restrict permissions (0600)
- Weaviate collections isolated per user
- API: JWT-based auth, rate limiting per user
