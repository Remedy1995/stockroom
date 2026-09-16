# Stockroom submission description

Stockroom is a production-ready inventory REST API with a browser demo that makes its behavior easy to evaluate. A user creates a private workspace, signs in, then manages products with create, list, detail, update, and delete operations. The app includes search, filtering, pagination, inventory value summaries, low-stock status, CSV export, and an audit log.

Authentication uses Argon2 password hashing and opaque session tokens. Browser sessions use strict HttpOnly cookies, while API clients can use the same token as a bearer credential. Expiring, single-use verification and password-reset links support account recovery flows. Users have owner, editor, or viewer roles. Each database query is scoped to the authenticated user's workspace, so a guessed identifier from another workspace does not reveal data. Owners add and remove members; editors manage inventory; viewers read it.

The API is designed for operational safety. It uses strict request models, database constraints, request IDs, structured errors, pagination limits, body-size limits, persisted rate limits, no-store API responses, security headers, restrictive origins and trusted hosts, health endpoints, schema migrations, Docker configuration, CI checks, and optimistic locking. Inventory updates include a version number, so concurrent edits produce a clear conflict instead of overwriting newer work.

The repository includes integration tests that verify authentication, authorization, workspace isolation, validation, the CRUD lifecycle, audit logging, conflict handling, session revocation, and health/security headers. The interactive OpenAPI reference is available at `/docs` when the app runs.

Public GitHub repository URL: _Add after publishing_  
Demo video URL: _Add after recording/uploading_
