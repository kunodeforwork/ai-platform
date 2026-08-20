# API Key Authentication Design

## Goal

Protect every business API with one deployment-provided platform API key while keeping
health checks and API documentation available. The slice establishes a small security
boundary that can later be replaced by tenant-aware credentials without coupling
authentication to Agent, persistence, or model execution code.

## Scope

- Require HTTP Bearer authentication for both current `/api/v1` router families:
  Agent configuration and Agent runs.
- Read one `PLATFORM_API_KEY` from the process environment lazily.
- Keep `/health`, `/docs`, and `/openapi.json` public.
- Publish the Bearer scheme and protected-operation requirements in OpenAPI.
- Preserve every existing authenticated success response and downstream error contract.

This slice does not include login, credential issuance or rotation, multiple keys, users,
RBAC, tenant isolation, JWT, OAuth, rate limiting, or actor attribution in run audit
records.

## Approach

Use a FastAPI router-level dependency when the two business routers are included in the
application. This centralizes enforcement, makes omission on individual endpoints less
likely, and lets FastAPI generate the OpenAPI security declaration. It is preferred over
path-matching middleware, which would duplicate routing knowledge, and per-endpoint
declarations, which are repetitive and easy to omit.

## Components

### Authentication boundary

Add `src/chint_ai_platform/auth.py` with these responsibilities:

- lazily read and validate `PLATFORM_API_KEY`;
- extract a Bearer credential through FastAPI's HTTP Bearer security scheme;
- compare the presented and configured values with `secrets.compare_digest`;
- raise stable boundary exceptions without embedding credentials;
- register safe HTTP exception mappings.

The module exposes a `require_api_key` dependency. It returns no business value: passing
the boundary only authorizes execution to continue. Agent services, repositories, and
DeepSeek adapters never receive the key.

### Application composition

`main.py` attaches `require_api_key` as an include-level dependency to the Agent
configuration and Agent run routers. The health route remains outside those protected
router registrations. FastAPI's documentation and OpenAPI endpoints are also left at
their default public locations.

The dependency must remain lazy. Missing authentication configuration does not prevent
application construction, health checks, documentation access, or OpenAPI generation.

## Request Flow

1. A request targets a protected `/api/v1` route.
2. The security dependency parses the `Authorization` header as HTTP Bearer.
3. If the server key is absent or blank, authentication stops with the safe configuration
   error.
4. If the header is missing, malformed, uses another scheme, contains a blank credential,
   or does not match, authentication stops with the same invalid-key response.
5. A valid key allows normal request validation and the existing business flow to run.

Authentication failure must not call an Agent service, create a database Session, invoke
DeepSeek, or write an Agent run audit record. Authorization headers and credentials must
not be logged or persisted by application code.

## Error Contract

Missing or blank server configuration returns:

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{"error":{"code":"auth_not_configured","message":"API authentication is not configured"}}
```

Any invalid client credential returns one indistinguishable response:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Content-Type: application/json

{"error":{"code":"invalid_api_key","message":"Invalid API key"}}
```

The 401 response does not reveal whether the header was absent, malformed, empty, or
incorrect. The 503 response does not reveal environment contents. Existing database,
Agent, validation, and DeepSeek errors remain unchanged after authentication succeeds.

## OpenAPI

The generated document defines an HTTP Bearer security scheme and applies it to every
operation from the two protected routers. `/health` has no security requirement. Swagger
UI remains public and provides its standard **Authorize** control for authenticated API
calls.

## Testing

Unit tests cover:

- valid, missing, blank, and incorrect environment configuration;
- missing, malformed, wrong-scheme, blank, wrong, and valid client credentials;
- use of the constant-time comparison boundary;
- stable exceptions that contain no credential material.

API tests cover:

- both protected router families reject absent and invalid credentials;
- a valid credential preserves representative existing success and error behavior;
- authentication failure short-circuits service, database, DeepSeek, and run recording;
- `/health`, `/docs`, and `/openapi.json` remain public;
- OpenAPI contains the Bearer scheme and protected-operation security requirements.

Existing API tests use a shared fixture to configure the platform key and supply a valid
Authorization header where they are testing behavior beyond authentication. Tests do not
use a real secret or connect to DeepSeek.

## Delivery

Document `PLATFORM_API_KEY` in `.env.example` and `README.md`, including authenticated
PowerShell examples. Run the full pytest suite, Ruff, OpenAPI assertions, a secret scan,
and an independent code review before pushing the feature branch. Merging or pushing
`main` remains a separate explicit approval step.
