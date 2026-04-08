#!/usr/bin/env python3
"""
API Scaffolder - Generates boilerplate for RESTful and GraphQL APIs.

Usage:
    python scripts/api_scaffolder.py <project-path> [options]

Options:
    --name NAME         Project/service name (default: myapi)
    --type TYPE         API type: rest | graphql (default: rest)
    --lang LANG         Language: node | python | go (default: node)
    --db DB             Database: postgres | mysql | sqlite | mongo (default: postgres)
    --auth              Include JWT authentication scaffold
    --docker            Include Dockerfile and docker-compose.yml
    --dry-run           Print file tree without writing files
    -v, --verbose       Verbose output
"""

import argparse
import os
import sys
import textwrap
from pathlib import Path


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

NODE_REST_TEMPLATES = {
    "package.json": """\
{{
  "name": "{name}",
  "version": "1.0.0",
  "description": "REST API service",
  "main": "src/index.js",
  "scripts": {{
    "start": "node src/index.js",
    "dev": "nodemon src/index.js",
    "test": "jest --coverage",
    "lint": "eslint src/"
  }},
  "dependencies": {{
    "express": "^4.18.2",
    "pg": "^8.11.3",
    "dotenv": "^16.3.1",
    "joi": "^17.11.0",
    "helmet": "^7.1.0",
    "cors": "^2.8.5",
    "morgan": "^1.10.0",
    "express-rate-limit": "^7.1.5"
  }},
  "devDependencies": {{
    "nodemon": "^3.0.2",
    "jest": "^29.7.0",
    "supertest": "^6.3.3",
    "eslint": "^8.55.0"
  }}
}}
""",

    "src/index.js": """\
require('dotenv').config();
const app = require('./app');

const PORT = process.env.PORT || 3000;

app.listen(PORT, () => {{
  console.log(`{name} running on port ${{PORT}}`);
}});
""",

    "src/app.js": """\
const express = require('express');
const helmet = require('helmet');
const cors = require('cors');
const morgan = require('morgan');
const rateLimit = require('express-rate-limit');

const router = require('./routes');
const {{ errorHandler }} = require('./middleware/errorHandler');

const app = express();

// Security middleware
app.use(helmet());
app.use(cors());
app.use(rateLimit({{ windowMs: 15 * 60 * 1000, max: 100 }}));

// Request parsing
app.use(express.json());
app.use(express.urlencoded({{ extended: true }}));
app.use(morgan('combined'));

// Routes
app.use('/api/v1', router);

// Health check
app.get('/health', (_req, res) => res.json({{ status: 'ok' }}));

// Error handling (must be last)
app.use(errorHandler);

module.exports = app;
""",

    "src/routes/index.js": """\
const {{ Router }} = require('express');
const exampleRouter = require('./example');

const router = Router();

router.use('/examples', exampleRouter);

module.exports = router;
""",

    "src/routes/example.js": """\
const {{ Router }} = require('express');
const controller = require('../controllers/exampleController');
const {{ validate }} = require('../middleware/validate');
const schema = require('../schemas/exampleSchema');

const router = Router();

router.get('/',       controller.list);
router.get('/:id',    controller.get);
router.post('/',      validate(schema.create), controller.create);
router.put('/:id',    validate(schema.update), controller.update);
router.delete('/:id', controller.remove);

module.exports = router;
""",

    "src/controllers/exampleController.js": """\
const service = require('../services/exampleService');

exports.list   = async (req, res, next) => {{
  try {{ res.json(await service.list(req.query)); }}
  catch (err) {{ next(err); }}
}};

exports.get    = async (req, res, next) => {{
  try {{ res.json(await service.get(req.params.id)); }}
  catch (err) {{ next(err); }}
}};

exports.create = async (req, res, next) => {{
  try {{ res.status(201).json(await service.create(req.body)); }}
  catch (err) {{ next(err); }}
}};

exports.update = async (req, res, next) => {{
  try {{ res.json(await service.update(req.params.id, req.body)); }}
  catch (err) {{ next(err); }}
}};

exports.remove = async (req, res, next) => {{
  try {{
    await service.remove(req.params.id);
    res.status(204).send();
  }} catch (err) {{ next(err); }}
}};
""",

    "src/services/exampleService.js": """\
const db = require('../db');

exports.list   = ({ limit = 20, offset = 0 }) =>
  db.query('SELECT * FROM examples ORDER BY id LIMIT $1 OFFSET $2', [limit, offset])
    .then(r => r.rows);

exports.get    = (id) =>
  db.query('SELECT * FROM examples WHERE id = $1', [id])
    .then(r => r.rows[0] ?? null);

exports.create = (data) =>
  db.query(
    'INSERT INTO examples (name, description) VALUES ($1, $2) RETURNING *',
    [data.name, data.description]
  ).then(r => r.rows[0]);

exports.update = (id, data) =>
  db.query(
    'UPDATE examples SET name=$1, description=$2, updated_at=NOW() WHERE id=$3 RETURNING *',
    [data.name, data.description, id]
  ).then(r => r.rows[0]);

exports.remove = (id) =>
  db.query('DELETE FROM examples WHERE id = $1', [id]);
""",

    "src/db/index.js": """\
const {{ Pool }} = require('pg');

const pool = new Pool({{
  connectionString: process.env.DATABASE_URL,
  max: 10,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 2000,
}});

module.exports = pool;
""",

    "src/middleware/errorHandler.js": """\
exports.errorHandler = (err, _req, res, _next) => {{
  const status = err.status || 500;
  console.error(err);
  res.status(status).json({{
    error: {{
      message: err.message || 'Internal Server Error',
      ...(process.env.NODE_ENV !== 'production' && {{ stack: err.stack }}),
    }},
  }});
}};
""",

    "src/middleware/validate.js": """\
exports.validate = (schema) => (req, res, next) => {{
  const {{ error }} = schema.validate(req.body, {{ abortEarly: false }});
  if (error) {{
    return res.status(422).json({{
      error: {{ message: 'Validation failed', details: error.details }},
    }});
  }}
  next();
}};
""",

    "src/schemas/exampleSchema.js": """\
const Joi = require('joi');

exports.create = Joi.object({{
  name:        Joi.string().min(1).max(120).required(),
  description: Joi.string().max(500),
}});

exports.update = Joi.object({{
  name:        Joi.string().min(1).max(120),
  description: Joi.string().max(500),
}}).min(1);
""",

    ".env.example": """\
NODE_ENV=development
PORT=3000
DATABASE_URL=postgres://user:password@localhost:5432/{name}
JWT_SECRET=change_me_in_production
""",

    ".gitignore": """\
node_modules/
.env
coverage/
dist/
*.log
""",

    "src/db/migrations/001_create_examples.sql": """\
CREATE TABLE IF NOT EXISTS examples (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(120) NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_examples_name ON examples (name);
""",
}

