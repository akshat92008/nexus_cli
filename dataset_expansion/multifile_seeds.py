#!/usr/bin/env python3
"""
dataset_expansion/multifile_seeds.py — Hand-authored Multi-File, Multi-Language Seed Examples

These are the 12 gold-standard seed examples for Category B (Multi-File, Multi-Language).
Each demonstrates Nova correctly outputting 3–5 files in languages other than Python.
Languages covered: JavaScript, TypeScript, Go, CSS.

These seeds serve two purposes:
  1. Direct training examples (high-quality, hand-verified)
  2. Few-shot examples for the synthetic generator (generate_multifile_examples.py)

Part of the Nova model family by Amaura.
"""

MULTIFILE_SEEDS = [

    # ── 1. Express.js API split into 3 files ──────────────────────────────────
    {
        "language": "javascript",
        "file_count": 3,
        "prompt": "Split the Express.js app into three files: `src/app.js` (Express setup), `src/routes/users.js` (GET /users and POST /users routes), and `src/middleware/logger.js` (request logger middleware).",
        "response": """\
<<THINKING>>
Splitting Express app into app.js, routes/users.js, middleware/logger.js. Three separate files.

<<FILES>>
```javascript
// filepath: src/app.js
// action: CREATE

const express = require('express');
const logger = require('./middleware/logger');
const usersRouter = require('./routes/users');

const app = express();
app.use(express.json());
app.use(logger);
app.use('/users', usersRouter);

module.exports = app;
```
```javascript
// filepath: src/routes/users.js
// action: CREATE

const express = require('express');
const router = express.Router();

const users = [];

router.get('/', (req, res) => {
    res.json(users);
});

router.post('/', (req, res) => {
    const user = { id: Date.now(), ...req.body };
    users.push(user);
    res.status(201).json(user);
});

module.exports = router;
```
```javascript
// filepath: src/middleware/logger.js
// action: CREATE

function logger(req, res, next) {
    console.log(`[${new Date().toISOString()}] ${req.method} ${req.path}`);
    next();
}

module.exports = logger;
```

<<TEST_COMMAND>>
npm test""",
    },

    # ── 2. Go HTTP server split into 3 files ──────────────────────────────────
    {
        "language": "go",
        "file_count": 3,
        "prompt": "Create a Go HTTP server split into three files: `cmd/main.go` (entry point), `internal/handlers/health.go` (health check handler), and `internal/handlers/users.go` (user list handler).",
        "response": """\
<<THINKING>>
Creating Go HTTP server: cmd/main.go entry point, plus two handler files in internal/handlers/.

<<FILES>>
```go
// filepath: cmd/main.go
// action: CREATE

package main

import (
    "log"
    "net/http"

    "github.com/example/app/internal/handlers"
)

func main() {
    mux := http.NewServeMux()
    mux.HandleFunc("/health", handlers.Health)
    mux.HandleFunc("/users", handlers.Users)

    log.Println("Server listening on :8080")
    log.Fatal(http.ListenAndServe(":8080", mux))
}
```
```go
// filepath: internal/handlers/health.go
// action: CREATE

package handlers

import (
    "encoding/json"
    "net/http"
)

func Health(w http.ResponseWriter, r *http.Request) {
    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}
```
```go
// filepath: internal/handlers/users.go
// action: CREATE

package handlers

import (
    "encoding/json"
    "net/http"
)

type User struct {
    ID   int    `json:"id"`
    Name string `json:"name"`
}

var users = []User{
    {ID: 1, Name: "Alice"},
    {ID: 2, Name: "Bob"},
}

func Users(w http.ResponseWriter, r *http.Request) {
    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(users)
}
```

<<TEST_COMMAND>>
go test ./...""",
    },

    # ── 3. TypeScript module split into 3 files ───────────────────────────────
    {
        "language": "typescript",
        "file_count": 3,
        "prompt": "Create a TypeScript user service split into three files: `src/types/user.ts` (User interface), `src/services/userService.ts` (CRUD operations), and `src/controllers/userController.ts` (request handlers).",
        "response": """\
<<THINKING>>
TypeScript user service: types/user.ts interface, services/userService.ts CRUD, controllers/userController.ts handlers.

<<FILES>>
```typescript
// filepath: src/types/user.ts
// action: CREATE

export interface User {
    id: number;
    name: string;
    email: string;
    createdAt: Date;
}

export type CreateUserDTO = Omit<User, 'id' | 'createdAt'>;
```
```typescript
// filepath: src/services/userService.ts
// action: CREATE

import { User, CreateUserDTO } from '../types/user';

const users: User[] = [];
let nextId = 1;

export function createUser(dto: CreateUserDTO): User {
    const user: User = { id: nextId++, ...dto, createdAt: new Date() };
    users.push(user);
    return user;
}

export function getUsers(): User[] {
    return users;
}

export function getUserById(id: number): User | undefined {
    return users.find(u => u.id === id);
}
```
```typescript
// filepath: src/controllers/userController.ts
// action: CREATE

import { Request, Response } from 'express';
import { createUser, getUsers, getUserById } from '../services/userService';

export function listUsers(req: Request, res: Response): void {
    res.json(getUsers());
}

export function getUser(req: Request, res: Response): void {
    const user = getUserById(Number(req.params.id));
    if (!user) {
        res.status(404).json({ error: 'User not found' });
        return;
    }
    res.json(user);
}

export function createUserHandler(req: Request, res: Response): void {
    const user = createUser(req.body);
    res.status(201).json(user);
}
```

<<TEST_COMMAND>>
npx jest""",
    },

    # ── 4. CSS component split into 4 files ───────────────────────────────────
    {
        "language": "css",
        "file_count": 4,
        "prompt": "Split `styles.css` into four files: `styles/variables.css` (CSS custom properties), `styles/layout/grid.css` (grid system), `styles/components/buttons.css` (button styles), and `styles/components/cards.css` (card styles).",
        "response": """\
<<THINKING>>
Splitting monolithic CSS into variables.css, layout/grid.css, components/buttons.css, components/cards.css.

<<FILES>>
```css
/* filepath: styles/variables.css */
/* action: CREATE */

:root {
    --color-primary: #6366f1;
    --color-primary-dark: #4f46e5;
    --color-secondary: #ec4899;
    --color-background: #0f172a;
    --color-surface: #1e293b;
    --color-text: #f1f5f9;
    --color-text-muted: #94a3b8;

    --spacing-xs: 0.25rem;
    --spacing-sm: 0.5rem;
    --spacing-md: 1rem;
    --spacing-lg: 1.5rem;
    --spacing-xl: 2rem;

    --radius-sm: 0.375rem;
    --radius-md: 0.5rem;
    --radius-lg: 0.75rem;

    --font-sans: 'Inter', system-ui, sans-serif;
    --font-mono: 'JetBrains Mono', monospace;
}
```
```css
/* filepath: styles/layout/grid.css */
/* action: CREATE */

.container {
    width: 100%;
    max-width: 1280px;
    margin-inline: auto;
    padding-inline: var(--spacing-lg);
}

.grid {
    display: grid;
    gap: var(--spacing-md);
}

.grid-2 { grid-template-columns: repeat(2, 1fr); }
.grid-3 { grid-template-columns: repeat(3, 1fr); }
.grid-4 { grid-template-columns: repeat(4, 1fr); }

@media (max-width: 768px) {
    .grid-2, .grid-3, .grid-4 {
        grid-template-columns: 1fr;
    }
}
```
```css
/* filepath: styles/components/buttons.css */
/* action: CREATE */

.btn {
    display: inline-flex;
    align-items: center;
    gap: var(--spacing-xs);
    padding: var(--spacing-sm) var(--spacing-md);
    border: none;
    border-radius: var(--radius-md);
    font-family: var(--font-sans);
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 150ms ease;
}

.btn-primary {
    background: var(--color-primary);
    color: #fff;
}

.btn-primary:hover {
    background: var(--color-primary-dark);
    transform: translateY(-1px);
}

.btn-ghost {
    background: transparent;
    color: var(--color-text-muted);
    border: 1px solid var(--color-surface);
}

.btn-ghost:hover {
    color: var(--color-text);
    border-color: var(--color-primary);
}
```
```css
/* filepath: styles/components/cards.css */
/* action: CREATE */

.card {
    background: var(--color-surface);
    border-radius: var(--radius-lg);
    padding: var(--spacing-lg);
    border: 1px solid rgba(255, 255, 255, 0.06);
    transition: border-color 200ms ease, transform 200ms ease;
}

.card:hover {
    border-color: var(--color-primary);
    transform: translateY(-2px);
}

.card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: var(--spacing-md);
}

.card-title {
    font-size: 1rem;
    font-weight: 600;
    color: var(--color-text);
}

.card-body {
    color: var(--color-text-muted);
    font-size: 0.875rem;
    line-height: 1.6;
}
```

<<TEST_COMMAND>>
none""",
    },

    # ── 5. Go CLI tool split into 3 files ─────────────────────────────────────
    {
        "language": "go",
        "file_count": 3,
        "prompt": "Create a Go CLI database pinger split into three files: `cmd/pinger/main.go` (entry, reads PG_CONN from env), `internal/db/connection.go` (ping function), and `internal/config/config.go` (env config loader).",
        "response": """\
<<THINKING>>
Go CLI pinger: main.go entry, internal/db/connection.go for ping, internal/config/config.go for env loading.

<<FILES>>
```go
// filepath: cmd/pinger/main.go
// action: CREATE

package main

import (
    "fmt"
    "log"
    "time"

    "github.com/example/pinger/internal/config"
    "github.com/example/pinger/internal/db"
)

func main() {
    cfg := config.Load()
    log.Printf("Starting pinger for %s (interval: %s)", cfg.PGDSN, cfg.Interval)

    for {
        if err := db.Ping(cfg.PGDSN); err != nil {
            log.Printf("[FAIL] %v", err)
        } else {
            fmt.Println("[OK] Database reachable")
        }
        time.Sleep(cfg.Interval)
    }
}
```
```go
// filepath: internal/db/connection.go
// action: CREATE

package db

import (
    "database/sql"
    "fmt"

    _ "github.com/lib/pq"
)

func Ping(dsn string) error {
    db, err := sql.Open("postgres", dsn)
    if err != nil {
        return fmt.Errorf("open: %w", err)
    }
    defer db.Close()

    if err := db.Ping(); err != nil {
        return fmt.Errorf("ping: %w", err)
    }
    return nil
}
```
```go
// filepath: internal/config/config.go
// action: CREATE

package config

import (
    "os"
    "time"
)

type Config struct {
    PGDSN    string
    Interval time.Duration
}

func Load() Config {
    dsn := os.Getenv("PG_CONN")
    if dsn == "" {
        dsn = "postgres://localhost/postgres?sslmode=disable"
    }
    return Config{
        PGDSN:    dsn,
        Interval: 5 * time.Second,
    }
}
```

<<TEST_COMMAND>>
go test ./...""",
    },

    # ── 6. Fastify migration: 4 JS files ──────────────────────────────────────
    {
        "language": "javascript",
        "file_count": 4,
        "prompt": "Migrate from Express to Fastify. Rewrite these 4 files: `server.js` (Fastify server setup), `routes/api.js` (root GET /api route), `routes/users.js` (GET /users route), and `middleware/logger.js` (Fastify logger plugin).",
        "response": """\
<<THINKING>>
Migrating 4 files from Express to Fastify: server.js, routes/api.js, routes/users.js, middleware/logger.js.

<<FILES>>
```javascript
// filepath: server.js
// action: MODIFY

const fastify = require('fastify')({ logger: false });
const loggerPlugin = require('./middleware/logger');
const apiRoutes = require('./routes/api');
const usersRoutes = require('./routes/users');

fastify.register(loggerPlugin);
fastify.register(apiRoutes);
fastify.register(usersRoutes);

const start = async () => {
    try {
        await fastify.listen({ port: 3000, host: '0.0.0.0' });
        console.log('Server running on port 3000');
    } catch (err) {
        fastify.log.error(err);
        process.exit(1);
    }
};

start();
```
```javascript
// filepath: routes/api.js
// action: MODIFY

async function apiRoutes(fastify, options) {
    fastify.get('/api', async (request, reply) => {
        return { status: 'ok', version: '1.0.0' };
    });
}

module.exports = apiRoutes;
```
```javascript
// filepath: routes/users.js
// action: MODIFY

const users = [
    { id: 1, name: 'Alice' },
    { id: 2, name: 'Bob' },
];

async function usersRoutes(fastify, options) {
    fastify.get('/users', async (request, reply) => {
        return users;
    });
}

module.exports = usersRoutes;
```
```javascript
// filepath: middleware/logger.js
// action: MODIFY

const fp = require('fastify-plugin');

async function loggerPlugin(fastify, options) {
    fastify.addHook('onRequest', async (request, reply) => {
        console.log(`[${new Date().toISOString()}] ${request.method} ${request.url}`);
    });
}

module.exports = fp(loggerPlugin);
```

<<TEST_COMMAND>>
npm test""",
    },

    # ── 7. TypeScript React components: 3 files ───────────────────────────────
    {
        "language": "typescript",
        "file_count": 3,
        "prompt": "Create three TypeScript React component files: `components/Button.tsx` (reusable button with variant prop), `components/Card.tsx` (card with title and children), and `components/index.ts` (re-export barrel).",
        "response": """\
<<THINKING>>
Three TypeScript React files: Button.tsx component, Card.tsx component, index.ts barrel export.

<<FILES>>
```typescript
// filepath: components/Button.tsx
// action: CREATE

import React from 'react';

interface ButtonProps {
    variant?: 'primary' | 'secondary' | 'ghost';
    size?: 'sm' | 'md' | 'lg';
    disabled?: boolean;
    onClick?: () => void;
    children: React.ReactNode;
}

export const Button: React.FC<ButtonProps> = ({
    variant = 'primary',
    size = 'md',
    disabled = false,
    onClick,
    children,
}) => {
    const classes = [
        'btn',
        `btn-${variant}`,
        `btn-${size}`,
        disabled ? 'btn-disabled' : '',
    ].filter(Boolean).join(' ');

    return (
        <button
            className={classes}
            disabled={disabled}
            onClick={onClick}
            type="button"
        >
            {children}
        </button>
    );
};
```
```typescript
// filepath: components/Card.tsx
// action: CREATE

import React from 'react';

interface CardProps {
    title: string;
    subtitle?: string;
    children: React.ReactNode;
    className?: string;
}

export const Card: React.FC<CardProps> = ({ title, subtitle, children, className = '' }) => {
    return (
        <div className={`card ${className}`}>
            <div className="card-header">
                <h3 className="card-title">{title}</h3>
                {subtitle && <p className="card-subtitle">{subtitle}</p>}
            </div>
            <div className="card-body">
                {children}
            </div>
        </div>
    );
};
```
```typescript
// filepath: components/index.ts
// action: CREATE

export { Button } from './Button';
export { Card } from './Card';
```

<<TEST_COMMAND>>
npx jest""",
    },

    # ── 8. Go package split into __init__ equivalent (3 files) ───────────────
    {
        "language": "go",
        "file_count": 3,
        "prompt": "Create a Go `cache` package with three files: `cache/cache.go` (Cache interface), `cache/memory.go` (in-memory implementation with TTL), and `cache/errors.go` (custom error types).",
        "response": """\
<<THINKING>>
Go cache package: cache.go interface, memory.go TTL implementation, errors.go custom errors.

<<FILES>>
```go
// filepath: cache/cache.go
// action: CREATE

package cache

import "time"

// Cache defines the contract for all cache implementations.
type Cache interface {
    Get(key string) ([]byte, error)
    Set(key string, value []byte, ttl time.Duration) error
    Delete(key string) error
    Flush() error
}
```
```go
// filepath: cache/memory.go
// action: CREATE

package cache

import (
    "sync"
    "time"
)

type entry struct {
    value     []byte
    expiresAt time.Time
}

type MemoryCache struct {
    mu    sync.RWMutex
    items map[string]entry
}

func NewMemoryCache() *MemoryCache {
    return &MemoryCache{items: make(map[string]entry)}
}

func (c *MemoryCache) Get(key string) ([]byte, error) {
    c.mu.RLock()
    defer c.mu.RUnlock()
    e, ok := c.items[key]
    if !ok || time.Now().After(e.expiresAt) {
        return nil, ErrCacheMiss
    }
    return e.value, nil
}

func (c *MemoryCache) Set(key string, value []byte, ttl time.Duration) error {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.items[key] = entry{value: value, expiresAt: time.Now().Add(ttl)}
    return nil
}

func (c *MemoryCache) Delete(key string) error {
    c.mu.Lock()
    defer c.mu.Unlock()
    delete(c.items, key)
    return nil
}

func (c *MemoryCache) Flush() error {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.items = make(map[string]entry)
    return nil
}
```
```go
// filepath: cache/errors.go
// action: CREATE

package cache

import "errors"

var (
    // ErrCacheMiss is returned when a key is not found or has expired.
    ErrCacheMiss = errors.New("cache: key not found or expired")

    // ErrInvalidTTL is returned when a non-positive TTL is provided.
    ErrInvalidTTL = errors.New("cache: TTL must be positive")
)
```

<<TEST_COMMAND>>
go test ./cache/...""",
    },

    # ── 9. JavaScript Python package __init__ equivalent (3 JS files) ─────────
    {
        "language": "javascript",
        "file_count": 3,
        "prompt": "Break the monolithic `calculator.js` into a three-file package: `lib/operations/basic.js` (add, subtract, multiply, divide), `lib/operations/advanced.js` (power, sqrt, factorial), and `lib/index.js` (re-export all operations).",
        "response": """\
<<THINKING>>
Splitting calculator.js into lib/operations/basic.js, lib/operations/advanced.js, lib/index.js.

<<FILES>>
```javascript
// filepath: lib/operations/basic.js
// action: CREATE

function add(a, b) { return a + b; }
function subtract(a, b) { return a - b; }
function multiply(a, b) { return a * b; }
function divide(a, b) {
    if (b === 0) throw new Error('Division by zero');
    return a / b;
}

module.exports = { add, subtract, multiply, divide };
```
```javascript
// filepath: lib/operations/advanced.js
// action: CREATE

function power(base, exp) { return Math.pow(base, exp); }
function sqrt(n) {
    if (n < 0) throw new Error('Cannot take sqrt of negative number');
    return Math.sqrt(n);
}
function factorial(n) {
    if (n < 0) throw new Error('Factorial undefined for negative numbers');
    if (n === 0 || n === 1) return 1;
    return n * factorial(n - 1);
}

module.exports = { power, sqrt, factorial };
```
```javascript
// filepath: lib/index.js
// action: CREATE

const basic = require('./operations/basic');
const advanced = require('./operations/advanced');

module.exports = { ...basic, ...advanced };
```

<<TEST_COMMAND>>
npm test""",
    },

    # ── 10. Go gRPC service: 4 files ──────────────────────────────────────────
    {
        "language": "go",
        "file_count": 4,
        "prompt": "Create a minimal Go gRPC user service with four files: `proto/user.proto` (service definition), `server/server.go` (gRPC server), `server/handlers.go` (CreateUser and GetUser handlers), and `cmd/main.go` (entry point).",
        "response": """\
<<THINKING>>
Go gRPC user service: proto definition, server.go setup, handlers.go, cmd/main.go entry point. Four files.

<<FILES>>
```protobuf
// filepath: proto/user.proto
// action: CREATE

syntax = "proto3";

package user;

option go_package = "github.com/example/userservice/proto";

service UserService {
    rpc CreateUser (CreateUserRequest) returns (User);
    rpc GetUser    (GetUserRequest)    returns (User);
}

message User {
    string id    = 1;
    string name  = 2;
    string email = 3;
}

message CreateUserRequest {
    string name  = 1;
    string email = 2;
}

message GetUserRequest {
    string id = 1;
}
```
```go
// filepath: server/server.go
// action: CREATE

package server

import (
    "net"

    pb "github.com/example/userservice/proto"
    "google.golang.org/grpc"
)

func Start(addr string) error {
    lis, err := net.Listen("tcp", addr)
    if err != nil {
        return err
    }
    s := grpc.NewServer()
    pb.RegisterUserServiceServer(s, &UserServer{users: make(map[string]*pb.User)})
    return s.Serve(lis)
}
```
```go
// filepath: server/handlers.go
// action: CREATE

package server

import (
    "context"
    "fmt"

    pb "github.com/example/userservice/proto"
    "google.golang.org/grpc/codes"
    "google.golang.org/grpc/status"
)

type UserServer struct {
    pb.UnimplementedUserServiceServer
    users map[string]*pb.User
    next  int
}

func (s *UserServer) CreateUser(ctx context.Context, req *pb.CreateUserRequest) (*pb.User, error) {
    s.next++
    user := &pb.User{
        Id:    fmt.Sprintf("%d", s.next),
        Name:  req.Name,
        Email: req.Email,
    }
    s.users[user.Id] = user
    return user, nil
}

func (s *UserServer) GetUser(ctx context.Context, req *pb.GetUserRequest) (*pb.User, error) {
    user, ok := s.users[req.Id]
    if !ok {
        return nil, status.Errorf(codes.NotFound, "user %s not found", req.Id)
    }
    return user, nil
}
```
```go
// filepath: cmd/main.go
// action: CREATE

package main

import (
    "log"

    "github.com/example/userservice/server"
)

func main() {
    addr := ":50051"
    log.Printf("gRPC server listening on %s", addr)
    if err := server.Start(addr); err != nil {
        log.Fatalf("server failed: %v", err)
    }
}
```

<<TEST_COMMAND>>
go test ./...""",
    },

    # ── 11. CSS design system: 4 files ────────────────────────────────────────
    {
        "language": "css",
        "file_count": 4,
        "prompt": "Create a minimal CSS design system with 4 files: `tokens.css` (design tokens), `typography.css` (heading and body styles), `forms.css` (input, label, select styles), and `utilities.css` (flex/grid helper classes).",
        "response": """\
<<THINKING>>
CSS design system: tokens.css design tokens, typography.css text styles, forms.css form elements, utilities.css helpers.

<<FILES>>
```css
/* filepath: tokens.css */
/* action: CREATE */

:root {
    /* Colors */
    --clr-primary: hsl(245, 80%, 60%);
    --clr-primary-hover: hsl(245, 80%, 50%);
    --clr-danger: hsl(0, 72%, 55%);
    --clr-success: hsl(142, 60%, 45%);
    --clr-bg: hsl(220, 20%, 10%);
    --clr-surface: hsl(220, 18%, 15%);
    --clr-border: hsl(220, 15%, 22%);
    --clr-text: hsl(220, 20%, 92%);
    --clr-text-muted: hsl(220, 12%, 55%);

    /* Typography */
    --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
    --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
    --text-xs: 0.75rem;
    --text-sm: 0.875rem;
    --text-base: 1rem;
    --text-lg: 1.125rem;
    --text-xl: 1.25rem;
    --text-2xl: 1.5rem;
    --text-3xl: 1.875rem;

    /* Spacing */
    --space-1: 0.25rem;
    --space-2: 0.5rem;
    --space-3: 0.75rem;
    --space-4: 1rem;
    --space-6: 1.5rem;
    --space-8: 2rem;

    /* Radii */
    --radius-sm: 0.25rem;
    --radius: 0.5rem;
    --radius-lg: 0.75rem;
    --radius-full: 9999px;
}
```
```css
/* filepath: typography.css */
/* action: CREATE */

*, *::before, *::after { box-sizing: border-box; }

body {
    font-family: var(--font-sans);
    font-size: var(--text-base);
    color: var(--clr-text);
    background: var(--clr-bg);
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
}

h1, h2, h3, h4, h5, h6 {
    font-weight: 700;
    line-height: 1.2;
    color: var(--clr-text);
}

h1 { font-size: var(--text-3xl); }
h2 { font-size: var(--text-2xl); }
h3 { font-size: var(--text-xl); }
h4 { font-size: var(--text-lg); }

p { margin-block: var(--space-3); }

code, kbd, pre {
    font-family: var(--font-mono);
    font-size: 0.9em;
}

code {
    background: var(--clr-surface);
    padding: 0.1em 0.35em;
    border-radius: var(--radius-sm);
    color: var(--clr-primary);
}
```
```css
/* filepath: forms.css */
/* action: CREATE */

label {
    display: block;
    font-size: var(--text-sm);
    font-weight: 500;
    color: var(--clr-text-muted);
    margin-bottom: var(--space-1);
}

input[type="text"],
input[type="email"],
input[type="password"],
input[type="number"],
select,
textarea {
    width: 100%;
    padding: var(--space-2) var(--space-3);
    background: var(--clr-surface);
    border: 1px solid var(--clr-border);
    border-radius: var(--radius);
    color: var(--clr-text);
    font-family: var(--font-sans);
    font-size: var(--text-sm);
    transition: border-color 150ms ease, box-shadow 150ms ease;
    outline: none;
}

input:focus,
select:focus,
textarea:focus {
    border-color: var(--clr-primary);
    box-shadow: 0 0 0 3px hsl(245, 80%, 60%, 0.2);
}

input.error,
select.error {
    border-color: var(--clr-danger);
}

.field { margin-bottom: var(--space-4); }
```
```css
/* filepath: utilities.css */
/* action: CREATE */

/* Flexbox */
.flex { display: flex; }
.flex-col { flex-direction: column; }
.items-center { align-items: center; }
.items-start { align-items: flex-start; }
.justify-center { justify-content: center; }
.justify-between { justify-content: space-between; }
.gap-1 { gap: var(--space-1); }
.gap-2 { gap: var(--space-2); }
.gap-4 { gap: var(--space-4); }

/* Grid */
.grid { display: grid; }
.grid-2 { grid-template-columns: repeat(2, 1fr); }
.grid-3 { grid-template-columns: repeat(3, 1fr); }

/* Spacing */
.p-2 { padding: var(--space-2); }
.p-4 { padding: var(--space-4); }
.p-6 { padding: var(--space-6); }
.px-4 { padding-inline: var(--space-4); }
.py-2 { padding-block: var(--space-2); }
.mt-4 { margin-top: var(--space-4); }
.mb-4 { margin-bottom: var(--space-4); }

/* Text */
.text-sm { font-size: var(--text-sm); }
.text-muted { color: var(--clr-text-muted); }
.font-bold { font-weight: 700; }
.text-center { text-align: center; }

/* Display */
.hidden { display: none; }
.w-full { width: 100%; }
.rounded { border-radius: var(--radius); }
.rounded-full { border-radius: var(--radius-full); }
```

<<TEST_COMMAND>>
none""",
    },

    # ── 12. JavaScript auth module split: 3 files ─────────────────────────────
    {
        "language": "javascript",
        "file_count": 3,
        "prompt": "Split `auth.js` into three files: `auth/models.js` (User class with password hashing), `auth/middleware.js` (JWT verification middleware), and `auth/utils.js` (generateToken and hashPassword helpers).",
        "response": """\
<<THINKING>>
Splitting auth.js into auth/models.js User class, auth/middleware.js JWT middleware, auth/utils.js helpers.

<<FILES>>
```javascript
// filepath: auth/models.js
// action: CREATE

const { hashPassword } = require('./utils');

class User {
    constructor({ id, name, email, password }) {
        this.id = id;
        this.name = name;
        this.email = email;
        this.passwordHash = hashPassword(password);
    }

    toJSON() {
        return { id: this.id, name: this.name, email: this.email };
    }
}

module.exports = { User };
```
```javascript
// filepath: auth/middleware.js
// action: CREATE

const jwt = require('jsonwebtoken');
const SECRET = process.env.JWT_SECRET || 'dev-secret';

function verifyToken(req, res, next) {
    const header = req.headers['authorization'] || '';
    const token = header.startsWith('Bearer ') ? header.slice(7) : null;

    if (!token) {
        return res.status(401).json({ error: 'Missing token' });
    }

    try {
        req.user = jwt.verify(token, SECRET);
        next();
    } catch {
        res.status(401).json({ error: 'Invalid or expired token' });
    }
}

module.exports = { verifyToken };
```
```javascript
// filepath: auth/utils.js
// action: CREATE

const crypto = require('crypto');
const jwt = require('jsonwebtoken');
const SECRET = process.env.JWT_SECRET || 'dev-secret';

function hashPassword(password) {
    return crypto.createHash('sha256').update(password).digest('hex');
}

function generateToken(payload, expiresIn = '24h') {
    return jwt.sign(payload, SECRET, { expiresIn });
}

module.exports = { hashPassword, generateToken };
```

<<TEST_COMMAND>>
npm test""",
    },

]


