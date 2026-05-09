# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a multi-language admin platform combining:
- **Python Backend** (FastAPI + SQLAlchemy) - Core business logic, user/permission management, AI Agents
- **Go Gateway** (Gin) - JWT auth, permission checks, routing, rate limiting
- **Go Generator** (Gin) - Code generation service with Claude API integration
- **Go Deploy** (Gin) - Docker-based deployment pipeline
- **React Frontend** (Vite + Ant Design 5) - Admin UI

## Ports & Services

| Service | Port | Path Prefix |
|---------|------|-------------|
| React Frontend | 3000 | - |
| Go Gateway | 8080 | - |
| Python Backend | 8081 | `/api` |
| Go Generator | 8082 | `/generator` |
| Go Deploy | 8083 | `/deploy` |
| Python Agent | 8084 | `/agent` |
| Go Config | 8085 | `/config` |
| WebSocket | 8086 | `/ws` |
| PostgreSQL | 5432 | - |
| Redis | 6379 | - |

## Build Commands

### Python Backend
```bash
cd admin-python
pip install -e .
python -m app.main
```

### Go Services
```bash
# Gateway
cd admin-gateway && go mod tidy && go run cmd/main.go

# Generator
cd admin-generator && go mod tidy && go run cmd/server/main.go

# Deploy
cd admin-deploy && go mod tidy && go run cmd/server/main.go

# Config
cd admin-config && go mod tidy && go run cmd/server/main.go

# WebSocket
cd admin-ws && go mod tidy && go run cmd/server/main.go
```

### Frontend
```bash
cd admin-frontend
npm install
npm run dev      # Development
npm run build    # Production build
npm run lint     # ESLint
```

### Docker Compose (All Services)
```bash
cd docker && docker-compose up -d
```

## Architecture

```
┌─────────────────────────────────────────────┐
│         React Frontend (3000)               │
│         Vite + Ant Design + Zustand         │
└─────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│         Go Gateway (8080)                   │
│  JWT验证 → 权限校验 → 路由转发 → 限流       │
└─────────────────────────────────────────────┘
         │              │              │
         ▼              ▼              ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│Python Backend│ │Go Generator │ │ Go Deploy   │
│   (8081)    │ │   (8082)    │ │   (8083)    │
│  AI Agents  │ │  Code Gen   │ │  Pipeline   │
└─────────────┘ └─────────────┘ └─────────────┘
```

## 6 AI Agents

| Agent | ID | Responsibility |
|-------|----|---------------|
| Product Manager | PM | Requirements gathering, PRD documents |
| Project Manager | PJM | Task breakdown, API contract definition |
| Backend Developer | BE | Backend development, bug fixes |
| Frontend Developer | FE | Frontend development, bug fixes |
| QA Engineer | QA | Test cases, bug reports |
| Reporter | RPT | Progress summary, daily reports |

## Key Patterns

### Request Flow
1. Frontend sends requests to Gateway (8080)
2. Gateway validates JWT, checks permissions via Redis
3. Gateway forwards to appropriate backend service
4. Services use tenant_id for multi-tenancy data isolation

### Multi-Tenancy
- All business tables include `tenant_id` column
- `sys_tenant` table stores tenant configurations
- JWT token contains tenant_id for request isolation

### Permission System
- User groups (`sys_admin_group`) contain permission lists
- Permissions stored as JSON array in `power` field
- Menu visibility controlled by `sys_menu.permission` matching

### Timestamp Convention
- All time fields stored as BIGINT milliseconds (e.g., `create_time`, `update_time`)

## Database

Schema located at `database/schema.sql`. Key tables:
- `sys_admin` - Administrator accounts
- `sys_admin_group` - User groups with permissions
- `sys_menu` - Menu and permission definitions
- `sys_tenant` - Multi-tenant configuration
- `gen_function_config` / `gen_field_config` - Code generation configs
- `deploy_task` / `deploy_project` - Deployment management

Initialize: `psql -U postgres -f database/schema.sql`

## Default Credentials

- Username: `admin`
- Password: `admin123`
- Tenant ID: `1`

## Frontend Structure

```
admin-frontend/src/
├── pages/          # Route pages (login, system, generator, deploy, webchat, skills)
├── components/     # Reusable components
├── services/       # API service calls
├── stores/         # Zustand state management
└── utils/          # Helper functions
```

Path alias: `@/` maps to `src/`

## Go Module Structure

Each Go service follows:
```
├── cmd/            # Entry points
│   └── main.go (or server/main.go)
├── internal/
│   ├── config/     # Configuration loading
│   ├── handler/    # HTTP handlers
│   ├── router/     # Route definitions
│   ├── middleware/ # HTTP middleware
│   └── service/    # Business logic
├── pkg/            # Shared utilities
└── config.yaml     # Service configuration
```

## Python Module Structure

```
admin-python/
├── app/
│   ├── ai/         # AI agents (PM/PJM/BE/FE/QA/RPT)
│   ├── api/        # FastAPI routes
│   ├── core/       # Config, database
│   ├── messaging/  # Message adapters (Telegram/Discord/Slack/Feishu)
│   ├── models/     # SQLAlchemy models
│   ├── schemas/    # Pydantic schemas
│   └── services/   # Business logic
├── tests/          # Pytest tests
└── alembic/        # Database migrations
```
