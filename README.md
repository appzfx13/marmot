🦫 Marmot Enterprise Platform
A high-performance, dual-architecture web platform built with Django, HTMX, PostgreSQL, and Redis.
Marmot is engineered with a Domain-Driven Service Layer that bridges dynamic hypermedia UIs (HTMX) and RESTful APIs, designed from the ground up for seamless AI Agent Automation.
📋 Table of Contents
Overview & Architecture
Project Directory Structure
Prerequisites
Quick Start Guide
Core Architecture: Service Layer Pattern
1. Shared Service Layer (services.py)
2. HTMX Web View (views.py)
3. Pure REST API View (views.py)
AI Automation & Extension Setup
Database & Services Management
Testing & Quality Assurance
🏛️ Overview & Architecture
Marmot eliminates the trade-offs between traditional server-rendered templates and modern single-page applications (SPAs):
HTMX Frontend: Delivers dynamic, SPA-like interactions directly via server-rendered HTML partials with zero JavaScript framework overhead.
Decoupled REST API: Exposes clean JSON endpoints for mobile apps, external clients, or webhooks.
Shared Service Layer: Business logic, authorization, and data queries live in reusable service modules—ensuring full DRY (Don't Repeat Yourself) compliance across both HTMX and API views.
AI-Ready Engine: Pre-configured directory structure (apps/ai_agents/) and async worker infrastructure (Redis/Celery) ready for tool integration with AI agents (LangChain, AutoGen, LlamaIndex).

Plaintext


                      ┌─────────────────────────────────┐
                      │      Shared Service Layer       │
                      │   (apps/<app_name>/services.py) │
                      └────────────────▲────────────────┘
                                       │
            ┌──────────────────────────┴──────────────────────────┐
            │                                                     │
 ┌──────────┴──────────┐                               ┌──────────┴──────────┐
 │  apps/users/views   │                               │   apps/api/views    │
 │   (HTMX / HTML)     │                               │     (JSON REST)     │
 └─────────────────────┘                               └─────────────────────┘


📁 Project Directory Structure

Plaintext


marmot/
├── apps/
│   ├── api/             # Dedicated REST / JSON API endpoints
│   ├── users/           # Authentication, User Profiles, and HTMX UI
│   │   ├── mixins.py    # HTMX Partial Rendering helpers
│   │   ├── services.py  # Business logic & query abstraction layer
│   │   └── views.py     # Template & HTMX views
│   ├── trade_core/      # Core Trading Engine logic
│   ├── trade_config/    # Trading Rules, Fees, & Configuration
│   ├── market/          # Market Data Ingestion & Streamers
│   ├── notifications/   # Alerts, Emails, & Notification Dispatcher
│   ├── masters/         # Reference Data & System Master Records
│   ├── common/          # Reusable Utilities, Mixins, & Base Models
│   └── ai_agents/       # Dedicated module for AI Workflows & Tools
├── templates/
│   └── marmot/          # Django Templates & HTMX Partial Blocks
│       └── partials/    # HTMX partial fragments
├── .env                 # Environment configuration variables
├── docker-compose.yml   # Docker Orchestration Configuration
├── Dockerfile           # Python/Django App Container Definition
├── entrypoint.sh        # Startup script for web & migration execution
└── manage.py            # Django administrative CLI


⚙️ Prerequisites
Before getting started, ensure you have the following tools installed locally:
Docker Desktop (v20.10 or higher)
Docker Compose (v2.0 or higher)
Python 3.11+ (Optional: only required for local virtualenv setup outside Docker)
🚀 Quick Start Guide
Follow these steps to get your entire stack running in a matter of minutes.
Step 1: Clone and Configure Environment

Bash


# Clone the repository
git clone https://github.com/your-org/marmot.git
cd marmot

# Create your local environment file (if not present)
cp .env.example .env


Step 2: Build and Run Docker Stack
Spin up all containers (Django App, PostgreSQL, Redis, Adminer) in detached mode:

Bash


docker-compose up -d --build


Step 3: Verify Running Services
Check the container status to confirm all services are healthy:

Bash


docker ps


Container Name
Image
Port Mapping
Service Description
django_app
marmot-web
0.0.0.0:8000 -> 8000
Django Web Server & API Gateway
postgres_db
postgres:16-alpine
0.0.0.0:5432 -> 5432
PostgreSQL Primary Database
redis_broker
redis:7-alpine
0.0.0.0:6379 -> 6379
Redis Caching & Async Task Broker
adminer_ui
adminer:latest
0.0.0.0:8080 -> 8080
Web-Based Database Management UI

Step 4: Run Initial Database Migrations & Create Superuser

Bash


# Apply pending migrations
docker exec -it django_app python manage.py migrate

# Create an administrator user
docker exec -it django_app python manage.py createsuperuser


Step 5: Access the Application
Web Application / HTMX: Open http://localhost:8000
Database Adminer UI: Open http://localhost:8080
Django Admin Panel: Open http://localhost:8000/admin/
💻 Core Architecture: Service Layer Pattern
To keep views thin and business logic scalable, follow this 3-tier standard across all modules.
1. Shared Service Layer (apps/users/services.py)
Extract database queries, permissions logic, and calculations into service functions.

Python


# apps/users/services.py
from typing import Optional
from django.contrib.auth import get_user_model
from .models import MemberRoleChoices

User = get_user_model()
ALLOWED_ROLES = [MemberRoleChoices.ADMIN, MemberRoleChoices.TRADERS]

def is_marmot_authorized(user) -> bool:
    """Centralized authorization check for user roles."""
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    allowed_values = [
        role.value if hasattr(role, 'value') else role for role in ALLOWED_ROLES
    ]

    # Role checks against direct attributes, database profiles, and Django groups
    if getattr(user, 'role', None) in allowed_values:
        return True

    marmot_user = User.objects.filter(username__iexact=user.username).first()
    if marmot_user and getattr(marmot_user, 'role', None) in allowed_values:
        return True

    return user.groups.filter(name__in=allowed_values).exists()

def get_marmot_profile(username: str) -> Optional[User]:
    """Retrieves user profile safely."""
    return User.objects.filter(username__iexact=username).first()


2. HTMX Web View (apps/users/views.py)
Uses partial template rendering for HTMX requests and falls back to full layouts for page reloads.

Python


# apps/users/views.py
from django.views.generic import TemplateView
from .mixins import HTMXPartialMixin, MarmotRoleRequiredMixin
from .services import get_marmot_profile

class UserDashboardView(HTMXPartialMixin, MarmotRoleRequiredMixin, TemplateView):
    template_name = 'marmot/dashboard.html'
    partial_template_name = 'marmot/partials/dashboard_content.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['marmot_profile'] = get_marmot_profile(self.request.user.username)
        return context


3. Pure REST API View (apps/api/views.py)
Reuses the exact same service layer function to return clean JSON data to API clients.

Python


# apps/api/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from apps.users.services import is_marmot_authorized, get_marmot_profile

class APIDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not is_marmot_authorized(request.user):
            return Response({"error": "Unauthorized role"}, status=status.HTTP_403_FORBIDDEN)
        
        profile = get_marmot_profile(request.user.username)
        return Response({
            "status": "success",
            "data": {
                "username": profile.username if profile else request.user.username,
                "email": request.user.email,
                "role": getattr(profile, 'role', None),
            }
        })


🤖 AI Automation & Extension Setup
The repository is built to support AI Agents and autonomous workflows:
Tool Integration (apps/ai_agents/tools.py): Expose functions in services.py directly as structured function signatures for LLM tool calling (LangChain, LlamaIndex, OpenAI Assistant API).
Background Async Execution: Process long-running AI inference, vector embedding batching, or data pipeline jobs asynchronously using Redis as the message broker.
HTMX Streaming UI: Utilize Server-Sent Events (SSE) or WebSockets to stream LLM responses token-by-token directly into HTMX partials.
🗄️ Database & Services Management
Connecting to Adminer DB Management
Open http://localhost:8080 in your browser.
Set System to PostgreSQL.
Set Server to postgres_db.
Enter credentials configured in your .env file (Default: User: postgres, Password: postgres, DB: marmot_db).
Viewing Application Logs

Bash


# Stream logs for all containers
docker-compose logs -f

# Stream logs for the Django web app container only
docker logs -f django_app


🧪 Testing & Quality Assurance
Execute the test suite inside the running application container:

Bash


# Run all tests across the project
docker exec -it django_app python manage.py test

# Run tests for a specific module
docker exec -it django_app python manage.py test apps.users


