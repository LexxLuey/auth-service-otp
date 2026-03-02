# Django Authentication Service with OTP - Implementation Roadmap

## Phase 1: Project Foundation and Setup (Day 1, Hours 1-3)

### 1.1 Initial Project Structure

- Create project root directory with proper naming convention
- Initialize Git repository with appropriate .gitignore (Python, Docker, IDE files)
- Create directory structure following modular Django pattern:

  ```
  project_root/
  ├── apps/
  │   ├── accounts/
  │   └── audit/
  ├── config/
  ├── docker/
  ├── docs/
  └── scripts/
  ```

### 1.2 Environment and Dependencies

- Create requirements.txt with all required packages:
  - Django and Django REST Framework
  - Redis and Redis client libraries
  - Celery and Celery beat
  - djangorestframework-simplejwt
  - drf-spectacular
  - python-dotenv
  - psycopg2-binary
  - Additional utilities: django-filter, django-cors-headers (if needed)
- Create .env.example file with all required environment variables:
  - Database credentials and connection strings
  - Redis connection details
  - Django secret key and debug settings
  - JWT settings (algorithm, expiration times)
  - Email backend configuration (console backend for demo)
- Document all environment variables with descriptions and examples

### 1.3 Docker Configuration

- Create Dockerfile for Django application:
  - Use official Python slim image
  - Set up working directory
  - Install system dependencies if needed
  - Copy requirements and install Python packages
  - Configure entrypoint script for waiting on dependencies
- Create docker-compose.yml with services:
  - web: Django application with volume mounts for development
  - postgres: Official PostgreSQL image with volume for data persistence
  - redis: Official Redis image with basic configuration
  - celery_worker: Celery worker service (depends on web, redis)
- Create docker-entrypoint.sh script to wait for database and redis before starting
- Configure volume mounts for live code reloading in development

### 1.4 Django Project Configuration

- Initialize Django project in config/ directory
- Configure settings module with environment-based configuration:
  - Base settings for common configuration
  - Development settings with debug enabled
  - Production-like settings for docker (debug off)
- Set up URL routing structure with versioning (/api/v1/)
- Configure database connection using environment variables
- Set up Redis cache backend for future use
- Configure JWT settings (access token lifetime, refresh token lifetime)
- Set up drf-spectacular for OpenAPI documentation

### 1.5 Testing Framework Setup

- Configure pytest with pytest-django
- Create base test classes and fixtures
- Set up test database configuration
- Create initial test structure mirroring app structure
- Configure coverage reporting

## Phase 2: Core Models and Base Infrastructure (Day 1, Hours 4-6)

### 2.1 User Model Customization

- Create custom user model in accounts app:
  - Use email as username field (remove username)
  - Add necessary fields (is_active, is_staff, date_joined)
  - Configure USERNAME_FIELD and REQUIRED_FIELDS
- Create and run initial migrations
- Update AUTH_USER_MODEL in settings
- Create admin registration for user model

### 2.2 Audit Log Model

- Design AuditLog model in audit app with fields:
  - event (choices: OTP_REQUESTED, OTP_VERIFIED, OTP_FAILED, OTP_LOCKED)
  - email (indexed for filtering)
  - ip_address (generic IP field)
  - user_agent (text field)
  - metadata (JSON field for additional data)
  - created_at (auto timestamp, indexed)
- Add appropriate indexes for common filters (email, event, created_at)
- Create model methods for structured logging
- Register model with admin interface
- Create and run migrations

### 2.3 Redis Service Layer

- Create Redis client wrapper/utility in accounts app:
  - Connection management with connection pooling
  - Error handling and reconnection logic
  - Key naming conventions with prefixes
- Implement atomic Redis operations:
  - SET with EX and NX for OTP storage
  - INCR with EXPIRE for counters
  - GET and DELETE for one-time operations
  - TTL inspection for rate limit responses
- Create helper functions for:
  - OTP storage and retrieval
  - Rate limit counters (email and IP based)
  - Failed attempt tracking with lockout mechanism
  - Atomic increment with expiry

### 2.4 Celery Configuration

- Set up Celery application in config/celery.py
- Configure Redis as both broker and result backend
- Define task base classes with error handling
- Create task decorators for common patterns
- Configure task routing if needed (separate queues)
- Set up periodic task discovery (though not required, good practice)
- Create celery.py in project root for worker discovery

## Phase 3: OTP Request Flow Implementation (Day 2, Hours 1-3)

### 3.1 OTP Request Serializer and Validation

- Create OTPRequestSerializer in accounts app:
  - Email field with validation (format, required)
  - Custom validation hooks for rate limit checks
  - Clean error messages following API consistency
- Implement serializer-level validation that calls Redis rate limit checks
- Add method to generate 6-digit OTP using secrets module

### 3.2 Rate Limiting Implementation