def to_jsonl_entry(seed: dict) -> dict:
    """Convert a seed to a training JSONL entry in the Nova format."""
    return {
        "messages": [
            {"role": "user", "content": seed["prompt"]},
            {"role": "assistant", "content": seed["response"]},
        ],
        "metadata": {
            "category": "multi_file_multi_language",
            "language": seed["language"],
            "file_count": seed["file_count"],
            "version": "v1_seed",
        }
    }


if __name__ == "__main__":
    import json
    from collections import Counter

    print(f"Multi-File Seed Examples ({len(MULTIFILE_SEEDS)} total)")
    print("=" * 70)

    lang_counts = Counter(s["language"] for s in MULTIFILE_SEEDS)
    file_counts = Counter(s["file_count"] for s in MULTIFILE_SEEDS)
    print(f"Languages: {dict(lang_counts)}")
    print(f"File counts: {dict(file_counts)}")
    print()

    for i, seed in enumerate(MULTIFILE_SEEDS, 1):
        print(f"[{i}] Lang: {seed['language']} | Files: {seed['file_count']}")
        print(f"     Prompt: {seed['prompt'][:80]}...")

    print("\n" + "=" * 70)
    print("JSONL format (first entry):")
    print(json.dumps(to_jsonl_entry(MULTIFILE_SEEDS[0]), indent=2))
