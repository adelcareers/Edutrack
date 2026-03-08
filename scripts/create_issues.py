#!/usr/bin/env python3
"""
Script to create all GitHub Issues for EduTrack product backlog.
Reads from AGENT_DELIVERY_PLAN.md and creates issues via GitHub CLI.
Run: python scripts/create_issues.py
"""
import subprocess
import json
import sys

REPO = "adelcareers/Edutrack"

# Milestone number map (will be populated from GitHub)
MILESTONE_MAP = {}  # title_prefix -> number


def gh_api(endpoint, method="GET", fields=None, jq=None):
    cmd = ["gh", "api", endpoint, "--method", method]
    if fields:
        for k, v in fields.items():
            cmd += ["-f", f"{k}={v}"]
    if jq:
        cmd += ["--jq", jq]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}", file=sys.stderr)
        return None
    return result.stdout.strip()


def create_milestone(title, desc):
    out = gh_api(
        f"repos/{REPO}/milestones",
        method="POST",
        fields={"title": title, "description": desc, "state": "open"},
        jq=".number"
    )
    if out:
        print(f"  Milestone #{out}: {title}")
        return int(out)
    return None


def get_milestones():
    result = subprocess.run(
        ["gh", "api", f"repos/{REPO}/milestones", "--paginate"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return {}
    data = json.loads(result.stdout)
    return {m["title"]: m["number"] for m in data}


def create_issue(title, body, labels, milestone_title):
    cmd = [
        "gh", "issue", "create",
        "--repo", REPO,
        "--title", title,
        "--body", body,
        "--milestone", milestone_title,
    ]
    for label in labels:
        cmd += ["--label", label]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR creating issue '{title}': {result.stderr}", file=sys.stderr)
        return None
    url = result.stdout.strip()
    print(f"  Created: {title} → {url}")
    return url


def main():
    # ── Step 1: Ensure milestones exist ──────────────────────────────────────
    print("\n[1/3] Checking milestones...")
    existing = get_milestones()

    needed = {
        "E1: Project Foundation": "All infrastructure exists. App deploys to Heroku. Admin panel live. Curriculum seeded. Sprint 0",
        "E2: Authentication & Roles": "Parent and student can register/login. Role-based access enforced. Sprint 1",
        "E3: Child Setup & Scheduling": "Parent adds child, selects subjects, triggers auto-scheduler. 180-day timetable generated. Sprint 1",
        "E4: Calendar View": "Student sees Syllabird-style weekly calendar with coloured subject cards. Sprint 2",
        "E5: Lesson Tracking": "Student marks lessons complete/skip, sets mastery scores, adds notes, reschedules. Sprint 2",
        "E6: Evidence & Files": "Student uploads evidence files to Cloudinary per lesson. Sprint 2",
        "E7: Reports & LA Sharing": "Parent generates PDF reports and shares via secure UUID token. Sprint 3",
        "E8: Payments (Stripe Stub)": "Pricing page and checkout stub with STRIPE_ENABLED feature flag. Sprint 3",
        "E9: Testing, Documentation & Final Deploy": "Automated tests, full README docs, final Heroku production deployment. Sprint 3",
    }

    global MILESTONE_MAP
    MILESTONE_MAP = dict(existing)

    for title, desc in needed.items():
        if title not in MILESTONE_MAP:
            num = create_milestone(title, desc)
            if num:
                MILESTONE_MAP[title] = num
        else:
            print(f"  Exists #{MILESTONE_MAP[title]}: {title}")

    print("\n[2/3] Milestone map:")
    for t, n in MILESTONE_MAP.items():
        print(f"  #{n}: {t}")

    # ── Step 2: Define all issues ─────────────────────────────────────────────
    print("\n[3/3] Creating issues...")

    issues = [
        # ── SPRINT 0 ── E1 Foundation ─────────────────────────────────────────
        {
            "title": "[S0.1] Django Project Skeleton",
            "milestone": "E1: Project Foundation",
            "labels": ["must-have", "backend", "devops", "sprint-0", "epic-E1"],
            "body": """## User Story
As a developer, I can initialise a clean Django project with all six apps registered, so that every subsequent story has a consistent, scalable codebase to build on.

## Acceptance Criteria
- [ ] `python manage.py check` returns 0 errors
- [ ] All 6 apps appear in INSTALLED_APPS
- [ ] `python manage.py runserver` starts without error
- [ ] .env is in .gitignore and NOT in the GitHub repository
- [ ] .env.example IS committed with all required keys but no values
- [ ] GitHub repository exists with at least 5 commits

## Tasks
- [ ] T1: `django-admin startproject edutrack .` → `commit: "chore: initialise Django project"`
- [ ] T2: `python manage.py startapp` for accounts, curriculum, scheduler, tracker, reports, payments → `commit: "chore: create six Django application modules"`
- [ ] T3: Register all 6 apps in INSTALLED_APPS; add crispy_forms, crispy_bootstrap5; set CRISPY_TEMPLATE_PACK → `commit: "chore: register all apps and crispy-forms in INSTALLED_APPS"`
- [ ] T4: Install python-decouple; refactor settings.py for SECRET_KEY, DEBUG, ALLOWED_HOSTS; create .env and .env.example → `commit: "chore: configure environment variable management with python-decouple"`
- [ ] T5: Create .gitignore (.env, *.pyc, __pycache__, db.sqlite3, media/, .DS_Store); create README.md skeleton → `commit: "chore: add gitignore and readme skeleton"`
- [ ] T6: git init; create GitHub repo; git push origin main

## Definition of Done
Project skeleton exists. Six apps registered. `manage.py check` passes. Secrets excluded from repo. GitHub repo live.

## LO Coverage
LO1.1, LO1.2, LO5.1, LO5.2, LO6.1, LO6.2, LO6.3""",
        },
        {
            "title": "[S0.2] Database Configuration",
            "milestone": "E1: Project Foundation",
            "labels": ["must-have", "backend", "devops", "sprint-0", "epic-E1"],
            "body": """## User Story
As a developer, I can connect the Django project to the Neon Postgres database, so that all models can be migrated and the app has a persistent data store.

## Acceptance Criteria
- [ ] `python manage.py migrate` completes with no errors
- [ ] DATABASE_URL is only in .env, never in settings.py
- [ ] whitenoise is configured in MIDDLEWARE
- [ ] requirements.txt is committed and contains all packages

## Tasks
- [ ] T1: `pip install django dj-database-url psycopg2-binary gunicorn whitenoise`; `pip freeze > requirements.txt` → `commit: "chore: add core Python dependencies to requirements.txt"`
- [ ] T2: Configure DATABASES in settings.py via dj_database_url; add DATABASE_URL to .env and .env.example → `commit: "chore: configure Neon Postgres database connection via dj-database-url"`
- [ ] T3: Add whitenoise to MIDDLEWARE; configure STATIC_URL, STATIC_ROOT, STATICFILES_STORAGE → `commit: "chore: configure whitenoise static file serving"`
- [ ] T4: `python manage.py migrate` → `commit: "chore: run initial Django migrations"`

## Definition of Done
Database connects. Migrations run. Whitenoise configured. No secrets in code.

## LO Coverage
LO1.2, LO5.2, LO6.1, LO6.3""",
        },
        {
            "title": "[S0.3] Cloudinary Storage Configuration",
            "milestone": "E1: Project Foundation",
            "labels": ["must-have", "backend", "devops", "sprint-0", "epic-E1"],
            "body": """## User Story
As a developer, I can configure Cloudinary as the media file storage backend, so that all file uploads in later sprints work in both development and production.

## Acceptance Criteria
- [ ] CLOUDINARY_URL is only in .env, never in settings.py
- [ ] DEFAULT_FILE_STORAGE points to cloudinary_storage
- [ ] `python manage.py check` still passes

## Tasks
- [ ] T1: `pip install cloudinary django-cloudinary-storage Pillow`; `pip freeze > requirements.txt` → `commit: "chore: add Cloudinary and Pillow to requirements.txt"`
- [ ] T2: Add 'cloudinary_storage', 'cloudinary' to INSTALLED_APPS (before staticfiles); set DEFAULT_FILE_STORAGE and CLOUDINARY_STORAGE; add CLOUDINARY_URL to .env and .env.example → `commit: "chore: configure Cloudinary as default media storage backend"`

## Definition of Done
Cloudinary configured. No credentials in code. `manage.py check` passes.

## LO Coverage
LO5.2, LO6.1""",
        },
        {
            "title": "[S0.4] All Seven Custom Models",
            "milestone": "E1: Project Foundation",
            "labels": ["must-have", "backend", "sprint-0", "epic-E1"],
            "body": """## User Story
As a developer, I can define all seven custom data models, so that the complete data architecture exists in code and can be migrated in one step.

## Acceptance Criteria
- [ ] All 7 models exist in their respective models.py files
- [ ] Every model has `__str__` returning a human-readable string
- [ ] Every model has a docstring explaining its purpose
- [ ] All ForeignKey relationships are correctly defined with on_delete
- [ ] `python manage.py makemigrations` produces 7 migration files (one per app)
- [ ] `python manage.py migrate` completes with no errors
- [ ] `python manage.py check` returns no errors

## Tasks
- [ ] T1: Write accounts/models.py — UserProfile (OneToOne→User, role choices, avatar CloudinaryField, subscription_active, created_at) → `commit: "feat(accounts): add UserProfile model with parent/student/admin role choices"`
- [ ] T2: Write curriculum/models.py — Lesson model (key_stage, subject_name, programme_slug, year, unit_slug, unit_title, lesson_number, lesson_title, lesson_url) → `commit: "feat(curriculum): add Lesson model for Oak National Academy curriculum data"`
- [ ] T3: Write scheduler/models.py — Child model (parent FK, first_name, birth_month/year, school_year, academic_year_start, student_user OneToOne, is_active) → `commit: "feat(scheduler): add Child model with parent relationship and student_user link"`
- [ ] T4: Write scheduler/models.py — EnrolledSubject model (child FK, subject_name, key_stage, lessons_per_week with validators, colour_hex, is_active) → `commit: "feat(scheduler): add EnrolledSubject model with lessons_per_week and colour"`
- [ ] T5: Write scheduler/models.py — ScheduledLesson model (child FK, lesson FK→curriculum.Lesson, enrolled_subject FK, scheduled_date db_index, order_on_day) → `commit: "feat(scheduler): add ScheduledLesson model for auto-generated timetable"`
- [ ] T6: Write tracker/models.py — LessonLog model (scheduled_lesson OneToOne, status choices, mastery choices, student_notes, completed_at, rescheduled_to, updated_by FK) → `commit: "feat(tracker): add LessonLog model with status and mastery score"`
- [ ] T7: Write tracker/models.py — EvidenceFile model (lesson_log FK, file CloudinaryField resource_type=auto, original_filename, uploaded_by FK, uploaded_at) → `commit: "feat(tracker): add EvidenceFile model with Cloudinary upload field"`
- [ ] T8: Write reports/models.py — Report model (child FK, created_by FK, created_at, report_type choices, date_from, date_to, share_token UUIDField, token_expires_at, pdf_file CloudinaryField) → `commit: "feat(reports): add Report model with UUID share_token for LA access"`
- [ ] T9: `python manage.py makemigrations` (all apps); `python manage.py migrate` → `commit: "chore: generate and apply initial migrations for all seven models"`

## Definition of Done
All 7 models migrated. `manage.py check` passes. Every model has `__str__` and docstring.

## LO Coverage
LO1.2, LO2.1, LO7.1""",
        },
        {
            "title": "[S0.5] Django Admin Configuration",
            "milestone": "E1: Project Foundation",
            "labels": ["must-have", "backend", "sprint-0", "epic-E1"],
            "body": """## User Story
As an admin, I can manage all application data through the Django admin panel, so that I can provide customer support and manage users without a separate interface.

## Acceptance Criteria
- [ ] All 7 models visible in Django admin at /admin/
- [ ] Superuser can log into admin panel
- [ ] Lesson admin has working search and filter
- [ ] LessonLog admin has status and mastery filters

## Tasks
- [ ] T1: accounts/admin.py — Extend UserAdmin with UserProfile inline; list_display=['user','role','subscription_active'], list_filter=['role'] → `commit: "feat(accounts): configure UserAdmin with role and subscription fields"`
- [ ] T2: curriculum/admin.py — Register Lesson with list_display, search_fields, list_filter → `commit: "feat(curriculum): configure Lesson admin with search and filter"`
- [ ] T3: scheduler/admin.py — Register Child, EnrolledSubject, ScheduledLesson with list_display and list_filter → `commit: "feat(scheduler): register scheduler models in Django admin"`
- [ ] T4: tracker/admin.py — Register LessonLog (list_filter=['status','mastery']), EvidenceFile → `commit: "feat(tracker): register tracker models in Django admin"`
- [ ] T5: reports/admin.py — Register Report with list_display=['child','report_type','created_at','share_token'], list_filter=['report_type'] → `commit: "feat(reports): register Report model in Django admin"`

## Definition of Done
All models in admin. List views show meaningful columns. Superuser can log in.

## LO Coverage
LO3.1""",
        },
        {
            "title": "[S0.6] Oak Curriculum Seed Command",
            "milestone": "E1: Project Foundation",
            "labels": ["must-have", "backend", "sprint-0", "epic-E1"],
            "body": """## User Story
As a developer, I can run a single management command to load the Oak National Academy CSV data into the database, so that the full 10,055-row curriculum is available for subject selection and scheduling.

## Acceptance Criteria
- [ ] `python manage.py seed_curriculum --file path/to/lessons.csv` runs without error
- [ ] Running twice produces no duplicate Lesson records (idempotent)
- [ ] Final output shows correct created/existing counts
- [ ] Command has a module-level docstring with usage example
- [ ] Lesson count in admin matches CSV row count (~10,055)

## Tasks
- [ ] T1: Create curriculum/management/__init__.py, commands/__init__.py; scaffold seed_curriculum.py with class Command and handle stub → `commit: "feat(curriculum): scaffold seed_curriculum management command"`
- [ ] T2: Implement CSV reading in handle(): accept --file argument; use csv.DictReader; Lesson.objects.get_or_create(lesson_url=row['lesson_url'], defaults={...}); count created vs existing → `commit: "feat(curriculum): implement CSV ingestion with idempotent get_or_create"`
- [ ] T3: Add progress output: print every 500 rows; print final summary "Seeded: X created, Y already existed. Total: Z lessons." → `commit: "feat(curriculum): add progress logging to seed_curriculum command"`

## Definition of Done
Seed runs clean. 10,055 records. Idempotent. Documented.

## LO Coverage
LO1.4""",
        },
        {
            "title": "[S0.7] Base Template and Static Files",
            "milestone": "E1: Project Foundation",
            "labels": ["must-have", "frontend", "sprint-0", "epic-E1"],
            "body": """## User Story
As a developer, I can create a base HTML template with Bootstrap 5 and a configured static file system, so that every page built in subsequent sprints inherits a consistent, accessible layout.

## Acceptance Criteria
- [ ] `python manage.py runserver` — homepage loads with Bootstrap styles
- [ ] Django messages block is present in base.html
- [ ] CSS variables are defined in custom.css
- [ ] W3C HTML validation passes on homepage
- [ ] Static files load (no 404s in browser console)

## Tasks
- [ ] T1: Configure TEMPLATES[0]['DIRS'] = [BASE_DIR / 'templates'] in settings.py; create templates/ directory → `commit: "chore: configure templates directory in settings"`
- [ ] T2: Create templates/base.html with Bootstrap 5.3 CDN, Bootstrap Icons CDN, navbar with brand "EduTrack", messages block, main content block, Bootstrap JS CDN, extra_css/extra_js blocks; all nav elements keyboard-navigable → `commit: "feat(templates): add base.html with Bootstrap 5 and Django messages support"`
- [ ] T3: Create static/css/custom.css with CSS variable palette (--primary, --secondary, --success, --warning, --danger, --dark, --light-bg, --border); configure STATICFILES_DIRS in settings.py; add {% load static %} and link to base.html → `commit: "style: add custom CSS with colour system variables"`
- [ ] T4: Create homepage view in edutrack/views.py; create templates/home.html extending base.html; add URL path('', views.home, name='home') → `commit: "feat(edutrack): add homepage placeholder view and template"`

## Definition of Done
Homepage renders. Bootstrap loads. Messages block present. W3C valid.

## LO Coverage
LO1.1""",
        },
        {
            "title": "[S0.8] First Heroku Deployment",
            "milestone": "E1: Project Foundation",
            "labels": ["must-have", "devops", "sprint-0", "epic-E1"],
            "body": """## User Story
As a developer, I can deploy the application skeleton to Heroku, so that we have a live URL from Day 3 and all subsequent work deploys to a real environment.

## Acceptance Criteria
- [ ] App accessible at Heroku URL with no 500 error
- [ ] /admin/ panel loads and superuser can log in
- [ ] All 7 models visible in admin
- [ ] curriculum.Lesson count is ~10,055
- [ ] DEBUG=False in Heroku config vars
- [ ] .env file is NOT in GitHub repository
- [ ] .env.example IS in GitHub repository

## Tasks
- [ ] T1: Create Procfile (`web: gunicorn edutrack.wsgi --log-file -`); create runtime.txt (`python-3.11.9`) → `commit: "chore: add Procfile and runtime.txt for Heroku deployment"`
- [ ] T2: Configure production security in settings.py: ALLOWED_HOSTS includes '.herokuapp.com', SECURE_BROWSER_XSS_FILTER=True, X_FRAME_OPTIONS='DENY', DEBUG=False in prod → `commit: "chore: configure production security settings for Heroku"`
- [ ] T3: `heroku create [app-name]`; set all Config Vars (DJANGO_SECRET_KEY, DJANGO_DEBUG=False, ALLOWED_HOSTS, DATABASE_URL, CLOUDINARY_URL, STRIPE keys, STRIPE_ENABLED=False); `git push heroku main` → `commit: "chore: initial Heroku deployment"`
- [ ] T4: `heroku run python manage.py migrate`; `heroku run python manage.py seed_curriculum --file [path]`; `heroku run python manage.py createsuperuser`
- [ ] T5: Smoke test live URL (homepage, /admin/, all 7 models, Lesson count ~10,055, DEBUG=False, .env not in GitHub) → `commit: "chore: verify Sprint 0 deployment — empty shell live on Heroku"`

## Definition of Done
Live on Heroku. Admin works. Curriculum seeded. DEBUG=False. No secrets in repo.

## LO Coverage
LO5.2, LO6.1, LO6.2, LO6.3""",
        },

        # ── SPRINT 1 ── E2 Auth & Roles ──────────────────────────────────────
        {
            "title": "[S1.1] Parent Registration",
            "milestone": "E2: Authentication & Roles",
            "labels": ["must-have", "backend", "frontend", "sprint-1", "epic-E2"],
            "body": """## User Story
As a parent, I can register an account with my email and password, so that I can access the platform and begin managing my child's home education.

## Acceptance Criteria
- [ ] POST with valid data creates User + UserProfile(role='parent')
- [ ] POST with duplicate email shows "Email already exists" error
- [ ] POST with mismatched passwords shows validation error
- [ ] After success: user is logged in, redirected, success message visible
- [ ] W3C HTML validation passes

## Tasks
- [ ] T1: `pip install django-crispy-forms crispy-bootstrap5`; confirm in INSTALLED_APPS; set CRISPY_TEMPLATE_PACK = 'bootstrap5' → `commit: "chore: add django-crispy-forms with bootstrap5 pack"`
- [ ] T2: accounts/forms.py — Create CustomUserCreationForm(UserCreationForm) with email (required, unique validation), first_name, last_name fields; override save() to set username=email → `commit: "feat(accounts): add CustomUserCreationForm with email as primary field"`
- [ ] T3: accounts/views.py — register_view(): GET renders form; POST validates → saves User → creates UserProfile(role='parent') → login → redirect with success message → `commit: "feat(accounts): add parent registration view with automatic UserProfile creation"`
- [ ] T4: accounts/urls.py + include in edutrack/urls.py at path('accounts/', ...) → `commit: "feat(accounts): wire registration URL"`
- [ ] T5: templates/accounts/register.html — extends base.html, {{ form|crispy }}, submit button, link to login; semantic HTML with aria attributes → `commit: "feat(templates): add registration page template"`

## Definition of Done
Registration creates parent UserProfile. Validation works. Redirects with message. W3C valid.

## LO Coverage
LO3.1, LO2.4""",
        },
        {
            "title": "[S1.2] Login, Logout & Login State",
            "milestone": "E2: Authentication & Roles",
            "labels": ["must-have", "backend", "frontend", "sprint-1", "epic-E2"],
            "body": """## User Story
As a user, I can log in and out of the application, so that I can access my role-appropriate pages and my login state is always visible.

## Acceptance Criteria
- [ ] Login with valid credentials redirects to role-appropriate page
- [ ] Login with wrong password shows error message
- [ ] Navbar shows first name + role badge when logged in
- [ ] Navbar shows Login/Register when logged out
- [ ] Logout clears session and redirects to homepage
- [ ] Unauthenticated request to protected URL redirects to /accounts/login/?next=...

## Tasks
- [ ] T1: Configure auth settings in settings.py: LOGIN_URL, LOGIN_REDIRECT_URL, LOGOUT_REDIRECT_URL → `commit: "feat(accounts): configure login/logout redirect URLs"`
- [ ] T2: accounts/views.py — login_view (wraps Django LoginView); logout_view (POST only, redirect to home with message); add to accounts/urls.py → `commit: "feat(accounts): add login and logout views"`
- [ ] T3: templates/accounts/login.html — extends base, crispy form, link to register → `commit: "feat(templates): add login page template"`
- [ ] T4: Update templates/base.html navbar with {% if user.is_authenticated %} block showing first_name + role badge (Bootstrap badge) and logout POST form; else Login/Register links → `commit: "feat(templates): reflect login state in navbar with name and role badge"`

## Definition of Done
Login/logout works. Navbar reflects state. Redirect on protected URL.

## LO Coverage
LO3.1, LO3.2""",
        },
        {
            "title": "[S1.3] Role-Based Access Decorator",
            "milestone": "E2: Authentication & Roles",
            "labels": ["must-have", "backend", "sprint-1", "epic-E2"],
            "body": """## User Story
As a developer, I can apply a single decorator to any view to restrict it by user role, so that role enforcement is consistent, centralised, and one line of code.

## Acceptance Criteria
- [ ] @role_required('parent') on a view: student is redirected with error message
- [ ] @role_required('student') on a view: parent is redirected with error message
- [ ] Unauthenticated user hitting any decorated view → /accounts/login/?next=...
- [ ] Decorator has a docstring with usage example
- [ ] functools.wraps used (preserves view function name)

## Tasks
- [ ] T1: accounts/decorators.py — create role_required(role) decorator factory; unauthenticated → redirect to login with next param; wrong role → redirect with error message; correct role → call view normally; use functools.wraps → `commit: "feat(accounts): add role_required decorator for role-based view protection"`
- [ ] T2: Apply @role_required('parent') to a test view to verify it works; manually test student hitting parent URL is redirected → `commit: "test(accounts): verify role_required decorator redirects incorrect roles"`

## Definition of Done
Decorator exists, documented. Parent→student blocked. Student→parent blocked. Unauth→login.

## LO Coverage
LO1.4, LO3.3""",
        },
        {
            "title": "[S1.4] Parent Creates Student Login",
            "milestone": "E2: Authentication & Roles",
            "labels": ["must-have", "backend", "frontend", "sprint-1", "epic-E2"],
            "body": """## User Story
As a parent, I can create login credentials for my child, so that my child can log in and see their calendar without needing an email address.

## Acceptance Criteria
- [ ] POST creates User(username=...) + UserProfile(role='student')
- [ ] Child.student_user is set to new User
- [ ] Duplicate username shows validation error
- [ ] Parent accessing another parent's child → 403
- [ ] Student can log in with created credentials
- [ ] View is inaccessible to student role

## Tasks
- [ ] T1: accounts/forms.py — StudentCreationForm with username, password1, password2 fields and unique username validation → `commit: "feat(accounts): add StudentCreationForm for parent-created student credentials"`
- [ ] T2: scheduler/views.py — create_student_login_view: @login_required @role_required('parent'); GET renders form; POST creates User + UserProfile(role='student') + links to child.student_user; verifies child.parent == request.user (403 if not) → `commit: "feat(scheduler): add view for parent to create student login credentials"`
- [ ] T3: templates/scheduler/create_student_login.html — form + credential display + success message → `commit: "feat(templates): add student credential creation page"`
- [ ] T4: Add URL: /children/<int:child_id>/create-login/ → `commit: "feat(scheduler): wire student login creation URL"`

## Definition of Done
Student login created and linked to Child. Ownership check. Student can log in.

## LO Coverage
LO3.1, LO3.3""",
        },

        # ── SPRINT 1 ── E3 Scheduling ─────────────────────────────────────────
        {
            "title": "[S1.5] Add Child Profile",
            "milestone": "E3: Child Setup & Scheduling",
            "labels": ["must-have", "backend", "frontend", "sprint-1", "epic-E3"],
            "body": """## User Story
As a parent, I can add my child's profile to my account, so that the system knows which school year my child is in and can present the right curriculum.

## Acceptance Criteria
- [ ] POST with valid data creates Child linked to request.user
- [ ] After save: redirect to subject selection for that child
- [ ] school_year dropdown populated from curriculum data (not hardcoded)
- [ ] Missing required fields show validation errors
- [ ] View inaccessible to student role

## Tasks
- [ ] T1: scheduler/forms.py — ChildForm(ModelForm) with first_name, birth_month, birth_year, school_year (ChoiceField from DB), academic_year_start; populate school_year from Lesson.objects.values_list('year', flat=True).distinct() → `commit: "feat(scheduler): add ChildForm with school year choices from curriculum data"`
- [ ] T2: scheduler/views.py — add_child_view: @login_required @role_required('parent'); GET renders form; POST saves child with parent=request.user, redirects to subject_selection → `commit: "feat(scheduler): add child profile creation view"`
- [ ] T3: templates/scheduler/add_child.html — crispy form, extends base → `commit: "feat(templates): add child profile creation page"`
- [ ] T4: Add URL path('children/add/', ...); add /children/ list view → `commit: "feat(scheduler): wire add child and child list URLs"`

## Definition of Done
Child created linked to parent. Redirects to subject selection. Validation works.

## LO Coverage
LO1.1, LO2.2, LO2.4""",
        },
        {
            "title": "[S1.6] Subject Selection Page",
            "milestone": "E3: Child Setup & Scheduling",
            "labels": ["must-have", "backend", "frontend", "sprint-1", "epic-E3"],
            "body": """## User Story
As a parent, I can select which Oak National Academy subjects my child will study and set a weekly lesson pace for each, so that the scheduling engine has everything it needs to generate the full timetable.

## Acceptance Criteria
- [ ] Subjects grouped by key_stage in accordion
- [ ] Spinner disabled until checkbox ticked
- [ ] Submitting with 0 subjects selected shows validation error
- [ ] EnrolledSubjects created with correct colour_hex from palette
- [ ] Each subject colour is distinct (palette cycles)
- [ ] View inaccessible to student role and other parents' children

## Tasks
- [ ] T1: scheduler/views.py — subject_selection_view: @login_required @role_required('parent'); verify child belongs to request.user; GET returns subjects grouped by key_stage with total lesson counts → `commit: "feat(scheduler): add subject selection view with grouped curriculum data"`
- [ ] T2: POST handler: parse checkboxes + spinners; create EnrolledSubject records with colour from SUBJECT_COLOUR_PALETTE; redirect to generate schedule → `commit: "feat(scheduler): implement EnrolledSubject creation with automatic colour assignment"`
- [ ] T3: templates/scheduler/subject_selection.html — Bootstrap accordion grouped by key_stage; each row: checkbox + subject name + "(N lessons)" badge + number spinner; spinner disabled by default → `commit: "feat(templates): add subject selection page with accordion groups and pace spinners"`
- [ ] T4: Vanilla JS to enable/disable spinner when checkbox is ticked/unticked → `commit: "style: add JS checkbox-to-spinner link on subject selection page"`
- [ ] T5: Add URL path('children/<int:child_id>/subjects/', ...) → `commit: "feat(scheduler): wire subject selection URL"`

## Definition of Done
EnrolledSubjects created with colour. Spinner UX works. Min 1 subject enforced.

## LO Coverage
LO1.1, LO2.2, LO2.3, LO2.4""",
        },
        {
            "title": "[S1.7] Schedule Generation Service",
            "milestone": "E3: Child Setup & Scheduling",
            "labels": ["must-have", "backend", "sprint-1", "epic-E3"],
            "body": """## User Story
As a developer, I can call a standalone service function to generate a 180-day lesson schedule, so that the algorithm is independently testable and separate from the web layer.

## Acceptance Criteria
- [ ] Function exists in scheduler/services.py with full docstring
- [ ] No lesson falls on Saturday or Sunday
- [ ] No subject exceeds its lessons_per_week in any calendar week
- [ ] Function returns integer count of records created
- [ ] bulk_create used with batch_size=500
- [ ] Running on fixture data completes without error

## Tasks
- [ ] T1: Create scheduler/services.py — add module docstring + generate_schedule(child, enrolled_subjects) function skeleton with parameters, return type annotation, full docstring → `commit: "feat(scheduler): add generate_schedule service function with full docstring"`
- [ ] T2: Implement Step 1 — build 180-day school day list (weekdays only from academic_year_start) → `commit: "feat(scheduler): implement 180-day weekday list generation"`
- [ ] T3: Implement Step 2 — build per-subject lesson queues from curriculum (ordered by unit_slug, lesson_number) → `commit: "feat(scheduler): implement per-subject lesson queue builder"`
- [ ] T4: Implement Step 3 — round-robin distribution with weekly pace limits (reset week_counts on new ISO week number) → `commit: "feat(scheduler): implement round-robin lesson distribution with weekly limits"`
- [ ] T5: Implement Step 4 — ScheduledLesson.objects.bulk_create(to_create, batch_size=500); return len(to_create) → `commit: "feat(scheduler): implement bulk_create for ScheduledLesson records"`

## Definition of Done
Algorithm implemented, documented. Runs clean. Uses bulk_create. Returns count.

## LO Coverage
LO1.4, LO2.2, LO2.3, LO7.1""",
        },
        {
            "title": "[S1.8] Schedule Generation Web Layer",
            "milestone": "E3: Child Setup & Scheduling",
            "labels": ["must-have", "backend", "frontend", "sprint-1", "epic-E3"],
            "body": """## User Story
As a parent, I can click "Generate Schedule" to have all lessons automatically distributed across the school year, so that my child immediately has a complete day-by-day timetable.

## Acceptance Criteria
- [ ] GET shows summary of what will be scheduled
- [ ] POST generates schedule and shows correct count in message
- [ ] Running POST twice (regenerate) deletes old schedule cleanly
- [ ] Parent redirected to dashboard after generation
- [ ] View inaccessible to student role

## Tasks
- [ ] T1: scheduler/views.py — generate_schedule_view: @login_required @role_required('parent'); GET renders confirmation page with summary; POST deletes existing ScheduledLessons → calls generate_schedule() → success message → redirect to dashboard → `commit: "feat(scheduler): add schedule generation view calling services.generate_schedule"`
- [ ] T2: templates/scheduler/generate_schedule.html — summary table + confirm button → `commit: "feat(templates): add schedule generation confirmation page"`
- [ ] T3: Add URL path('children/<int:child_id>/schedule/generate/', ...) → `commit: "feat(scheduler): wire schedule generation URL"`

## Definition of Done
Schedule generates. Count shown in message. Idempotent. Role protected.

## LO Coverage
LO2.2, LO2.3""",
        },
        {
            "title": "[S1.9] Parent Dashboard",
            "milestone": "E3: Child Setup & Scheduling",
            "labels": ["should-have", "backend", "frontend", "sprint-1", "epic-E3"],
            "body": """## User Story
As a parent, I can see a dashboard with a summary of my child's learning progress, so that I always have a quick overview without needing to drill into the calendar.

## Acceptance Criteria
- [ ] Dashboard shows stats per child (total scheduled, completed this week, overall % complete)
- [ ] Empty state shows Add Child prompt when no children exist
- [ ] Root URL / redirects parent here, student to /calendar/
- [ ] W3C valid, responsive

## Tasks
- [ ] T1: scheduler/views.py — parent_dashboard_view: @login_required @role_required('parent'); query all children for request.user; per child: total lessons, completed this week (Mon–Sun), overall % complete; empty state with CTA → `commit: "feat(scheduler): add parent dashboard view with progress summary"`
- [ ] T2: Update edutrack/urls.py root URL: root_redirect(request) redirects based on role → `commit: "feat(edutrack): add role-based root URL redirect"`
- [ ] T3: templates/scheduler/parent_dashboard.html — Bootstrap cards per child + CTA button → `commit: "feat(templates): add parent dashboard with child summary cards"`

## Definition of Done
Dashboard renders with correct stats. Empty state works. Role redirect from /.

## LO Coverage
LO1.1, LO3.3""",
        },
        {
            "title": "[S1.10] Sprint 1 Deployment",
            "milestone": "E3: Child Setup & Scheduling",
            "labels": ["must-have", "devops", "sprint-1", "epic-E3"],
            "body": """## User Story
As a developer, I can deploy Sprint 1 to Heroku and verify all auth and scheduling flows work in production.

## Acceptance Criteria (Smoke Test)
- [ ] Parent registration → child add → subject select → generate schedule (end-to-end)
- [ ] Student login with parent-created credentials works
- [ ] Role access control: student blocked from /children/, parent blocked from /calendar/
- [ ] Success messages visible at each step
- [ ] No 500 errors

## Tasks
- [ ] T1: `git push heroku main`; `heroku run python manage.py migrate`; smoke test all Sprint 1 flows on live URL → `commit: "chore: verify Sprint 1 deployment — auth and scheduling live on Heroku"`

## Definition of Done
All Sprint 1 features work on Heroku. No errors. Role checks enforced.

## LO Coverage
LO5.2, LO6.1""",
        },

        # ── SPRINT 2 ── E4 Calendar ───────────────────────────────────────────
        {
            "title": "[S2.1] Weekly Calendar View Structure",
            "milestone": "E4: Calendar View",
            "labels": ["must-have", "backend", "frontend", "sprint-2", "epic-E4"],
            "body": """## User Story
As a student, I can see a weekly calendar showing all my scheduled lessons organised into Monday to Friday columns, so that I always know exactly what I am supposed to study each day.

## Acceptance Criteria
- [ ] Calendar shows 5 columns Mon–Fri with correct dates
- [ ] Lessons appear in correct day column
- [ ] Empty day shows "No lessons scheduled" message
- [ ] View inaccessible to parent role directly
- [ ] W3C valid

## Tasks
- [ ] T1: tracker/views.py — calendar_view: @login_required @role_required('student'); parse year/week from URL params (default: current ISO week); query ScheduledLessons for student's child; build context {monday: [lessons], ...} + week_dates; include lesson_log and colour_hex per lesson → `commit: "feat(tracker): add weekly calendar view with day-keyed lesson context"`
- [ ] T2: templates/tracker/calendar.html — 5-column CSS Grid (Mon–Fri); day column header with name + date; empty state per column; lesson card placeholder with title + subject label → `commit: "feat(templates): add weekly calendar template with 5-column CSS grid layout"`
- [ ] T3: tracker/urls.py: path('calendar/', ...) + path('calendar/<int:year>/<int:week>/', ...); include in edutrack/urls.py → `commit: "feat(tracker): wire calendar URLs with week navigation parameters"`

## Definition of Done
Calendar renders for current week. Lessons in correct columns. Empty state shown.

## LO Coverage
LO1.1""",
        },
        {
            "title": "[S2.2] Calendar Week Navigation",
            "milestone": "E4: Calendar View",
            "labels": ["must-have", "backend", "frontend", "sprint-2", "epic-E4"],
            "body": """## User Story
As a student, I can navigate to previous and next weeks, so that I can review past lessons and see upcoming lessons without leaving the calendar.

## Acceptance Criteria
- [ ] ← navigates to previous week with correct dates
- [ ] → navigates to next week with correct dates
- [ ] "Today" always returns to current ISO week
- [ ] Week date range displayed in header updates correctly

## Tasks
- [ ] T1: tracker/views.py — compute prev_week and next_week ISO year/week tuples; add prev_url, next_url, today_url, week_display to context → `commit: "feat(tracker): add week navigation logic to calendar view"`
- [ ] T2: templates/tracker/calendar.html — add ← prev link, → next link, "Today" button to calendar header → `commit: "feat(templates): add week navigation controls to calendar header"`

## Definition of Done
Navigation works. Today button works. URL reflects active week.

## LO Coverage
LO1.1""",
        },
        {
            "title": "[S2.3] Subject Colour Cards",
            "milestone": "E4: Calendar View",
            "labels": ["must-have", "frontend", "sprint-2", "epic-E4"],
            "body": """## User Story
As a student, I can see each lesson card styled with its subject's colour, so that I can instantly identify subjects and the calendar is visually clear.

## Acceptance Criteria
- [ ] Same subject always uses same colour across all cards
- [ ] Card header band shows subject colour
- [ ] Complete badge visible on completed lessons
- [ ] Mastery dot visible on lessons with mastery set
- [ ] Text contrast is readable on all subject colours

## Tasks
- [ ] T1: templates/tracker/calendar.html — update lesson card markup with style="--subject-colour: {{ enrolled_subject.colour_hex }}"; card-header with subject name; card-footer with status badges and mastery dots → `commit: "feat(templates): apply subject colour system to calendar lesson cards"`
- [ ] T2: static/css/custom.css — add .lesson-card (border-left: 4px solid var(--subject-colour)), .card-header (background subject colour), .mastery-dot styles (green/amber/red) → `commit: "style: add lesson card CSS with coloured header band and mastery dot"`

## Definition of Done
Colour system applied. Status badges visible. Contrast readable.

## LO Coverage
LO1.1""",
        },

        # ── SPRINT 2 ── E5 Lesson Tracking ───────────────────────────────────
        {
            "title": "[S2.4] Lesson Detail Modal",
            "milestone": "E5: Lesson Tracking",
            "labels": ["must-have", "backend", "frontend", "sprint-2", "epic-E5"],
            "body": """## User Story
As a student, I can click a lesson card to see lesson details in a modal panel, so that I can interact with a lesson without leaving the calendar.

## Acceptance Criteria
- [ ] Clicking card opens modal with correct lesson data
- [ ] Oak lesson URL opens in new tab (target="_blank" rel="noopener")
- [ ] Modal has aria-modal="true" and aria-labelledby
- [ ] Modal closes on X click and backdrop click
- [ ] Student cannot open modal for another child's lessons

## Tasks
- [ ] T1: tracker/views.py — lesson_detail_view: @login_required @role_required('student'); verify ownership; return JSON {id, lesson_title, unit_title, subject_name, scheduled_date, lesson_url, colour_hex, status, mastery, student_notes, evidence_count} → `commit: "feat(tracker): add lesson detail JSON endpoint for modal population"`
- [ ] T2: Add URL path('lessons/<int:scheduled_id>/detail/', ..., name='lesson_detail') → `commit: "feat(tracker): wire lesson detail JSON URL"`
- [ ] T3: templates/tracker/calendar.html — add Bootstrap Modal markup with aria-modal="true", aria-labelledby="modal-title"; sections: header, body (details + Oak URL link), action buttons placeholder → `commit: "feat(templates): add lesson modal structure with ARIA attributes"`
- [ ] T4: static/js/calendar.js — card click handler: fetch JSON from detail endpoint; populate modal fields; bootstrap.Modal().show() → `commit: "style: add calendar.js with card click handler and modal population via fetch"`

## Definition of Done
Modal opens with correct data. ARIA present. Oak URL works. Ownership enforced.

## LO Coverage
LO2.2""",
        },
        {
            "title": "[S2.5] Mark Lesson Complete or Skip",
            "milestone": "E5: Lesson Tracking",
            "labels": ["must-have", "backend", "frontend", "sprint-2", "epic-E5"],
            "body": """## User Story
As a student, I can mark a lesson as complete or skip it from the modal, so that my progress is recorded and my parent can see what I have done.

## Acceptance Criteria
- [ ] Clicking Complete: LessonLog.status='complete', completed_at set
- [ ] Clicking Skip: LessonLog.status='skipped'
- [ ] Card badge updates immediately (no page reload)
- [ ] CSRF token included in all AJAX POST requests
- [ ] Ownership enforced (student cannot update another's lesson)

## Tasks
- [ ] T1: tracker/views.py — update_lesson_status_view: @login_required @role_required('student'); POST {status: 'complete'|'skipped'}; LessonLog.get_or_create; update status; if complete set completed_at=timezone.now(); verify ownership; return JSON {success, status, message} → `commit: "feat(tracker): add lesson status update view for complete and skip actions"`
- [ ] T2: Add URL path('lessons/<int:scheduled_id>/update/', ...) → `commit: "feat(tracker): wire lesson status update URL"`
- [ ] T3: static/js/calendar.js — Complete/Skip button click handlers: fetch POST with {status} + CSRF token; on success update card badge in DOM without page reload; getCookie('csrftoken') helper → `commit: "style: add AJAX lesson status update with immediate card badge refresh in calendar.js"`

## Definition of Done
Status saves. Card updates without reload. CSRF present. Ownership checked.

## LO Coverage
LO2.2, LO2.3""",
        },
        {
            "title": "[S2.6] Mastery Score",
            "milestone": "E5: Lesson Tracking",
            "labels": ["must-have", "backend", "frontend", "sprint-2", "epic-E5"],
            "body": """## User Story
As a student, I can set a mastery score of Green, Amber, or Red for any lesson, so that I and my parent can track how confident I feel about each topic.

## Acceptance Criteria
- [ ] Selecting mastery saves to LessonLog.mastery
- [ ] Only selected button shows active state (others deselected)
- [ ] Card mastery dot updates immediately
- [ ] Mastery can be changed after initial selection

## Tasks
- [ ] T1: tracker/views.py — update_mastery_view: POST {mastery: 'green'|'amber'|'red'}; get_or_create LessonLog; update mastery; return JSON success → `commit: "feat(tracker): add mastery score update view"`
- [ ] T2: Add URL path('lessons/<int:scheduled_id>/mastery/', ...) → `commit: "feat(tracker): wire mastery update URL"`
- [ ] T3: templates/tracker/calendar.html modal — add mastery button group with three buttons (data-mastery="green"|"amber"|"red"); active state class on currently selected → `commit: "feat(templates): add mastery score button group to lesson modal"`
- [ ] T4: static/js/calendar.js — mastery button click → fetch POST → update active button state + card mastery dot → `commit: "style: add AJAX mastery update with active button state and card dot refresh"`

## Definition of Done
Mastery saves and shows on card. Active state updates. Changeable.

## LO Coverage
LO2.2""",
        },
        {
            "title": "[S2.7] Student Notes",
            "milestone": "E5: Lesson Tracking",
            "labels": ["must-have", "backend", "frontend", "sprint-2", "epic-E5"],
            "body": """## User Story
As a student, I can add a personal note to any lesson, so that my portfolio reflects my genuine engagement with the content.

## Acceptance Criteria
- [ ] Notes save to LessonLog.student_notes
- [ ] Notes re-appear when modal reopened for same lesson
- [ ] Character counter updates in real-time
- [ ] Empty notes are valid (field is optional)
- [ ] Notes > 1000 chars are rejected

## Tasks
- [ ] T1: tracker/views.py — save_notes_view: POST {notes: string (max 1000 chars)}; get_or_create LessonLog; update student_notes; return JSON success → `commit: "feat(tracker): add student notes save view"`
- [ ] T2: Update lesson_detail_view to include student_notes in JSON response → `commit: "feat(tracker): include saved notes in lesson detail endpoint response"`
- [ ] T3: templates/tracker/calendar.html modal — add notes textarea with maxlength="1000" + character counter span → `commit: "feat(templates): add notes textarea with character counter to lesson modal"`
- [ ] T4: static/js/calendar.js — populate textarea on modal open; save on button click; update char counter in real-time → `commit: "style: add notes population and save handler in calendar.js"`

## Definition of Done
Notes save and reload. Char limit enforced. Empty is valid.

## LO Coverage
LO2.2, LO2.4""",
        },
        {
            "title": "[S2.8] Reschedule a Lesson",
            "milestone": "E5: Lesson Tracking",
            "labels": ["should-have", "backend", "frontend", "sprint-2", "epic-E5"],
            "body": """## User Story
As a student, I can move a lesson to a different date, so that my calendar stays accurate when I cannot complete something on the scheduled day.

## Acceptance Criteria
- [ ] Rescheduling to a past date is rejected
- [ ] Lesson disappears from original day after reschedule
- [ ] Lesson appears on new date when navigating to that week
- [ ] LessonLog.rescheduled_to is set for audit trail

## Tasks
- [ ] T1: tracker/views.py — reschedule_lesson_view: POST {new_date: 'YYYY-MM-DD'}; validate new_date > today; update ScheduledLesson.scheduled_date; get_or_create LessonLog; set rescheduled_to; return JSON success → `commit: "feat(tracker): add lesson reschedule view with future-date validation"`
- [ ] T2: Add URL path('lessons/<int:scheduled_id>/reschedule/', ...) → `commit: "feat(tracker): wire lesson reschedule URL"`
- [ ] T3: templates/tracker/calendar.html modal — add reschedule section: date input (min=tomorrow) + button → `commit: "feat(templates): add reschedule section with date picker to lesson modal"`
- [ ] T4: static/js/calendar.js — reschedule submit → fetch POST → close modal → reload calendar → `commit: "style: add reschedule AJAX handler in calendar.js"`

## Definition of Done
Reschedule moves lesson. Past dates rejected. Audit field set.

## LO Coverage
LO2.2, LO2.3""",
        },
        {
            "title": "[S2.9] Parent Read-Only Calendar",
            "milestone": "E5: Lesson Tracking",
            "labels": ["must-have", "backend", "frontend", "sprint-2", "epic-E5"],
            "body": """## User Story
As a parent, I can view my child's weekly calendar in read-only mode, so that I can monitor progress without logging in as the student.

## Acceptance Criteria
- [ ] Parent sees child's calendar with correct lessons
- [ ] Complete/Skip/Mastery buttons are NOT visible to parent
- [ ] Accessing another parent's child returns 403
- [ ] Week navigation works in parent view

## Tasks
- [ ] T1: tracker/views.py — parent_calendar_view: @login_required @role_required('parent'); accept child_id; verify child.parent == request.user (403 if not); same query as student calendar; pass is_readonly=True to context → `commit: "feat(tracker): add parent read-only calendar view with ownership check"`
- [ ] T2: templates/tracker/calendar.html — {% if not is_readonly %} conditional around action buttons → `commit: "feat(templates): conditionally hide action buttons in read-only calendar mode"`
- [ ] T3: Add URLs: /parent/calendar/<int:child_id>/ and /parent/calendar/<int:child_id>/<int:year>/<int:week>/ → `commit: "feat(tracker): wire parent calendar URLs"`

## Definition of Done
Parent sees read-only calendar. No action buttons. Ownership enforced.

## LO Coverage
LO1.1, LO3.3""",
        },

        # ── SPRINT 2 ── E6 Evidence ───────────────────────────────────────────
        {
            "title": "[S2.10] Evidence File Upload",
            "milestone": "E6: Evidence & Files",
            "labels": ["must-have", "backend", "frontend", "sprint-2", "epic-E6"],
            "body": """## User Story
As a student, I can upload a file as evidence of my work for any lesson, so that my portfolio contains tangible proof of my learning.

## Acceptance Criteria
- [ ] Valid file types upload to Cloudinary; EvidenceFile record created
- [ ] Invalid file types (e.g. .exe) show validation error; not uploaded
- [ ] Evidence count badge increments after upload
- [ ] LessonLog is created if it does not yet exist

## Tasks
- [ ] T1: tracker/views.py — upload_evidence_view: @login_required @role_required('student'); POST multipart; validate file type (image/*, application/pdf, .doc, .docx); get_or_create LessonLog; EvidenceFile.objects.create(...); return JSON {success, file_id, filename, uploaded_at} → `commit: "feat(tracker): add evidence file upload view with Cloudinary storage"`
- [ ] T2: Add URL path('lessons/<int:scheduled_id>/upload/', ...) → `commit: "feat(tracker): wire evidence upload URL"`
- [ ] T3: templates/tracker/calendar.html modal — add evidence section: file input (accept="image/*,.pdf,.doc,.docx"), upload button, evidence count badge → `commit: "feat(templates): add evidence upload form to lesson modal"`
- [ ] T4: Update lesson_detail_view to include evidence_count; static/js/calendar.js — handle file upload via FormData + fetch; update count badge → `commit: "style: add evidence file upload handler in calendar.js"`

## Definition of Done
Files upload to Cloudinary. Record created. Invalid types rejected. Count updates.

## LO Coverage
LO2.2""",
        },
        {
            "title": "[S2.11] Evidence File List and Delete",
            "milestone": "E6: Evidence & Files",
            "labels": ["must-have", "backend", "frontend", "sprint-2", "epic-E6"],
            "body": """## User Story
As a student, I can see all uploaded evidence files for a lesson and delete incorrect ones, so that I maintain an accurate portfolio.

## Acceptance Criteria
- [ ] File list shows filename + upload date for each file
- [ ] Delete button with confirm prompt removes file from DB and Cloudinary
- [ ] Deleting another student's file returns 403
- [ ] File list updates after deletion without page reload

## Tasks
- [ ] T1: tracker/views.py — delete_evidence_view: @login_required @role_required('student'); verify EvidenceFile.uploaded_by == request.user (403 if not); delete from Cloudinary (cloudinary.uploader.destroy(public_id)); delete EvidenceFile record; return JSON success → `commit: "feat(tracker): add evidence file deletion view with Cloudinary cleanup"`
- [ ] T2: Add URL path('evidence/<int:file_id>/delete/', ...) → `commit: "feat(tracker): wire evidence delete URL"`
- [ ] T3: Update lesson_detail_view to include file list [{id, original_filename, uploaded_at}] → `commit: "feat(tracker): include evidence file list in lesson detail endpoint"`
- [ ] T4: static/js/calendar.js — render file list in modal; delete handler with confirm() dialog; update list after deletion without page reload → `commit: "style: add evidence file list rendering and delete confirmation handler"`

## Definition of Done
File list renders. Delete removes from DB and Cloudinary. Ownership enforced.

## LO Coverage
LO2.2""",
        },
        {
            "title": "[S2.12] Sprint 2 Deployment",
            "milestone": "E6: Evidence & Files",
            "labels": ["must-have", "devops", "sprint-2", "epic-E6"],
            "body": """## User Story
As a developer, I can deploy Sprint 2 to Heroku and verify the full student lesson interaction loop works in production.

## Acceptance Criteria (Smoke Test)
- [ ] Student marks lesson complete; card updates immediately
- [ ] Mastery scores save and show on card
- [ ] Notes save and reload on modal reopen
- [ ] File uploads to Cloudinary in production
- [ ] Parent calendar shows correct read-only view
- [ ] No 500 errors

## Tasks
- [ ] T1: `git push heroku main`; `heroku run python manage.py migrate`; smoke test full student interaction loop + parent read-only; verify Cloudinary uploads work in production → `commit: "chore: verify Sprint 2 deployment — full lesson interaction loop live"`

## Definition of Done
All Sprint 2 features work on Heroku. Cloudinary uploads confirmed.

## LO Coverage
LO5.2, LO6.1""",
        },

        # ── SPRINT 3 ── E7 Reports ────────────────────────────────────────────
        {
            "title": "[S3.1] Report Creation Form",
            "milestone": "E7: Reports & LA Sharing",
            "labels": ["must-have", "backend", "frontend", "sprint-3", "epic-E7"],
            "body": """## User Story
As a parent, I can fill in a form to specify a report's date range and type, so that I can generate exactly the evidence the LA requires.

## Acceptance Criteria
- [ ] date_from > date_to shows validation error
- [ ] Preview shows number of completed lessons in the selected date range
- [ ] Both report types (Summary / Full Portfolio) available in dropdown
- [ ] View inaccessible to student role

## Tasks
- [ ] T1: reports/forms.py — ReportForm(ModelForm) with date_from, date_to, report_type fields; clean() validates date_from < date_to → `commit: "feat(reports): add ReportForm with date range validation"`
- [ ] T2: reports/views.py — create_report_view: @login_required @role_required('parent'); GET renders form + preview (count completed lessons in date range); POST validates form → proceeds to PDF generation → `commit: "feat(reports): add report creation view with completed lesson preview"`
- [ ] T3: templates/reports/create_report.html — crispy form + preview stats → `commit: "feat(templates): add report creation page with parameter form and preview"`
- [ ] T4: Add URL path('reports/create/<int:child_id>/', ...) → `commit: "feat(reports): wire report creation URL"`

## Definition of Done
Form renders. Date validation works. Preview accurate. Role protected.

## LO Coverage
LO2.2, LO3.1""",
        },
        {
            "title": "[S3.2] PDF Report Generation",
            "milestone": "E7: Reports & LA Sharing",
            "labels": ["must-have", "backend", "sprint-3", "epic-E7"],
            "body": """## User Story
As a parent, I can generate and download a PDF evidence report, so that I can submit a professional document to the Local Authority.

## Acceptance Criteria
- [ ] PDF downloads on click
- [ ] PDF contains child name, date range, and subject breakdown
- [ ] Full Portfolio type includes per-lesson notes and mastery
- [ ] Summary type contains totals only
- [ ] PDF file stored in Cloudinary; Report.pdf_file is set

## Tasks
- [ ] T1: `pip install xhtml2pdf`; `pip freeze > requirements.txt` → `commit: "chore: add xhtml2pdf to requirements.txt"`
- [ ] T2: reports/services.py — generate_pdf(report): query LessonLogs in date range; render pdf_template.html; use xhtml2pdf pisa.CreatePDF() to generate PDF bytes; upload to Cloudinary; save URL to report.pdf_file; return download URL → `commit: "feat(reports): implement PDF generation service with xhtml2pdf"`
- [ ] T3: templates/reports/pdf_template.html — clean print-ready HTML: child name, school year, date range, report type; per-subject table; if portfolio type: per-lesson rows with notes and mastery colour → `commit: "feat(reports): add HTML-to-PDF report template"`
- [ ] T4: reports/views.py — update create_report_view POST: create Report record → call generate_pdf() → redirect to report_detail with success message → `commit: "feat(reports): wire PDF generation to report creation POST"`
- [ ] T5: reports/views.py — report_detail_view: show metadata + PDF download link + share token URL; Add URL path('reports/<int:report_id>/', ...) → `commit: "feat(reports): add report detail view with download link and share URL"`

## Definition of Done
PDF downloads with correct content. Both types render. Stored in Cloudinary.

## LO Coverage
LO2.2, LO2.4, LO3.3""",
        },
        {
            "title": "[S3.3] LA Share Token Link",
            "milestone": "E7: Reports & LA Sharing",
            "labels": ["must-have", "backend", "frontend", "sprint-3", "epic-E7"],
            "body": """## User Story
As a parent, I can share a report via a secure link that does not require the LA to log in, so that the LA officer can view the evidence instantly.

## Acceptance Criteria
- [ ] Valid token URL renders report without any login
- [ ] Invalid UUID returns 404
- [ ] Expired token returns 403 with clear message
- [ ] Shared report page has no navbar login/logout links
- [ ] Share URL is copyable from parent's report detail page

## Tasks
- [ ] T1: reports/views.py — token_report_view: no @login_required; lookup Report by share_token (UUID param); 404 if not found; check token_expires_at expiry → 403 if expired; render standalone shared_report.html → `commit: "feat(reports): add LA share token view with UUID validation and expiry check"`
- [ ] T2: Add URL path('reports/share/<uuid:token>/', ...) → `commit: "feat(reports): wire LA share token URL"`
- [ ] T3: templates/reports/shared_report.html — standalone template (no extends base.html); EduTrack branding only; no navbar login/logout; report content + footer → `commit: "feat(templates): add standalone LA report template for token access"`
- [ ] T4: templates/reports/report_detail.html — add share section: display full token URL + copy-to-clipboard button (JS) → `commit: "feat(templates): add share URL display and copy button to report detail page"`

## Definition of Done
Token URL works without login. Invalid = 404. Expired = 403. Copy button works.

## LO Coverage
LO2.4, LO3.1, LO3.3""",
        },

        # ── SPRINT 3 ── E8 Payments ───────────────────────────────────────────
        {
            "title": "[S3.4] Stripe Pricing Page",
            "milestone": "E8: Payments (Stripe Stub)",
            "labels": ["must-have", "backend", "frontend", "sprint-3", "epic-E8"],
            "body": """## User Story
As a parent, I can view available subscription plans and understand what each tier includes, so that I can make an informed decision about upgrading.

## Acceptance Criteria
- [ ] Accessible without login
- [ ] Free and Pro tier features clearly listed
- [ ] "Choose Pro" links to checkout
- [ ] Responsive, W3C valid

## Tasks
- [ ] T1: payments/views.py — pricing_page_view (no auth required); context: {plans: [{name, price, features, cta}]} → `commit: "feat(payments): add Stripe pricing page view"`
- [ ] T2: templates/payments/pricing.html — two-column card layout (Free + Pro); feature comparison lists; "Choose Pro" CTA button → `commit: "feat(templates): add pricing page with Free and Pro tier comparison cards"`
- [ ] T3: Add URL path('payments/plans/', ...); add pricing link to base.html navbar → `commit: "feat(payments): wire pricing page URL and add to navbar"`

## Definition of Done
Pricing page renders. Two tiers visible. Links to checkout.

## LO Coverage
LO1.1, LO2.2""",
        },
        {
            "title": "[S3.5] Stripe Checkout Stub",
            "milestone": "E8: Payments (Stripe Stub)",
            "labels": ["should-have", "backend", "frontend", "sprint-3", "epic-E8"],
            "body": """## User Story
As a parent, I can click "Choose Pro" and be taken through a subscription upgrade journey, so that the payment flow is complete even if live charging is not yet active.

## Acceptance Criteria
- [ ] STRIPE_ENABLED=False shows test mode banner (not a broken form)
- [ ] Success page exists and renders
- [ ] Subscription gate on report creation redirects unsubscribed parents to pricing
- [ ] subscription_active field settable in Django admin (for testing)

## Tasks
- [ ] T1: Add STRIPE_ENABLED = config('STRIPE_ENABLED', cast=bool, default=False) and STRIPE_PUBLISHABLE_KEY to settings.py → `commit: "chore: add Stripe configuration to settings with STRIPE_ENABLED feature flag"`
- [ ] T2: payments/views.py — checkout_view: @login_required @role_required('parent'); context with stripe_enabled and stripe_key → `commit: "feat(payments): add Stripe checkout view with STRIPE_ENABLED feature flag"`
- [ ] T3: templates/payments/checkout.html — if STRIPE_ENABLED: Stripe.js form; if not: "⚠️ Test Mode — Payments are currently disabled" banner + plan summary → `commit: "feat(templates): add checkout template with feature flag test mode banner"`
- [ ] T4: payments/views.py — success_view + templates/payments/success.html; add subscription_gate to reports/views.py (redirect to pricing if not subscription_active) → `commit: "feat(payments): add success page and subscription gate on report generation"`
- [ ] T5: Add URLs: /payments/checkout/, /payments/success/ → `commit: "feat(payments): wire checkout and success URLs"`

## Definition of Done
Pricing→checkout flow complete. Feature flag works. Gate on reports.

## LO Coverage
LO1.1, LO2.2""",
        },

        # ── SPRINT 3 ── E9 Testing & Final Deploy ─────────────────────────────
        {
            "title": "[S3.6] Automated Python Tests",
            "milestone": "E9: Testing, Documentation & Final Deploy",
            "labels": ["must-have", "testing", "sprint-3", "epic-E9"],
            "body": """## User Story
As a developer, I can run an automated test suite covering all critical paths, so that the codebase is verified and testing competency is demonstrated.

## Acceptance Criteria
- [ ] `python manage.py test` exits with 0 failures
- [ ] Minimum 11 test cases across 4 test files
- [ ] Each test file has a module-level docstring
- [ ] All tests use setUp / TestCase fixtures (no live database dependency)
- [ ] Tests cover: scheduler, tracker, accounts, reports

## Tasks
- [ ] T1: scheduler/tests.py — 3 tests: test_schedule_generates_correct_count, test_no_weekend_lessons, test_respects_weekly_pace → `commit: "test(scheduler): add automated tests for schedule generation algorithm"`
- [ ] T2: tracker/tests.py — 2 tests: test_lesson_log_created_on_complete, test_status_update (pending → skipped) → `commit: "test(tracker): add automated tests for lesson log status updates"`
- [ ] T3: accounts/tests.py — 3 tests: test_registration_creates_parent_role, test_student_blocked_from_parent_views, test_parent_blocked_from_student_views → `commit: "test(accounts): add role-based access control tests"`
- [ ] T4: reports/tests.py — 3 tests: test_valid_token_renders_report, test_invalid_token_returns_404, test_expired_token_returns_403 → `commit: "test(reports): add share token validation tests"`
- [ ] T5: Run `python manage.py test` — confirm all 11 tests pass → `commit: "test: final test run — all 11 tests passing"`

## Definition of Done
All 11+ tests pass. No live DB dependency. Each file docstring present.

## LO Coverage
LO4.1, LO4.2""",
        },
        {
            "title": "[S3.7] README: UX and Design Documentation",
            "milestone": "E9: Testing, Documentation & Final Deploy",
            "labels": ["must-have", "docs", "sprint-3", "epic-E9"],
            "body": """## User Story
As a developer, I can document the UX design process and design rationale in the README, so that the assessor can follow the thinking from concept to implementation. *(Satisfies LO1.5)*

## Acceptance Criteria
- [ ] UX Design section present in README
- [ ] Wireframes for: calendar, lesson modal, dashboard, subject selection
- [ ] Colour system table documents all CSS variables
- [ ] Syllabird reference and adaptation explained
- [ ] Accessibility decisions documented

## Tasks
- [ ] T1: README.md — add UX Design section with: Project Purpose, Target User (Personas), Design Rationale (Syllabird inspiration), Wireframes (text descriptions or images), Colour System table, Accessibility Decisions → `commit: "docs(readme): add UX design section with wireframes and design rationale"`

## Definition of Done
README UX section complete. Wireframes described. Colour system documented.

## LO Coverage
LO1.5""",
        },
        {
            "title": "[S3.8] README: Testing Documentation",
            "milestone": "E9: Testing, Documentation & Final Deploy",
            "labels": ["must-have", "docs", "testing", "sprint-3", "epic-E9"],
            "body": """## User Story
As a developer, I can document all test procedures and results in the README, so that the assessor can see what was tested and the outcomes. *(Satisfies LO4.3)*

## Acceptance Criteria
- [ ] Automated test table lists all 11+ tests with pass/fail
- [ ] Manual JS test table has 8+ scenarios with actual results filled in
- [ ] Test run command documented
- [ ] All results are accurate (not placeholder text)

## Tasks
- [ ] T1: README.md — add Testing section with: Automated Tests table (test name | what it tests | result), Manual JavaScript Tests table (scenario | steps | expected | actual | pass/fail), How to Run Tests command → `commit: "docs(readme): add testing section with automated and manual test results"`

## Definition of Done
Testing section complete. All results filled in. Commands documented.

## LO Coverage
LO4.3""",
        },
        {
            "title": "[S3.9] README: Deployment and AI Reflection",
            "milestone": "E9: Testing, Documentation & Final Deploy",
            "labels": ["must-have", "docs", "devops", "sprint-3", "epic-E9"],
            "body": """## User Story
As a developer, I can document the deployment process and AI tool usage in the README, so that the assessor can reproduce the deployment and see how AI contributed. *(Satisfies LO6.2, LO8.1–LO8.5)*

## Acceptance Criteria
- [ ] Deployment section has complete step-by-step Heroku instructions
- [ ] AI section addresses all 5 LO8 criteria with specific examples
- [ ] Features section lists all implemented features
- [ ] README reads as professional documentation throughout

## Tasks
- [ ] T1: README.md — add Deployment section: Prerequisites, Environment Variables (reference .env.example), step-by-step Heroku deployment, How to run locally → `commit: "docs(readme): add complete deployment documentation with step-by-step guide"`
- [ ] T2: README.md — add AI Tools section covering all 5 LO8 criteria (Code Generation, Debugging, Optimisation, Unit Tests, Workflow Reflection) with specific examples → `commit: "docs(readme): add AI tools reflection covering all LO8 criteria"`
- [ ] T3: README.md — add Features section + final review of all sections for completeness and professional tone → `commit: "docs(readme): finalise README — all sections complete"`

## Definition of Done
README complete. Deployment reproducible from instructions. All LO8 points covered.

## LO Coverage
LO6.2, LO8.1, LO8.2, LO8.3, LO8.4, LO8.5""",
        },
        {
            "title": "[S3.10] Final Production Deployment",
            "milestone": "E9: Testing, Documentation & Final Deploy",
            "labels": ["must-have", "devops", "testing", "sprint-3", "epic-E9"],
            "body": """## User Story
As a developer, I can perform the final production deployment with all security settings verified, so that the submitted application is fully functional, secure, and meets all deployment requirements. *(Satisfies LO6.1, LO6.3)*

## Acceptance Criteria (Final Smoke Test)
- [ ] Register parent → add child → select subjects → generate schedule (end-to-end)
- [ ] Create student login → student logs in → views calendar
- [ ] Student marks lesson complete with mastery + notes + file upload
- [ ] Parent views read-only calendar
- [ ] Parent generates PDF report → downloads → copies LA share URL
- [ ] LA share URL opens in incognito without login
- [ ] Stripe pricing page renders; checkout shows test mode banner
- [ ] `python manage.py test` passes locally
- [ ] DEBUG=False, no secrets in repo

## Tasks
- [ ] T1: Run `python manage.py test` — all tests must pass before final push → `commit: "test: final test run — all tests passing before production deployment"`
- [ ] T2: Security audit checklist: .env not in git log; DEBUG=False in Heroku; ALLOWED_HOSTS not '*'; no hardcoded credentials (`git grep -r "password|secret|api_key" -- '*.py'`) → `commit: "chore: final security audit before production deployment"`
- [ ] T3: `git push heroku main`; `heroku run python manage.py migrate`; `heroku open`; full end-to-end smoke test → `commit: "chore: final production deployment — EduTrack v1.0"`

## Definition of Done
Full end-to-end smoke test passes on Heroku. All security checks pass. Tests pass.

## LO Coverage
LO6.1, LO6.3""",
        },
    ]

    # ── Step 3: Create all issues ─────────────────────────────────────────────
    for issue in issues:
        milestone_title = issue["milestone"]
        if milestone_title not in MILESTONE_MAP:
            print(f"  WARNING: no milestone for '{milestone_title}', skipping '{issue['title']}'")
            continue
        create_issue(
            title=issue["title"],
            body=issue["body"],
            labels=issue["labels"],
            milestone_title=milestone_title,
        )

    print("\nDone! All issues created.")


if __name__ == "__main__":
    main()