- Implement Redis-based rate limiting service:
  - Email rate limit: 3 requests per 10 minutes
  - IP rate limit: 10 requests per 1 hour
- Create decorator or mixin for view rate limiting
- Calculate retry-after seconds from Redis TTL
- Standardize error response format for rate limits:
  - Detail message explaining limit
  - Retry-after in seconds (if available)
  - Limit type that was exceeded

### 3.3 OTP Storage Service

- Create OTP storage service with Redis:
  - Store OTP with 5-minute TTL
  - Use secure key format (e.g., otp:{email})
  - Include metadata if needed (creation time)
- Implement retrieval and validation logic
- Ensure one-time use by atomic delete after verification

### 3.4 OTP Request View

- Create APIView or ViewSet for OTP request endpoint
- Implement POST method handling:
  - Validate incoming data with serializer
  - Check rate limits (raise 429 if exceeded)
  - Generate and store OTP
  - Trigger Celery tasks (don't wait for completion)
  - Return 202 with expiry information
- Add drf-spectacular decorators for OpenAPI documentation:
  - Request body schema
  - Response schemas (202, 429, 400)
  - Example requests and responses
  - Status code descriptions

### 3.5 Celery Tasks for OTP Request

- Create send_otp_email task in accounts app:
  - Accept email and OTP parameters
  - Log to console as per requirement
  - Handle potential failures gracefully
  - Retry logic (3 attempts with exponential backoff)
- Create write_audit_log task in audit app:
  - Accept event, email, ip, user_agent, metadata
  - Create AuditLog record asynchronously
  - Handle database connection issues
  - Ensure task idempotency
- Configure task routing if multiple queues

## Phase 4: OTP Verify Flow Implementation (Day 2, Hours 4-6)

### 4.1 OTP Verify Serializer

- Create OTPVerifySerializer in accounts app:
  - Email field with validation
  - OTP field (6 digits, required)
  - Custom validation to check Redis for OTP validity
  - Track failed attempts during validation
- Implement lockout check before OTP validation
- Add method to check and increment failed attempts atomically

### 4.2 Failed Attempt Tracking

- Implement failed attempts counter in Redis:
  - Key format: failed_attempts:{email}
  - 15-minute TTL (reset after lockout)
  - Max 5 attempts before lockout
- Create lockout mechanism:
  - After 5 failures, set lock flag with TTL
  - Calculate remaining lock time for response
  - Return 423 Locked with unlock ETA
- Ensure atomic operations for counter increments

### 4.3 User Creation/Update Logic

- Implement service function for user management:
  - Get or create user by email
  - Update last_login or similar fields
  - Ensure user is active
  - Return user instance
- Keep logic separate from view for reusability

### 4.4 JWT Token Generation

- Configure SimpleJWT settings:
  - Access token lifetime (short-lived, e.g., 15 minutes)
  - Refresh token lifetime (longer, e.g., 7 days)
  - Token payload customization (include email)
- Create token service function:
  - Generate tokens for user
  - Return structured response with tokens
- Add token refresh endpoint if desired (optional but good)

### 4.5 OTP Verify View

- Create OTP verify endpoint view:
  - Accept POST requests with serializer
  - Check for active lockout (return 423)
  - Validate OTP against Redis
  - Handle success: delete OTP, create/update user, generate tokens
  - Handle failure: increment failed attempts, trigger audit
- Add proper exception handling for edge cases
- Document with drf-spectacular:
  - Request/response schemas
  - Success response with tokens
  - Error responses (400, 423, 429)
  - Example flows

### 4.6 Audit Events for Verify Flow

- Create audit task calls for:
  - OTP_VERIFIED on success
  - OTP_FAILED on wrong OTP
  - OTP_LOCKED when lockout triggered
- Include relevant metadata (attempt count, remaining lock time)
- Ensure tasks are async and don't block response

## Phase 5: Audit Log Endpoint Implementation (Day 3, Hours 1-2)

### 5.1 Audit Log Serializer and View

- Create AuditLogSerializer with all model fields
- Implement read-only fields (no writes through API)
- Add validation for filter parameters
- Create AuditLogViewSet with:
  - JWT authentication required
  - Pagination (default page size 20)
  - Filter backends for query params
  - Ordering filter (default -created_at)
- Implement filter methods for:
  - email (exact match)
  - event (choice filter)
  - from_date (gte on created_at)
  - to_date (lte on created_at)

### 5.2 Filtering and Pagination

- Configure django-filter or custom filter backend
- Set up pagination class with page size parameter
- Ensure proper queryset optimization (select_related if any)
- Add metadata to paginated responses (count, next, previous)

### 5.3 Documentation and Permissions

- Set up JWT authentication class
- Configure drf-spectacular for audit endpoints:
  - Document filter parameters
  - Show paginated response structure
  - Include authentication requirement
  - Add example requests with filters
- Test permission enforcement

## Phase 6: Testing and Documentation (Day 3, Hours 2-4)

### 6.1 Unit Tests

- Write tests for models:
  - AuditLog string representation
  - Custom model methods
- Write tests for serializers:
  - Validation logic
  - Error messages
  - Edge cases (empty, invalid)
- Write tests for Redis services:
  - Atomic operations
  - TTL behavior
  - Race condition prevention
- Write tests for Celery tasks:
  - Task execution
  - Error handling
  - Database operations

### 6.2 Integration Tests

- Test OTP request flow:
  - Successful request
  - Rate limit triggers
  - Concurrent requests handling
- Test OTP verify flow:
  - Successful verification
  - Wrong OTP attempts
  - Lockout mechanism
  - JWT token generation
- Test audit log endpoint:
  - Authentication required
  - Filtering functionality
  - Pagination
- Use pytest fixtures for database and Redis

### 6.3 API Documentation Enhancement

- Enhance drf-spectacular configuration:
  - Add API title and description
  - Configure versioning
  - Add security schemes (JWT)
- Decorate all endpoints with:
  - Summary and description
  - Response status codes with descriptions
  - Example requests (using examples)
  - Example responses
- Test Swagger UI accessibility
- Ensure all schemas are accurate

## Phase 7: Docker Compose Polish and Final Testing (Day 3, Hours 4-5)

### 7.1 Docker Compose Refinement

- Test multi-container orchestration:
  - Service dependencies and startup order
  - Volume mounts for development
  - Environment variable propagation
  - Network configuration
- Create initialization scripts:
  - Wait for database
  - Run migrations automatically
  - Create superuser if needed (optional)
- Test single command startup: docker compose up --build

### 7.2 Environment Configuration

- Finalize .env.example with all variables:
  - Django settings (SECRET_KEY, DEBUG)
  - Database (POSTGRES_DB, USER, PASSWORD)
  - Redis (REDIS_URL, REDIS_PASSWORD if used)
  - JWT (SIGNING_KEY, ALGORITHM, expirations)
  - Email (EMAIL_BACKEND, console for demo)
- Document all variables in README

### 7.3 Final Integration Testing

- Run through demo flow locally:
  - Build and start containers
  - Access Swagger UI
  - Test OTP request happy path
  - Test rate limiting
  - Test OTP verify failure
  - Test lockout
  - Test successful verification with JWT
  - Test audit logs with filters
  - Check Celery logs for task execution
- Verify all Redis keys have proper TTLs
- Check database for audit log entries

## Phase 8: Documentation and Submission (Day 3, Hours 5-6)

### 8.1 README Creation

- Write comprehensive README with:
  - Project title and description
  - Prerequisites (Docker, Docker Compose)
  - Quick start guide
  - Environment variables (reference to .env.example)
  - API documentation link (Swagger UI)
  - Project structure overview
  - Testing instructions
  - Troubleshooting common issues

### 8.2 Code Cleanup and Final Review

- Run code through linters (flake8, black)
- Check for PEP8 compliance
- Apply Zen of Python principles:
  - Simple is better than complex
  - Readability counts
  - Errors should never pass silently
- Verify DRY principle:
  - Extract repeated logic to services
  - Use base classes for common patterns
- Check 12-factor app compliance:
  - Environment variable configuration
  - Backing services as attached resources
  - Logs as event streams

### 8.3 Final Git Operations

- Commit all changes with clear messages
- Create .gitignore for sensitive files
- Push to public GitHub repository
- Test clone on clean machine
- Verify all deliverables are present

### 8.4 Submission Preparation

- Prepare email with:
  - Public GitHub repository URL
  - Any additional notes for evaluators
  - Confirmation of requirements met
- Send to both email addresses
- Keep copy of sent email

## Critical Success Factors to Verify

### Redis Atomicity

- All counter operations use INCR with EXPIRE
- OTP verification deletes key in same operation as check
- No race conditions in rate limit checking

### Celery Asynchronicity

- Views don't wait for task completion
- Tasks are visible in worker logs
- Failed tasks have retry logic

### Rate Limit Accuracy

- Email limits: 3/10 minutes
- IP limits: 10/1 hour
- Retry-after headers are accurate
- 429 responses are informative

### Lockout Mechanism

- Max 5 failed attempts
- 15-minute lockout window
- 423 response with unlock ETA
- Counters reset appropriately

### API Documentation

- Every endpoint documented
- Examples provided
- Status codes explained
- Authentication clearly shown

### Docker Reliability

- Single command starts all services
- Dependencies wait for each other
- Data persists appropriately
- Logs are accessible

This roadmap prioritizes building a solid foundation first, then adding features incrementally while maintaining testability and documentation throughout. Each phase builds on the previous, allowing for verification of core requirements before moving to advanced features.
