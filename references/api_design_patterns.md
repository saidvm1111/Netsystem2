# API Design Patterns

A practical reference for designing robust, scalable, and developer-friendly APIs.

---

## 1. REST API Conventions

### Resource Naming

| Pattern | Example |
|---------|---------|
| Plural nouns for collections | `GET /users` |
| Singular noun for a resource | `GET /users/:id` |
| Nested resources (max 2 levels) | `GET /users/:id/orders` |
| Actions as sub-resources | `POST /orders/:id/cancel` |

### HTTP Methods

| Method | Semantics | Idempotent | Body |
|--------|-----------|-----------|------|
| GET | Read resource(s) | Yes | No |
| POST | Create resource | No | Yes |
| PUT | Replace resource | Yes | Yes |
| PATCH | Partial update | No | Yes |
| DELETE | Remove resource | Yes | No |

### Status Codes

```
200 OK              – successful GET, PUT, PATCH
201 Created         – successful POST (include Location header)
204 No Content      – successful DELETE
400 Bad Request     – malformed request / validation failure
401 Unauthorized    – missing or invalid credentials
403 Forbidden       – authenticated but not authorized
404 Not Found       – resource doesn't exist
409 Conflict        – state conflict (duplicate key, optimistic lock)
422 Unprocessable   – semantic validation errors
429 Too Many Req.   – rate limit exceeded
500 Internal Error  – unexpected server error
503 Unavailable     – downstream dependency down
```

### Versioning

Prefer URL versioning for public APIs (`/api/v1/`). Use header versioning
(`Accept: application/vnd.myapi.v2+json`) when clients control the header.

---

## 2. Request & Response Shape

### Standard Response Envelope

```json
{
  "data": { ... },
  "meta": { "total": 100, "page": 1, "per_page": 20 },
  "errors": null
}
```

### Error Response

```json
{
  "error": {
    "code":    "VALIDATION_FAILED",
    "message": "Human-readable description",
    "details": [
      { "field": "email", "message": "must be a valid email" }
    ]
  }
}
```

### Pagination

```
GET /users?page=2&per_page=20        (offset-based, simple)
GET /users?cursor=eyJpZCI6MTAwfQ==   (cursor-based, stable for large sets)
```

Response headers:
```
X-Total-Count: 2345
Link: <https://api.example.com/users?page=3>; rel="next"
```

### Filtering & Sorting

```
GET /orders?status=pending&created_after=2024-01-01
GET /users?sort=-created_at,email      (- prefix = descending)
GET /users?fields=id,email,name        (sparse fieldsets)
```

---

## 3. GraphQL Patterns

### Schema-first Design

Define the schema before implementing resolvers. Use SDL (Schema Definition Language):

```graphql
type Query {
  user(id: ID!): User
  users(filter: UserFilter, pagination: PaginationInput): UserConnection!
}

type Mutation {
  createUser(input: CreateUserInput!): CreateUserPayload!
}

type Subscription {
  orderUpdated(orderId: ID!): Order!
}
```

### Cursor-based Pagination (Relay spec)

```graphql
type UserConnection {
  edges: [UserEdge!]!
  pageInfo: PageInfo!
  totalCount: Int!
}

type UserEdge {
  node: User!
  cursor: String!
}

type PageInfo {
  hasNextPage: Boolean!
  hasPreviousPage: Boolean!
  startCursor: String
  endCursor: String
}
```

### DataLoader Pattern (N+1 prevention)

```javascript
const userLoader = new DataLoader(async (ids) => {
  const users = await db.query('SELECT * FROM users WHERE id = ANY($1)', [ids]);
  return ids.map(id => users.find(u => u.id === id) ?? null);
});
```

---

## 4. API Gateway Patterns

### Rate Limiting Strategies

| Strategy | Use case |
|----------|---------|
| Token bucket | Smooth bursts, recommended for most APIs |
| Leaky bucket | Strict constant rate |
| Fixed window | Simple, but boundary spike risk |
| Sliding window | Accurate, higher memory cost |

### Idempotency Keys

For non-idempotent operations (payments, emails), require an `Idempotency-Key` header.
Cache responses by key for 24 h. Return the same response for duplicate requests.

```
POST /payments
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
```

---

## 5. Webhook Design

- Use HTTPS only.
- Sign payloads with HMAC-SHA256; include signature in `X-Signature-256` header.
- Deliver with at-least-once semantics; document event schema versioning.
- Retry with exponential backoff (1 s, 5 s, 30 s, 5 min, 30 min).
- Include `X-Event-Type`, `X-Delivery-ID`, and `X-Timestamp` headers.
- Provide a replay endpoint for consumers to re-fetch missed events.

---

## 6. API Documentation Checklist

- [ ] OpenAPI / AsyncAPI spec committed alongside code
- [ ] Every endpoint has a summary, description, and example request/response
- [ ] Error codes documented with resolution steps
- [ ] Authentication method clearly described
- [ ] Rate limits documented
- [ ] Changelog maintained for breaking changes
- [ ] SDK / code samples provided for common languages