DOCKERFILE_CONTENT = """\
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production

FROM node:20-alpine
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
WORKDIR /app
COPY --from=builder /app/node_modules ./node_modules
COPY . .
USER appuser
EXPOSE 3000
CMD ["node", "src/index.js"]
"""

DOCKER_COMPOSE_CONTENT = """\
version: "3.9"
services:
  api:
    build: .
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=development
      - DATABASE_URL=postgres://postgres:postgres@db:5432/{name}
    depends_on:
      db:
        condition: service_healthy

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: {name}
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./src/db/migrations:/docker-entrypoint-initdb.d
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
"""

JWT_MIDDLEWARE = """\
const jwt = require('jsonwebtoken');

exports.authenticate = (req, res, next) => {{
  const header = req.headers.authorization || '';
  const token  = header.startsWith('Bearer ') ? header.slice(7) : null;
  if (!token) return res.status(401).json({{ error: {{ message: 'Unauthorized' }} }});

  try {{
    req.user = jwt.verify(token, process.env.JWT_SECRET);
    next();
  }} catch {{
    res.status(401).json({{ error: {{ message: 'Invalid token' }} }});
  }}
}};
"""

AUTH_ROUTES = """\
const {{ Router }} = require('express');
const bcrypt = require('bcryptjs');
const jwt    = require('jsonwebtoken');
const db     = require('../db');

const router = Router();

router.post('/register', async (req, res, next) => {{
  try {{
    const hash = await bcrypt.hash(req.body.password, 12);
    const {{ rows }} = await db.query(
      'INSERT INTO users (email, password_hash) VALUES ($1, $2) RETURNING id, email',
      [req.body.email, hash]
    );
    res.status(201).json({{ user: rows[0] }});
  }} catch (err) {{ next(err); }}
}});

router.post('/login', async (req, res, next) => {{
  try {{
    const {{ rows }} = await db.query('SELECT * FROM users WHERE email = $1', [req.body.email]);
    const user = rows[0];
    if (!user || !(await bcrypt.compare(req.body.password, user.password_hash))) {{
      return res.status(401).json({{ error: {{ message: 'Invalid credentials' }} }});
    }}
    const token = jwt.sign({{ sub: user.id, email: user.email }}, process.env.JWT_SECRET, {{ expiresIn: '24h' }});
    res.json({{ token }});
  }} catch (err) {{ next(err); }}
}});

module.exports = router;
"""

