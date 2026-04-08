# Backend Security Practices

A checklist-driven reference for building secure backend services.

---

## 1. Authentication

### JWT Best Practices

- Use **HS256** (shared secret) for single-service, **RS256** (asymmetric) for multi-service.
- Set short expiry (`exp`): 15 min for access tokens, 7 days for refresh tokens.
- Store the secret in an environment variable / secrets manager — never in source code.
- Always validate `alg`, `iss`, `aud`, and `exp` claims.
- Implement token rotation: issue a new refresh token on every use (refresh token rotation).
- Maintain a **token revocation list** (Redis set) for logout and compromise response.

```javascript
// Sign
const token = jwt.sign(
  { sub: user.id, email: user.email, role: user.role },
  process.env.JWT_SECRET,
  { expiresIn: '15m', issuer: 'myapi', audience: 'myapp' }
);

// Verify (always specify algorithms)
const payload = jwt.verify(token, process.env.JWT_SECRET, {
  algorithms: ['HS256'],
  issuer: 'myapi',
  audience: 'myapp',
});
```

### Password Storage

- Use **bcrypt** (cost ≥ 12) or **Argon2id** — never MD5, SHA-1, or plain SHA-256.
- Never log, return, or store plaintext passwords.
- Enforce a minimum length (12 chars) and check against HaveIBeenPwned's API.

---

## 2. Authorization

### Principle of Least Privilege

- Assign the minimum permissions needed.
- Use **RBAC** (Role-Based) for coarse-grained access; **ABAC** (Attribute-Based) for fine-grained.
- Always authorize at the service layer, not just the route layer.

```javascript
// Check ownership before returning data
const record = await db.findById(req.params.id);
if (record.user_id !== req.user.sub) {
  throw Object.assign(new Error('Forbidden'), { status: 403 });
}
```

### Row-Level Security (PostgreSQL)

```sql
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY documents_owner ON documents
  USING (owner_id = current_setting('app.user_id')::bigint);
```

Set `app.user_id` at the start of each transaction.

---

## 3. Input Validation & Sanitization

- Validate **all** external input at the boundary (HTTP body, query params, headers, env).
- Use a schema validation library (Joi, Zod, Yup, class-validator).
- Reject unknown fields (`allowUnknown: false` / `stripUnknown: true`).
- Sanitize HTML when rendering user content; prefer an allow-list over a deny-list.

```javascript
const schema = Joi.object({
  email: Joi.string().email().lowercase().trim().required(),
  age:   Joi.number().integer().min(0).max(150),
}).options({ allowUnknown: false });
```

---

## 4. SQL Injection Prevention

Always use parameterized queries. **Never** concatenate user input into SQL.

```javascript
// SAFE
const { rows } = await db.query(
  'SELECT * FROM users WHERE email = $1 AND active = true',
  [req.body.email]
);

// NEVER DO THIS
const { rows } = await db.query(
  `SELECT * FROM users WHERE email = '${req.body.email}'`  // SQL injection
);
```

With ORMs, avoid raw queries unless necessary; always use the ORM's parameter binding.

---

## 5. HTTP Security Headers

Use `helmet` (Node.js) or equivalent middleware:

| Header | Value |
|--------|-------|
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Content-Security-Policy` | Strict policy; `default-src 'self'` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | Deny unused browser features |

Remove `X-Powered-By` to avoid fingerprinting.

---

## 6. Rate Limiting & Abuse Prevention

```javascript
const rateLimit = require('express-rate-limit');

// Global limit
app.use(rateLimit({ windowMs: 15 * 60 * 1000, max: 100 }));

// Stricter limit on auth endpoints
app.use('/api/v1/auth', rateLimit({
  windowMs: 60 * 60 * 1000,  // 1 hour
  max: 10,
  skipSuccessfulRequests: true,
}));
```

Use a distributed store (Redis) for rate limit state in multi-instance deployments.

---

## 7. Secrets Management

| Do | Don't |
|----|-------|
| Store secrets in environment variables or a secrets manager (AWS Secrets Manager, Vault, Doppler) | Hard-code secrets in source code |
| Rotate secrets regularly; automate rotation | Use the same secret across environments |
| Use separate secrets per environment | Commit `.env` files to version control |
| Audit secret access | Share secrets over chat/email |

`.gitignore` must include `.env`, `*.pem`, `*.key`, `credentials.json`.

---

## 8. Dependency Security

```bash
# Audit regularly
npm audit --audit-level=high

# Pin exact versions in production
npm ci  # uses package-lock.json exactly

# Automated PRs for updates
# Use Dependabot or Renovate Bot
```

Remove unused dependencies. Never install packages from untrusted sources.

---

## 9. Logging & Monitoring

### What to Log

- Authentication events (success, failure, token refresh)
- Authorization failures
- Unusual activity (high error rates, large payloads)
- Input validation failures (aggregated)

### What NOT to Log

- Passwords, tokens, API keys
- Full credit card numbers (PCI-DSS)
- PII beyond what is strictly necessary (GDPR/CCPA)
- Full request bodies in production

### Structured Logging

```javascript
logger.info({
  event:      'auth.login',
  user_id:    user.id,
  ip:         req.ip,
  user_agent: req.headers['user-agent'],
  success:    true,
});
```

---

## 10. Security Checklist

### Before Every Release

- [ ] `npm audit` / `pip-audit` with no high/critical findings
- [ ] Secrets not committed (pre-commit hook: `detect-secrets`)
- [ ] OWASP Top 10 self-review completed
- [ ] Input validation covers all new endpoints
- [ ] New endpoints have authentication/authorization tests
- [ ] Error messages don't leak stack traces or internal details in production
- [ ] Rate limiting applied to new endpoints
- [ ] Database queries use parameterized statements

### Infrastructure

- [ ] TLS 1.2+ enforced; TLS 1.0/1.1 disabled
- [ ] Certificates auto-renewed (Let's Encrypt / ACM)
- [ ] Database not exposed to the public internet
- [ ] Principle of least privilege applied to IAM roles / DB users
- [ ] Security groups / firewall rules reviewed
- [ ] VPC flow logs and CloudTrail (or equivalent) enabled