AUTH_MIGRATION = """\
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    email         VARCHAR(254) UNIQUE NOT NULL,
    password_hash VARCHAR(60)  NOT NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_file(path: Path, content: str, dry_run: bool, verbose: bool) -> None:
    if dry_run:
        print(f"  [dry-run] {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    if verbose:
        print(f"  created  {path}")


def scaffold_node_rest(base: Path, name: str, auth: bool, docker: bool,
                       dry_run: bool, verbose: bool) -> None:
    for rel, tmpl in NODE_REST_TEMPLATES.items():
        content = tmpl.format(name=name)
        write_file(base / rel, content, dry_run, verbose)

    if auth:
        write_file(base / "src/middleware/auth.js",   JWT_MIDDLEWARE, dry_run, verbose)
        write_file(base / "src/routes/auth.js",       AUTH_ROUTES,   dry_run, verbose)
        write_file(base / "src/db/migrations/002_create_users.sql", AUTH_MIGRATION, dry_run, verbose)
        if verbose:
            print("  [auth] JWT middleware + /auth/register + /auth/login routes added")

    if docker:
        write_file(base / "Dockerfile",         DOCKERFILE_CONTENT,                    dry_run, verbose)
        write_file(base / "docker-compose.yml", DOCKER_COMPOSE_CONTENT.format(name=name), dry_run, verbose)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scaffold a backend API project.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(__doc__ or ""),
    )
    parser.add_argument("project_path", nargs="?", default=".", help="Output directory")
    parser.add_argument("--name",    default="myapi",  help="Service name")
    parser.add_argument("--type",    default="rest",   choices=["rest", "graphql"])
    parser.add_argument("--lang",    default="node",   choices=["node", "python", "go"])
    parser.add_argument("--db",      default="postgres", choices=["postgres", "mysql", "sqlite", "mongo"])
    parser.add_argument("--auth",    action="store_true", help="Include JWT auth scaffold")
    parser.add_argument("--docker",  action="store_true", help="Include Docker files")
    parser.add_argument("--dry-run", action="store_true", help="Print files without writing")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base = Path(args.project_path).resolve()

    print(f"Scaffolding {args.lang}/{args.type} API '{args.name}' -> {base}")
    if args.dry_run:
        print("(dry-run mode — no files will be written)\n")

    if args.lang == "node" and args.type == "rest":
        scaffold_node_rest(base, args.name, args.auth, args.docker,
                           args.dry_run, args.verbose)
    else:
        print(f"Template for {args.lang}/{args.type} not yet implemented.", file=sys.stderr)
        return 1

    print("\nDone! Next steps:")
    print(f"  cd {base}")
    print("  cp .env.example .env  # then edit DATABASE_URL / JWT_SECRET")
    print("  npm install")
    print("  npm run dev")
    return 0


if __name__ == "__main__":
    sys.exit(main())
