# EDUTRACK — AGENT EXECUTION DOCUMENT
> **Format:** Agile Delivery Plan · Machine-Optimised Markdown  
> **Version:** 1.0 · **Stack:** Django 5 · Bootstrap 5 · Neon Postgres · Cloudinary · Heroku  
> **Role of this document:** Feed to Claude at the start of every coding session. Agent parses state, identifies current story, executes tasks, commits, updates state.

---

## ⚠️ AGENT PRIME DIRECTIVES

```
DIRECTIVE 1 — READ BEFORE CODE
  Never write implementation code until you have read:
    (a) The current story's full AC block
    (b) The current story's task list
    (c) The current story's DoD
  If any of these are missing, halt and ask the human.

DIRECTIVE 2 — ONE TASK = ONE COMMIT
  Every task in a story maps to exactly one git commit.
  Commit message format is pre-specified per task.
  Never batch tasks. Never skip tasks.

DIRECTIVE 3 — VERIFY BEFORE PROCEEDING
  After each commit, confirm the change works before the next task.
  `python manage.py check` must pass after every backend change.
  W3C HTML validation must pass after every template change.

DIRECTIVE 4 — SECRETS NEVER IN CODE
  All sensitive values via python-decouple from .env.
  If you find yourself typing a URL, key, or password into code, STOP.

DIRECTIVE 5 — SCOPE LOCK
  Implement only what the current task specifies.
  Do not add features, refactor unrelated code, or anticipate future stories.
  Scope creep is a project risk. Stay in the task.

DIRECTIVE 6 — STATE UPDATE ON COMPLETION
  When a story is marked ✅ DONE, update the ## PROJECT STATE block below.
  The next session agent reads state first. Keep it accurate.
```

---

## PROJECT STATE
> **Agent: Update this block at the end of every session.**

```yaml
project_name: EduTrack
tagline: Home Education, Evidenced.
repo_url: 'https://github.com/adelcareers/Edutrack'
heroku_url: '[ADD HEROKU APP URL HERE]'
last_updated: '2026-03-08'
current_sprint: Sprint 0
current_story: S1.1
current_story_title: Auth — Registration & Login
current_story_status: NOT_STARTED
sprint_0_status: IN_PROGRESS
sprint_1_status: NOT_STARTED
sprint_2_status: NOT_STARTED
sprint_3_status: NOT_STARTED
stories_done: [S0.1, S0.2, S0.3, S0.4, S0.5, S0.6, S0.7]
stories_in_progress: []
stories_blocked: []
last_commit: 'd146929'
heroku_deployed: false
tests_passing: true
debug_false_in_prod: false
```

Note: You can run `python scripts/update_project_state.py --commit` to automatically set `last_updated` to today's date and commit the change.

---

## PART 1 — TECHNICAL FOUNDATION

### 1.1 Tech Stack

| Layer | Technology | Version | Notes |
|-------|-----------|---------|-------|
| Backend Framework | Django | ≥5.0 | Primary application framework |
| Language | Python | 3.11+ | Specified in runtime.txt |
| Database | PostgreSQL (Neon) | latest | Accessed via DATABASE_URL env var |
| ORM | Django ORM | built-in | No raw SQL. All queries via ORM. |
| Frontend | Bootstrap 5 | 5.3 CDN | No npm build step. CDN only. |
| Icons | Bootstrap Icons | 1.11 CDN | |
| JavaScript | Vanilla JS | ES2020+ | No framework. AJAX via fetch(). |
| File Storage | Cloudinary | latest | All user uploads. No local media in prod. |
| Payments | Stripe | latest | Feature-flagged. UI stub only for MVP. |
| PDF Generation | xhtml2pdf | latest | Pure Python. No system dependencies. |
| Forms | django-crispy-forms + crispy-bootstrap5 | latest | |
| WSGI Server | gunicorn | latest | Heroku production server |
| Static Files | whitenoise | latest | Serves static files from Heroku |
| Env Management | python-decouple | latest | Reads .env in dev, env vars in prod |
| Deployment | Heroku | - | Git-push deployment |
| Version Control | Git + GitHub | - | Conventional commits |
| Project Board | GitHub Projects | - | Kanban: Backlog→Analysis→Progress→Review→Done |

### 1.2 Environment Variables

```bash
# ── REQUIRED: All must be set in .env (dev) and Heroku Config Vars (prod) ──

# Django core
DJANGO_SECRET_KEY=your-long-random-secret-key-here
DJANGO_DEBUG=True                         # False in production — NEVER True in prod
ALLOWED_HOSTS=localhost,127.0.0.1         # .herokuapp.com in production

# Database
DATABASE_URL=postgresql://user:pass@host/dbname  # Neon Postgres connection string

# Cloudinary
CLOUDINARY_URL=cloudinary://api_key:api_secret@cloud_name

# Stripe (feature-flagged — payments disabled in MVP)
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_ENABLED=False                      # Keep False for MVP

# .env.example MUST be committed with all keys but NO values
```

### 1.3 System Architecture — Role-Based Access Control (RBAC)

```
ROLES:
  parent   → Full CRUD on own children, subjects, schedules, reports, subscription
  student  → Read calendar, mark lessons, set mastery, add notes, upload evidence
  admin    → Django admin panel, all user management, customer support
  la       → No login. UUID share token URL. Read-only report view.

RBAC IMPLEMENTATION:
  UserProfile.role (CharField: parent|student|admin)
  @role_required("parent") decorator → 302 redirect if wrong role
  @login_required → 302 to login if unauthenticated
  LA access → Report.share_token (UUID) validated in view, no session needed

ACCESS MATRIX:
  /                          → parent:dashboard  student:calendar  admin:admin
  /accounts/register/        → public
  /accounts/login/           → public
  /children/*                → parent only
  /calendar/*                → student only
  /parent/calendar/*         → parent only (read-only child view)
  /reports/*                 → parent only (except /reports/share/<token>/)
  /reports/share/<token>/    → la token (no auth)
  /payments/*                → parent only (except /payments/plans/ = public)
  /admin/                    → admin only
```

### 1.4 Django Application Structure

```
edutrack/                          ← Django project root
├── edutrack/                      ← Project package
│   ├── settings.py                ← python-decouple for all env vars
│   ├── urls.py                    ← Root URL configuration
│   ├── wsgi.py
│   └── asgi.py
│
├── accounts/                      ← E2: Auth, roles, UserProfile
│   ├── models.py                  ← UserProfile (role, avatar)
│   ├── views.py                   ← register, login, logout, profile
│   ├── forms.py                   ← CustomUserCreationForm, StudentCreationForm
│   ├── decorators.py              ← role_required(role)
│   ├── admin.py                   ← Extended UserAdmin
│   ├── urls.py
│   └── tests.py
│
├── curriculum/                    ← E1: Oak National Academy seed data (read-only)
│   ├── models.py                  ← Lesson (key_stage, subject, unit, lesson, url)
│   ├── admin.py
│   ├── management/
│   │   └── commands/
│   │       └── seed_curriculum.py ← loads CSV → Lesson records
│   └── tests.py
│
├── scheduler/                     ← E3: Children, subjects, auto-scheduler
│   ├── models.py                  ← Child, EnrolledSubject, ScheduledLesson
│   ├── views.py                   ← dashboard, add_child, subject_selection, generate
│   ├── forms.py                   ← ChildForm, SubjectSelectionForm
│   ├── services.py                ← generate_schedule() ← core algorithm
│   ├── admin.py
│   ├── urls.py
│   └── tests.py
│
├── tracker/                       ← E4/E5/E6: Calendar, lesson logging, evidence
│   ├── models.py                  ← LessonLog, EvidenceFile
│   ├── views.py                   ← calendar, lesson_detail, update_status, upload
│   ├── forms.py                   ← LessonLogForm, EvidenceUploadForm
│   ├── admin.py
│   ├── urls.py
│   └── tests.py
│
├── reports/                       ← E7: PDF reports, LA share tokens
│   ├── models.py                  ← Report (share_token, pdf_file)
│   ├── views.py                   ← create_report, report_detail, token_view
│   ├── forms.py                   ← ReportForm
│   ├── services.py                ← generate_pdf()
│   ├── templates/reports/
│   │   └── pdf_template.html      ← xhtml2pdf source template
│   ├── admin.py
│   ├── urls.py
│   └── tests.py
│
├── payments/                      ← E8: Stripe (UI stub, feature-flagged)
│   ├── views.py                   ← pricing_page, checkout, success
│   ├── urls.py
│   └── tests.py
│
├── templates/                     ← All HTML templates
│   ├── base.html                  ← Bootstrap 5, navbar, messages, content block
│   ├── accounts/
│   │   ├── register.html
│   │   ├── login.html
│   │   └── profile.html
│   ├── scheduler/
│   │   ├── parent_dashboard.html
│   │   ├── add_child.html
│   │   ├── subject_selection.html
│   │   ├── generate_schedule.html
│   │   └── create_student_login.html
│   ├── tracker/
│   │   └── calendar.html          ← includes lesson modal
│   ├── reports/
│   │   ├── create_report.html
│   │   ├── report_detail.html
│   │   └── shared_report.html     ← LA token view (no navbar auth)
│   └── payments/
│       ├── pricing.html
│       ├── checkout.html
│       └── success.html
│
├── static/
│   ├── css/
│   │   └── custom.css             ← CSS variables, card styles, calendar grid
│   └── js/
│       └── calendar.js            ← Card click, modal, AJAX, mastery, upload
│
├── docs/                          ← Project documentation
│   ├── wireframes/                ← Wireframe images or descriptions (LO1.5)
│   └── ai_reflections.md         ← AI tool usage log (LO8)
│
├── requirements.txt               ← All Python dependencies pinned
├── Procfile                       ← web: gunicorn edutrack.wsgi
├── runtime.txt                    ← python-3.11.x
├── .env.example                   ← All keys, no values
├── .gitignore                     ← .env, *.pyc, __pycache__, db.sqlite3, media/
└── README.md                      ← Full project documentation (LO1.5, LO4.3, LO6.2, LO8)
```

### 1.5 Data Models (All 7 Custom)

```python
# accounts/models.py
class UserProfile(models.Model):
    user         = models.OneToOneField(User, on_delete=CASCADE)
    role         = models.CharField(max_length=20, choices=[('parent','Parent'),('student','Student'),('admin','Admin')])
    avatar       = CloudinaryField('avatar', blank=True, null=True)
    subscription_active = models.BooleanField(default=False)
    created_at   = models.DateTimeField(auto_now_add=True)

# curriculum/models.py
class Lesson(models.Model):
    key_stage    = models.CharField(max_length=10, db_index=True)
    subject_name = models.CharField(max_length=100, db_index=True)
    programme_slug = models.CharField(max_length=200)
    year         = models.CharField(max_length=20, db_index=True)
    unit_slug    = models.CharField(max_length=200)
    unit_title   = models.CharField(max_length=300)
    lesson_number = models.IntegerField()
    lesson_title = models.CharField(max_length=300)
    lesson_url   = models.URLField(max_length=500)

# scheduler/models.py
class Child(models.Model):
    parent       = models.ForeignKey(User, on_delete=CASCADE, related_name='children')
    first_name   = models.CharField(max_length=100)
    birth_month  = models.IntegerField(choices=[(i,i) for i in range(1,13)])
    birth_year   = models.IntegerField()
    school_year  = models.CharField(max_length=20)
    academic_year_start = models.DateField()
    student_user = models.OneToOneField(User, null=True, blank=True, on_delete=SET_NULL, related_name='child_profile')
    is_active    = models.BooleanField(default=True)

class EnrolledSubject(models.Model):
    child        = models.ForeignKey(Child, on_delete=CASCADE, related_name='enrolled_subjects')
    subject_name = models.CharField(max_length=100)
    key_stage    = models.CharField(max_length=10)
    lessons_per_week = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    colour_hex   = models.CharField(max_length=7)
    is_active    = models.BooleanField(default=True)

class ScheduledLesson(models.Model):
    child        = models.ForeignKey(Child, on_delete=CASCADE)
    lesson       = models.ForeignKey('curriculum.Lesson', on_delete=CASCADE)
    enrolled_subject = models.ForeignKey(EnrolledSubject, on_delete=CASCADE)
    scheduled_date = models.DateField(db_index=True)
    order_on_day = models.IntegerField(default=0)

# tracker/models.py
class LessonLog(models.Model):
    STATUS_CHOICES = [('pending','Pending'),('complete','Complete'),('skipped','Skipped')]
    MASTERY_CHOICES = [('unset','Unset'),('green','Green'),('amber','Amber'),('red','Red')]
    scheduled_lesson = models.OneToOneField(ScheduledLesson, on_delete=CASCADE)
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    mastery      = models.CharField(max_length=10, choices=MASTERY_CHOICES, default='unset')
    student_notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    rescheduled_to = models.DateField(null=True, blank=True)
    updated_by   = models.ForeignKey(User, null=True, on_delete=SET_NULL)

class EvidenceFile(models.Model):
    lesson_log   = models.ForeignKey(LessonLog, on_delete=CASCADE, related_name='evidence_files')
    file         = CloudinaryField('evidence', resource_type='auto')
    original_filename = models.CharField(max_length=255)
    uploaded_by  = models.ForeignKey(User, null=True, on_delete=SET_NULL)
    uploaded_at  = models.DateTimeField(auto_now_add=True)

# reports/models.py
class Report(models.Model):
    TYPE_CHOICES = [('summary','Summary'),('portfolio','Full Portfolio')]
    child        = models.ForeignKey(Child, on_delete=CASCADE)
    created_by   = models.ForeignKey(User, null=True, on_delete=SET_NULL)
    created_at   = models.DateTimeField(auto_now_add=True)
    report_type  = models.CharField(max_length=20, choices=TYPE_CHOICES)
    date_from    = models.DateField()
    date_to      = models.DateField()
    share_token  = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    pdf_file     = CloudinaryField('reports', blank=True, null=True)
```

### 1.6 Core Algorithm — Scheduling Engine

```python
# scheduler/services.py
def generate_schedule(child, enrolled_subjects):
    """
    Distributes all Oak curriculum lessons across 180 school weekdays.

    Algorithm:
      1. Build list of 180 weekday dates from child.academic_year_start
      2. Build per-subject lesson queues ordered by unit_slug, lesson_number
      3. Round-robin distribute: for each day, assign lessons respecting
         each subject's weekly lessons_per_week limit
      4. bulk_create all ScheduledLesson records (batch_size=500)

    Returns: int — total ScheduledLesson records created
    """
    # STEP 1: Build school day list
    school_days = []
    current = child.academic_year_start
    while len(school_days) < 180:
        if current.weekday() < 5:  # Monday=0, Friday=4
            school_days.append(current)
        current += timedelta(days=1)

    # STEP 2: Build lesson queues per subject
    queues = {}
    for subject in enrolled_subjects:
        queues[subject.id] = list(
            Lesson.objects.filter(
                subject_name=subject.subject_name,
                year=child.school_year
            ).order_by('unit_slug', 'lesson_number')
        )

    # STEP 3: Distribute round-robin with weekly pace limits
    to_create = []
    week_counts = {s.id: 0 for s in enrolled_subjects}
    current_week = school_days[0].isocalendar()[1]

    for day in school_days:
        if day.isocalendar()[1] != current_week:
            week_counts = {s.id: 0 for s in enrolled_subjects}
            current_week = day.isocalendar()[1]
        order = 0
        for subject in enrolled_subjects:
            if (week_counts[subject.id] < subject.lessons_per_week
                    and queues[subject.id]):
                lesson = queues[subject.id].pop(0)
                to_create.append(ScheduledLesson(
                    child=child,
                    lesson=lesson,
                    enrolled_subject=subject,
                    scheduled_date=day,
                    order_on_day=order
                ))
                week_counts[subject.id] += 1
                order += 1

    # STEP 4: Bulk insert
    ScheduledLesson.objects.bulk_create(to_create, batch_size=500)
    return len(to_create)
```

### 1.7 requirements.txt

```
django>=5.0,<6.0
psycopg2-binary
dj-database-url
python-decouple
gunicorn
whitenoise
cloudinary
django-cloudinary-storage
Pillow
stripe
xhtml2pdf
django-crispy-forms
crispy-bootstrap5
```

### 1.8 Procfile & runtime.txt

```
# Procfile
web: gunicorn edutrack.wsgi --log-file -

# runtime.txt
python-3.11.9
```

---

## PART 2 — GLOBAL DEFINITIONS (APPLIES TO ALL STORIES)

### Definition of Ready (DoR)
A story is READY when all of the following are true:
- [ ] User story statement is present (As a / I can / so that)
- [ ] Acceptance criteria are written and unambiguous
- [ ] All tasks are broken into single-commit chunks
- [ ] Dependencies (prior stories) are DONE
- [ ] Agent understands what "done" looks like for this story

### Definition of Done (DoD)
A story is DONE when all of the following are true:
- [ ] All acceptance criteria pass (tested manually)
- [ ] Code follows PEP 8; all functions have docstrings
- [ ] No hardcoded secrets, URLs, or credentials in any file
- [ ] `python manage.py check` returns no errors
- [ ] Templates pass W3C HTML validation
- [ ] If a form: tested with invalid inputs (errors display correctly)
- [ ] If a view: access control tested (correct role can access, wrong role is blocked)
- [ ] Conventional commit message used for every task commit
- [ ] GitHub Projects issue moved to ✅ Done column
- [ ] PROJECT STATE block in this document updated

### Commit Convention
```
feat(app):      New feature or user-visible behaviour
fix(app):       Bug fix
test(app):      Adding or updating automated tests
docs:           README, docstrings, comments
style:          CSS/template changes, no logic
chore:          Config, deps, environment
refactor(app):  Restructure, no behaviour change

Examples:
  feat(accounts): add role-based registration with parent/student roles
  feat(scheduler): implement 180-day lesson distribution algorithm
  fix(tracker): mastery score not persisting on modal close
  test(accounts): add role access control test cases
  chore: configure Cloudinary storage backend
  docs(readme): add deployment section
```

---

## PART 3 — AGILE BACKLOG

> **Hierarchy:** Epic → Story → Tasks → AC → DoD → Metadata  
> **Priority:** P0 = must-have for sprint · P1 = important · P2 = could defer  
> **Points:** Fibonacci scale: 1, 2, 3, 5, 8  

---

## 🏗️ EPIC E1 — Project Foundation
**Milestone:** All infrastructure exists. App deploys to Heroku. Admin panel live. Curriculum seeded.  
**Sprint:** Sprint 0 (Days 1–3)  
**LO Coverage:** LO1.1, LO1.2, LO2.1, LO5.1, LO5.2, LO6.1, LO6.2, LO6.3, LO7.1

---

### STORY S0.1 — Django Project Skeleton
```yaml
id: S0.1
epic: E1
sprint: 0
priority: P0
points: 2
status: DONE
depends_on: []
```
**User Story:** As a developer, I can initialise a clean Django project with all six apps registered, so that every subsequent story has a consistent, scalable codebase to build on.

**Tasks:**
```
T1: django-admin startproject edutrack .
    commit: "chore: initialise Django project"

T2: python manage.py startapp accounts
    python manage.py startapp curriculum
    python manage.py startapp scheduler
    python manage.py startapp tracker
    python manage.py startapp reports
    python manage.py startapp payments
    commit: "chore: create six Django application modules"

T3: Register all 6 apps in INSTALLED_APPS
    Add 'django.contrib.messages', crispy_forms, crispy_bootstrap5
    Set CRISPY_TEMPLATE_PACK = 'bootstrap5'
    commit: "chore: register all apps and crispy-forms in INSTALLED_APPS"

T4: Install python-decouple; refactor settings.py
    SECRET_KEY = config('DJANGO_SECRET_KEY')
    DEBUG = config('DJANGO_DEBUG', cast=bool, default=False)
    ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv())
    Create .env with local values
    Create .env.example with all keys, no values
    commit: "chore: configure environment variable management with python-decouple"

T5: Create .gitignore (exclude: .env, *.pyc, __pycache__, db.sqlite3, media/, .DS_Store)
    Create README.md skeleton with project title and one-line description
    commit: "chore: add gitignore and readme skeleton"

T6: git init; create GitHub repo; git push origin main
    commit: (initial push — no commit message, this IS the first commit)
```

**Acceptance Criteria:**
- [ ] `python manage.py check` returns 0 errors
- [ ] All 6 apps appear in INSTALLED_APPS
- [ ] `python manage.py runserver` starts without error
- [ ] .env is in .gitignore and NOT in the GitHub repository
- [ ] .env.example IS committed with all required keys but no values
- [ ] GitHub repository exists with at least 5 commits

**Definition of Done:** Project skeleton exists. Six apps registered. `manage.py check` passes. Secrets excluded from repo. GitHub repo live.

---

### STORY S0.2 — Database Configuration
```yaml
id: S0.2
epic: E1
sprint: 0
priority: P0
points: 1
status: DONE
depends_on: [S0.1]
```
**User Story:** As a developer, I can connect the Django project to the Neon Postgres database, so that all models can be migrated and the app has a persistent data store.

**Tasks:**
```
T1: pip install django dj-database-url psycopg2-binary gunicorn whitenoise
    pip freeze > requirements.txt
    commit: "chore: add core Python dependencies to requirements.txt"

T2: Configure DATABASES in settings.py:
      import dj_database_url
      DATABASES = {'default': dj_database_url.config(default=config('DATABASE_URL'))}
    Add DATABASE_URL to .env and .env.example
    commit: "chore: configure Neon Postgres database connection via dj-database-url"

T3: Add whitenoise to MIDDLEWARE (after SecurityMiddleware)
    STATIC_URL = '/static/'
    STATIC_ROOT = BASE_DIR / 'staticfiles'
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
    commit: "chore: configure whitenoise static file serving"

T4: python manage.py migrate (creates Django system tables)
    commit: "chore: run initial Django migrations"
```

**Acceptance Criteria:**
- [ ] `python manage.py migrate` completes with no errors
- [ ] DATABASE_URL is only in .env, never in settings.py
- [ ] whitenoise is configured in MIDDLEWARE
- [ ] requirements.txt is committed and contains all packages

**Definition of Done:** Database connects. Migrations run. Whitenoise configured. No secrets in code.

---

### STORY S0.3 — Cloudinary Storage Configuration
```yaml
id: S0.3
epic: E1
sprint: 0
priority: P0
points: 1
status: DONE
depends_on: [S0.2]
```
**User Story:** As a developer, I can configure Cloudinary as the media file storage backend, so that all file uploads in later sprints work in both development and production.

**Tasks:**
```
T1: pip install cloudinary django-cloudinary-storage Pillow
    pip freeze > requirements.txt
    commit: "chore: add Cloudinary and Pillow to requirements.txt"

T2: Add to INSTALLED_APPS: 'cloudinary_storage', 'cloudinary'
    (cloudinary_storage must come BEFORE django.contrib.staticfiles)
    DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
    CLOUDINARY_STORAGE = {'CLOUDINARY_URL': config('CLOUDINARY_URL')}
    Add CLOUDINARY_URL to .env and .env.example
    commit: "chore: configure Cloudinary as default media storage backend"
```

**Acceptance Criteria:**
- [ ] CLOUDINARY_URL is only in .env, never in settings.py
- [ ] DEFAULT_FILE_STORAGE points to cloudinary_storage
- [ ] `python manage.py check` still passes

**Definition of Done:** Cloudinary configured. No credentials in code. check passes.

---

### STORY S0.4 — All Seven Custom Models
```yaml
id: S0.4
epic: E1
sprint: 0
priority: P0
points: 5
status: DONE
depends_on: [S0.3]
```
**User Story:** As a developer, I can define all seven custom data models, so that the complete data architecture exists in code and can be migrated in one step.

> **Reference:** See Section 1.5 of this document for full model definitions.

**Tasks:**
```
T1: Write accounts/models.py — UserProfile model
    (OneToOne→User, role choices, avatar CloudinaryField, subscription_active, created_at)
    Add __str__, docstring, Meta class
    commit: "feat(accounts): add UserProfile model with parent/student/admin role choices"

T2: Write curriculum/models.py — Lesson model
    (key_stage, subject_name, programme_slug, year, unit_slug, unit_title, lesson_number, lesson_title, lesson_url)
    Add __str__, docstring, Meta with ordering
    commit: "feat(curriculum): add Lesson model for Oak National Academy curriculum data"

T3: Write scheduler/models.py — Child model
    (parent FK, first_name, birth_month, birth_year, school_year, academic_year_start, student_user OneToOne, is_active)
    Add __str__, docstring
    commit: "feat(scheduler): add Child model with parent relationship and student_user link"

T4: Write scheduler/models.py — EnrolledSubject model
    (child FK, subject_name, key_stage, lessons_per_week with validators, colour_hex, is_active)
    Add __str__, docstring
    commit: "feat(scheduler): add EnrolledSubject model with lessons_per_week and colour"

T5: Write scheduler/models.py — ScheduledLesson model
    (child FK, lesson FK→curriculum.Lesson, enrolled_subject FK, scheduled_date db_index, order_on_day)
    Add __str__, docstring
    commit: "feat(scheduler): add ScheduledLesson model for auto-generated timetable"

T6: Write tracker/models.py — LessonLog model
    (scheduled_lesson OneToOne, status choices, mastery choices, student_notes, completed_at, rescheduled_to, updated_by FK)
    Add __str__, docstring
    commit: "feat(tracker): add LessonLog model with status and mastery score"

T7: Write tracker/models.py — EvidenceFile model
    (lesson_log FK, file CloudinaryField resource_type=auto, original_filename, uploaded_by FK, uploaded_at)
    Add __str__, docstring
    commit: "feat(tracker): add EvidenceFile model with Cloudinary upload field"

T8: Write reports/models.py — Report model
    (child FK, created_by FK, created_at, report_type choices, date_from, date_to,
     share_token UUIDField default=uuid4 unique, token_expires_at, pdf_file CloudinaryField)
    import uuid at top
    Add __str__, docstring
    commit: "feat(reports): add Report model with UUID share_token for LA access"

T9: python manage.py makemigrations (all apps)
    python manage.py migrate
    commit: "chore: generate and apply initial migrations for all seven models"
```

**Acceptance Criteria:**
- [ ] All 7 models exist in their respective models.py files
- [ ] Every model has `__str__` returning a human-readable string
- [ ] Every model has a docstring explaining its purpose
- [ ] All ForeignKey relationships are correctly defined with on_delete
- [ ] `python manage.py makemigrations` produces 7 migration files (one per app)
- [ ] `python manage.py migrate` completes with no errors
- [ ] `python manage.py check` returns no errors

**Definition of Done:** All 7 models migrated. check passes. Every model has __str__ and docstring.

---

### STORY S0.5 — Django Admin Configuration
```yaml
id: S0.5
epic: E1
sprint: 0
priority: P0
points: 2
status: DONE
depends_on: [S0.4]
```
**User Story:** As an admin, I can manage all application data through the Django admin panel, so that I can provide customer support and manage users without a separate interface.

**Tasks:**
```
T1: accounts/admin.py — Extend UserAdmin to show UserProfile inline
    Register UserProfile with list_display=['user','role','subscription_active'], list_filter=['role']
    commit: "feat(accounts): configure UserAdmin with role and subscription fields"

T2: curriculum/admin.py — Register Lesson
    list_display=['lesson_title','subject_name','year','key_stage']
    search_fields=['lesson_title','subject_name','unit_title']
    list_filter=['key_stage','year','subject_name']
    commit: "feat(curriculum): configure Lesson admin with search and filter"

T3: scheduler/admin.py — Register Child, EnrolledSubject, ScheduledLesson
    Child: list_display=['first_name','school_year','parent'], list_filter=['school_year']
    commit: "feat(scheduler): register scheduler models in Django admin"

T4: tracker/admin.py — Register LessonLog, EvidenceFile
    LessonLog: list_display=['scheduled_lesson','status','mastery'], list_filter=['status','mastery']
    commit: "feat(tracker): register tracker models in Django admin"

T5: reports/admin.py — Register Report
    list_display=['child','report_type','created_at','share_token'], list_filter=['report_type']
    commit: "feat(reports): register Report model in Django admin"
```

**Acceptance Criteria:**
- [ ] All 7 models visible in Django admin at /admin/
- [ ] Superuser can log into admin panel
- [ ] Lesson admin has working search and filter
- [ ] LessonLog admin has status and mastery filters

**Definition of Done:** All models in admin. List views show meaningful columns. Superuser can log in.

---

### STORY S0.6 — Oak Curriculum Seed Command
```yaml
id: S0.6
epic: E1
sprint: 0
priority: P0
points: 3
status: DONE
depends_on: [S0.5]
```
**User Story:** As a developer, I can run a single management command to load the Oak National Academy CSV data into the database, so that the full 10,055-row curriculum is available for subject selection and scheduling.

**Tasks:**
```
T1: Create directory: curriculum/management/__init__.py
    Create directory: curriculum/management/commands/__init__.py
    Create curriculum/management/commands/seed_curriculum.py — scaffold only (class Command, handle stub)
    commit: "feat(curriculum): scaffold seed_curriculum management command"

T2: Implement CSV reading in handle():
    - Accept --file argument (path to CSV)
    - Open CSV with csv.DictReader
    - For each row: Lesson.objects.get_or_create(
        lesson_url=row['lesson_url'],  ← unique key
        defaults={all other fields}
      )
    - Count created vs existing
    Add module docstring explaining command purpose and usage
    commit: "feat(curriculum): implement CSV ingestion with idempotent get_or_create"

T3: Add progress output:
    - Print row count every 500 rows
    - Print final summary: "Seeded: X created, Y already existed. Total: Z lessons."
    commit: "feat(curriculum): add progress logging to seed_curriculum command"
```

**Acceptance Criteria:**
- [ ] `python manage.py seed_curriculum --file path/to/lessons.csv` runs without error
- [ ] Running twice produces no duplicate Lesson records
- [ ] Final output shows correct created/existing counts
- [ ] Command has a module-level docstring with usage example
- [ ] Lesson count in admin matches CSV row count (~10,055)

**Definition of Done:** Seed runs clean. 10,055 records. Idempotent. Documented.

---

### STORY S0.7 — Base Template and Static Files
```yaml
id: S0.7
epic: E1
sprint: 0
priority: P0
points: 2
status: DONE
depends_on: [S0.6]
```
**User Story:** As a developer, I can create a base HTML template with Bootstrap 5 and a configured static file system, so that every page built in subsequent sprints inherits a consistent, accessible layout.

**Tasks:**
```
T1: Configure TEMPLATES in settings.py:
      TEMPLATES[0]['DIRS'] = [BASE_DIR / 'templates']
    Create templates/ directory at project root
    commit: "chore: configure templates directory in settings"

T2: Create templates/base.html:
    - <!DOCTYPE html> with lang="en"
    - Bootstrap 5.3 CSS CDN link in <head>
    - Bootstrap Icons 1.11 CDN link
    - {% block extra_css %}{% endblock %}
    - <nav> with brand "EduTrack", placeholder nav links, empty user area (right)
    - {% if messages %} block rendering Django messages as Bootstrap alerts
    - <main class="container-fluid py-4">{% block content %}{% endblock %}</main>
    - Bootstrap 5.3 JS CDN at bottom of <body>
    - {% block extra_js %}{% endblock %}
    All nav and interactive elements keyboard-navigable
    commit: "feat(templates): add base.html with Bootstrap 5 and Django messages support"

T3: Create static/css/custom.css with CSS variable palette:
    :root {
      --primary: #2563EB;
      --secondary: #EA580C;
      --success: #16A34A;
      --warning: #D97706;
      --danger: #DC2626;
      --dark: #1B2A4A;
      --light-bg: #F8FAFC;
      --border: #E2E8F0;
    }
    Configure in settings.py: STATICFILES_DIRS = [BASE_DIR / 'static']
    Add {% load static %} and <link> to base.html
    commit: "style: add custom CSS with colour system variables"

T4: Create a homepage view in edutrack/views.py:
    def home(request): return render(request, 'home.html')
    Create templates/home.html extending base.html with "EduTrack — Coming Soon" content
    Add URL: path('', views.home, name='home') in edutrack/urls.py
    commit: "feat(edutrack): add homepage placeholder view and template"
```

**Acceptance Criteria:**
- [ ] `python manage.py runserver` — homepage loads with Bootstrap styles
- [ ] Django messages block is present in base.html
- [ ] CSS variables are defined in custom.css
- [ ] W3C HTML validation passes on homepage
- [ ] Static files load (no 404s in browser console)

**Definition of Done:** Homepage renders. Bootstrap loads. Messages block present. W3C valid.

---

### STORY S0.8 — First Heroku Deployment
```yaml
id: S0.8
epic: E1
sprint: 0
priority: P0
points: 3
status: NOT_STARTED
depends_on: [S0.7]
```
**User Story:** As a developer, I can deploy the application skeleton to Heroku, so that we have a live URL from Day 3 and all subsequent work deploys to a real environment.

**Tasks:**
```
T1: Create Procfile: web: gunicorn edutrack.wsgi --log-file -
    Create runtime.txt: python-3.11.9
    commit: "chore: add Procfile and runtime.txt for Heroku deployment"

T2: Configure production security in settings.py:
    ALLOWED_HOSTS includes '.herokuapp.com'
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'DENY'
    Ensure DEBUG=False when DJANGO_DEBUG is not set
    commit: "chore: configure production security settings for Heroku"

T3: heroku create [app-name]
    Set all Config Vars in Heroku dashboard:
      DJANGO_SECRET_KEY, DJANGO_DEBUG=False, ALLOWED_HOSTS, DATABASE_URL,
      CLOUDINARY_URL, STRIPE_PUBLISHABLE_KEY, STRIPE_SECRET_KEY, STRIPE_ENABLED=False
    git push heroku main
    commit: "chore: initial Heroku deployment"

T4: heroku run python manage.py migrate
    heroku run python manage.py seed_curriculum --file [path]
    heroku run python manage.py createsuperuser
    (Heroku CLI commands — no commit needed)

T5: Smoke test live URL:
    - Homepage loads (no 500)
    - /admin/ accessible, superuser login works
    - Admin shows all 7 models
    - Lesson count ~10,055
    Confirm DEBUG=False and no .env in GitHub
    commit: "chore: verify Sprint 0 deployment — empty shell live on Heroku"
```

**Acceptance Criteria:**
- [ ] App accessible at Heroku URL with no 500 error
- [ ] /admin/ panel loads and superuser can log in
- [ ] All 7 models visible in admin
- [ ] curriculum.Lesson count is ~10,055
- [ ] DEBUG=False in Heroku config vars
- [ ] .env file is NOT in GitHub repository
- [ ] .env.example IS in GitHub repository

**Definition of Done:** Live on Heroku. Admin works. Curriculum seeded. DEBUG=False. No secrets in repo.

---

## 🔐 EPIC E2 — Authentication & Roles
**Milestone:** Parent and student can register/login. Role-based access enforced on all views.  
**Sprint:** Sprint 1 (Days 4–6)  
**LO Coverage:** LO3.1, LO3.2, LO3.3

---

### STORY S1.1 — Parent Registration
```yaml
id: S1.1
epic: E2
sprint: 1
priority: P0
points: 3
status: NOT_STARTED
depends_on: [S0.8]
```
**User Story:** As a parent, I can register an account with my email and password, so that I can access the platform and begin managing my child's home education.

**Tasks:**
```
T1: pip install django-crispy-forms crispy-bootstrap5
    pip freeze > requirements.txt
    Confirm in INSTALLED_APPS: 'crispy_forms', 'crispy_bootstrap5'
    CRISPY_TEMPLATE_PACK = 'bootstrap5'
    commit: "chore: add django-crispy-forms with bootstrap5 pack"

T2: accounts/forms.py — Create CustomUserCreationForm(UserCreationForm):
    Add email field (required, unique validation)
    Add first_name, last_name fields
    Override save() to set username=email
    Docstring explaining form purpose
    commit: "feat(accounts): add CustomUserCreationForm with email as primary field"

T3: accounts/views.py — Create register_view():
    GET: render registration form
    POST: validate form → save User → create UserProfile(role='parent') → login → redirect to dashboard
    Add success message: "Welcome to EduTrack! Your parent account is ready."
    Docstring on view function
    commit: "feat(accounts): add parent registration view with automatic UserProfile creation"

T4: accounts/urls.py + include in edutrack/urls.py
    path('accounts/', include('accounts.urls'))
    path('accounts/register/', views.register_view, name='register')
    commit: "feat(accounts): wire registration URL"

T5: templates/accounts/register.html:
    Extends base.html
    {{ form|crispy }} with submit button
    Link to login page
    Semantic HTML: <form>, <label>, aria attributes
    commit: "feat(templates): add registration page template"
```

**Acceptance Criteria:**
- [ ] POST with valid data creates User + UserProfile(role='parent')
- [ ] POST with duplicate email shows "Email already exists" error
- [ ] POST with mismatched passwords shows validation error
- [ ] After success: user is logged in, redirected, success message visible
- [ ] W3C HTML validation passes

**Definition of Done:** Registration creates parent UserProfile. Validation works. Redirects with message. W3C valid.

---

### STORY S1.2 — Login, Logout & Login State
```yaml
id: S1.2
epic: E2
sprint: 1
priority: P0
points: 2
status: NOT_STARTED
depends_on: [S1.1]
```
**User Story:** As a user, I can log in and out of the application, so that I can access my role-appropriate pages and my login state is always visible.

**Tasks:**
```
T1: Configure auth settings in settings.py:
    LOGIN_URL = '/accounts/login/'
    LOGIN_REDIRECT_URL = '/'
    LOGOUT_REDIRECT_URL = '/'
    AUTH_USER_MODEL = 'auth.User'  (default — confirm not changed)
    commit: "feat(accounts): configure login/logout redirect URLs"

T2: accounts/views.py — login_view (wraps Django LoginView with custom template)
    accounts/views.py — logout_view (POST only, redirect to home with message)
    Add to accounts/urls.py
    commit: "feat(accounts): add login and logout views"

T3: templates/accounts/login.html — extends base, crispy form, link to register
    commit: "feat(templates): add login page template"

T4: Update templates/base.html navbar:
    {% if user.is_authenticated %}
      Show: user.first_name + role badge (Bootstrap badge component)
      Show: logout button (POST form, not GET link)
    {% else %}
      Show: Login link + Register link
    {% endif %}
    commit: "feat(templates): reflect login state in navbar with name and role badge"
```

**Acceptance Criteria:**
- [ ] Login with valid credentials redirects to role-appropriate page
- [ ] Login with wrong password shows error message
- [ ] Navbar shows first name + role badge when logged in
- [ ] Navbar shows Login/Register when logged out
- [ ] Logout clears session and redirects to homepage
- [ ] Unauthenticated request to protected URL redirects to /accounts/login/?next=...

**Definition of Done:** Login/logout works. Navbar reflects state. Redirect on protected URL.

---

### STORY S1.3 — Role-Based Access Decorator
```yaml
id: S1.3
epic: E2
sprint: 1
priority: P0
points: 2
status: NOT_STARTED
depends_on: [S1.2]
```
**User Story:** As a developer, I can apply a single decorator to any view to restrict it by user role, so that role enforcement is consistent, centralised, and one line of code.

**Tasks:**
```
T1: accounts/decorators.py — create role_required(role):
    """
    Decorator factory. Wraps a view to enforce role-based access.
    Unauthenticated → redirect to login with next param.
    Wrong role → redirect to role-appropriate home with error message.
    Correct role → call view normally.
    Usage: @role_required('parent')
    """
    Use functools.wraps to preserve wrapped function metadata
    commit: "feat(accounts): add role_required decorator for role-based view protection"

T2: Apply @role_required('parent') to register_view (test it works)
    Remove it after testing (register must be public)
    Manually test: logged-in student hits parent URL → redirected
    commit: "test(accounts): verify role_required decorator redirects incorrect roles"
```

**Acceptance Criteria:**
- [ ] @role_required('parent') on a view: student is redirected with error message
- [ ] @role_required('student') on a view: parent is redirected with error message
- [ ] Unauthenticated user hitting any decorated view → /accounts/login/?next=...
- [ ] Decorator has a docstring with usage example
- [ ] functools.wraps used (preserves view function name)

**Definition of Done:** Decorator exists, documented. Parent→student blocked. Student→parent blocked. Unauth→login.

---

### STORY S1.4 — Parent Creates Student Login
```yaml
id: S1.4
epic: E2
sprint: 1
priority: P0
points: 2
status: NOT_STARTED
depends_on: [S1.3]
```
**User Story:** As a parent, I can create login credentials for my child, so that my child can log in and see their calendar without needing an email address.

**Tasks:**
```
T1: accounts/forms.py — StudentCreationForm:
    Fields: username (CharField), password1, password2
    Validate username uniqueness
    commit: "feat(accounts): add StudentCreationForm for parent-created student credentials"

T2: scheduler/views.py — create_student_login_view:
    @login_required @role_required('parent')
    GET: render form for given child_id
    POST: create User + UserProfile(role='student') + link to child.student_user
    Verify child.parent == request.user (403 if not)
    Add success message with username
    commit: "feat(scheduler): add view for parent to create student login credentials"

T3: templates/scheduler/create_student_login.html
    Form + credential display after creation + success message
    commit: "feat(templates): add student credential creation page"

T4: Add URL: /children/<int:child_id>/create-login/
    commit: "feat(scheduler): wire student login creation URL"
```

**Acceptance Criteria:**
- [ ] POST creates User(username=...) + UserProfile(role='student')
- [ ] Child.student_user is set to new User
- [ ] Duplicate username shows validation error
- [ ] Parent accessing another parent's child → 403
- [ ] Student can log in with created credentials
- [ ] View is inaccessible to student role

**Definition of Done:** Student login created and linked to Child. Ownership check. Student can log in.

---

## 📅 EPIC E3 — Child Setup & Scheduling
**Milestone:** Parent adds child, selects subjects, triggers auto-scheduler. 180-day timetable generated.  
**Sprint:** Sprint 1 (Days 4–6)  
**LO Coverage:** LO1.4, LO2.2, LO2.3, LO2.4, LO7.1

---

### STORY S1.5 — Add Child Profile
```yaml
id: S1.5
epic: E3
sprint: 1
priority: P0
points: 2
status: NOT_STARTED
depends_on: [S1.3]
```
**User Story:** As a parent, I can add my child's profile to my account, so that the system knows which school year my child is in and can present the right curriculum.

**Tasks:**
```
T1: scheduler/forms.py — ChildForm(ModelForm):
    Fields: first_name, birth_month, birth_year, school_year (ChoiceField from DB), academic_year_start
    Populate school_year choices from Lesson.objects.values_list('year',flat=True).distinct()
    Docstring on form class
    commit: "feat(scheduler): add ChildForm with school year choices from curriculum data"

T2: scheduler/views.py — add_child_view:
    @login_required @role_required('parent')
    GET: render ChildForm
    POST: validate → save child (parent=request.user) → redirect to subject_selection
    Add success message: "[Name] added! Now select their subjects."
    commit: "feat(scheduler): add child profile creation view"

T3: templates/scheduler/add_child.html — crispy form, extends base
    commit: "feat(templates): add child profile creation page"

T4: Add URL: path('children/add/', ...)
    Add /children/ list view (shows parent's children with links to manage)
    commit: "feat(scheduler): wire add child and child list URLs"
```

**Acceptance Criteria:**
- [ ] POST with valid data creates Child linked to request.user
- [ ] After save: redirect to subject selection for that child
- [ ] school_year dropdown populated from curriculum data (not hardcoded)
- [ ] Missing required fields show validation errors
- [ ] View inaccessible to student role

**Definition of Done:** Child created linked to parent. Redirects to subject selection. Validation works.

---

### STORY S1.6 — Subject Selection Page
```yaml
id: S1.6
epic: E3
sprint: 1
priority: P0
points: 3
status: NOT_STARTED
depends_on: [S1.5]
```
**User Story:** As a parent, I can select which Oak National Academy subjects my child will study and set a weekly lesson pace for each, so that the scheduling engine has everything it needs to generate the full timetable.

**Tasks:**
```
T1: scheduler/views.py — subject_selection_view:
    @login_required @role_required('parent')
    Verify child belongs to request.user
    GET: query distinct subjects for child.school_year grouped by key_stage
    Context: {key_stage: [{subject_name, total_lessons}, ...]}
    commit: "feat(scheduler): add subject selection view with grouped curriculum data"

T2: On valid POST:
    Parse submitted checkboxes + spinners
    For each selected subject: EnrolledSubject.objects.create(
      child, subject_name, key_stage,
      lessons_per_week=submitted_pace,
      colour_hex=SUBJECT_COLOUR_PALETTE[index % len(SUBJECT_COLOUR_PALETTE)]
    )
    SUBJECT_COLOUR_PALETTE = ['#E63946','#2A9D8F','#E9C46A','#F4A261','#264653','#8338EC','#3A86FF','#FB5607','#FFBE0B','#06D6A0']
    Redirect to generate schedule confirmation page
    commit: "feat(scheduler): implement EnrolledSubject creation with automatic colour assignment"

T3: templates/scheduler/subject_selection.html:
    Accordion grouped by key_stage
    Each row: checkbox + subject name + "(N lessons)" badge + number spinner
    Spinner disabled by default; enabled when checkbox ticked (vanilla JS)
    At least 1 subject required (HTML5 validation + view-level check)
    commit: "feat(templates): add subject selection page with accordion groups and pace spinners"

T4: style: JS to link checkbox↔spinner enable/disable state
    commit: "style: add JS checkbox-to-spinner link on subject selection page"

T5: Add URL: path('children/<int:child_id>/subjects/', ...)
    commit: "feat(scheduler): wire subject selection URL"
```

**Acceptance Criteria:**
- [ ] Subjects grouped by key_stage in accordion
- [ ] Spinner disabled until checkbox ticked
- [ ] Submitting with 0 subjects selected shows validation error
- [ ] EnrolledSubjects created with correct colour_hex from palette
- [ ] Each subject colour is distinct (palette cycles)
- [ ] View inaccessible to student role and other parents' children

**Definition of Done:** EnrolledSubjects created with colour. Spinner UX works. Min 1 subject enforced.

---

### STORY S1.7 — Schedule Generation Service
```yaml
id: S1.7
epic: E3
sprint: 1
priority: P0
points: 5
status: NOT_STARTED
depends_on: [S1.6]
```
**User Story:** As a developer, I can call a standalone service function to generate a 180-day lesson schedule, so that the algorithm is independently testable and separate from the web layer.

> **Reference:** See Section 1.6 of this document for full algorithm pseudocode.

**Tasks:**
```
T1: Create scheduler/services.py — add module docstring + generate_schedule function skeleton
    (parameters, return type annotation, full docstring)
    commit: "feat(scheduler): add generate_schedule service function with full docstring"

T2: Implement Step 1 — build 180-day school day list (weekdays only from academic_year_start)
    commit: "feat(scheduler): implement 180-day weekday list generation"

T3: Implement Step 2 — build per-subject lesson queues from curriculum
    (ordered by unit_slug, lesson_number)
    commit: "feat(scheduler): implement per-subject lesson queue builder"

T4: Implement Step 3 — round-robin distribution with weekly pace limits
    (reset week_counts on new ISO week number)
    commit: "feat(scheduler): implement round-robin lesson distribution with weekly limits"

T5: Implement Step 4 — ScheduledLesson.objects.bulk_create(to_create, batch_size=500)
    Return len(to_create)
    commit: "feat(scheduler): implement bulk_create for ScheduledLesson records"
```

**Acceptance Criteria:**
- [ ] Function exists in scheduler/services.py with full docstring
- [ ] No lesson falls on Saturday or Sunday
- [ ] No subject exceeds its lessons_per_week in any calendar week
- [ ] Function returns integer count of records created
- [ ] bulk_create used with batch_size=500
- [ ] Running on fixture data completes without error

**Definition of Done:** Algorithm implemented, documented. Runs clean. Uses bulk_create. Returns count.

---

### STORY S1.8 — Schedule Generation Web Layer
```yaml
id: S1.8
epic: E3
sprint: 1
priority: P0
points: 2
status: NOT_STARTED
depends_on: [S1.7]
```
**User Story:** As a parent, I can click "Generate Schedule" to have all lessons automatically distributed across the school year, so that my child immediately has a complete day-by-day timetable.

**Tasks:**
```
T1: scheduler/views.py — generate_schedule_view:
    @login_required @role_required('parent')
    GET: render confirmation page with summary (child name, subject list, estimated lesson counts)
    POST: delete existing ScheduledLessons for child → call generate_schedule() → success message
    Message: "[Name]'s schedule is ready — [N] lessons scheduled across 180 days."
    Redirect to parent dashboard
    commit: "feat(scheduler): add schedule generation view calling services.generate_schedule"

T2: templates/scheduler/generate_schedule.html — summary table + confirm button
    commit: "feat(templates): add schedule generation confirmation page"

T3: Add URL: path('children/<int:child_id>/schedule/generate/', ...)
    commit: "feat(scheduler): wire schedule generation URL"
```

**Acceptance Criteria:**
- [ ] GET shows summary of what will be scheduled
- [ ] POST generates schedule and shows correct count in message
- [ ] Running POST twice (regenerate) deletes old schedule cleanly
- [ ] Parent redirected to dashboard after generation
- [ ] View inaccessible to student role

**Definition of Done:** Schedule generates. Count shown in message. Idempotent. Role protected.

---

### STORY S1.9 — Parent Dashboard
```yaml
id: S1.9
epic: E3
sprint: 1
priority: P1
points: 2
status: NOT_STARTED
depends_on: [S1.8]
```
**User Story:** As a parent, I can see a dashboard with a summary of my child's learning progress, so that I always have a quick overview without needing to drill into the calendar.

**Tasks:**
```
T1: scheduler/views.py — parent_dashboard_view:
    @login_required @role_required('parent')
    Query: all children for request.user
    For each child: total lessons scheduled, completed this week (Mon–Sun), overall % complete
    If no children: empty state with "Add your first child" CTA
    commit: "feat(scheduler): add parent dashboard view with progress summary"

T2: Update edutrack/urls.py root URL:
    def root_redirect(request): redirect based on role (parent→dashboard, student→calendar, unauth→home)
    commit: "feat(edutrack): add role-based root URL redirect"

T3: templates/scheduler/parent_dashboard.html — Bootstrap cards per child + CTA button
    commit: "feat(templates): add parent dashboard with child summary cards"
```

**Acceptance Criteria:**
- [ ] Dashboard shows stats per child
- [ ] Empty state shows Add Child prompt when no children exist
- [ ] Root URL / redirects parent here, student to /calendar/
- [ ] W3C valid, responsive

**Definition of Done:** Dashboard renders with correct stats. Empty state works. Role redirect from /.

---

### STORY S1.10 — Sprint 1 Deployment
```yaml
id: S1.10
epic: E3
sprint: 1
priority: P0
points: 1
status: NOT_STARTED
depends_on: [S1.9]
```
**User Story:** As a developer, I can deploy Sprint 1 to Heroku and verify all auth and scheduling flows work in production.

**Tasks:**
```
T1: git push heroku main; heroku run python manage.py migrate
    Smoke test all Sprint 1 flows on live URL
    commit: "chore: verify Sprint 1 deployment — auth and scheduling live on Heroku"
```

**Acceptance Criteria (Smoke Test):**
- [ ] Parent registration → child add → subject select → generate schedule (end-to-end)
- [ ] Student login with parent-created credentials works
- [ ] Role access control: student blocked from /children/, parent blocked from /calendar/
- [ ] Success messages visible at each step
- [ ] No 500 errors

**Definition of Done:** All Sprint 1 features work on Heroku. No errors. Role checks enforced.

---

## 🗓️ EPIC E4 — Calendar View
**Milestone:** Student sees Syllabird-style weekly calendar with coloured subject cards.  
**Sprint:** Sprint 2 (Days 7–9) | **LO Coverage:** LO1.1

---

### STORY S2.1 — Weekly Calendar View Structure
```yaml
id: S2.1
epic: E4
sprint: 2
priority: P0
points: 3
status: NOT_STARTED
depends_on: [S1.10]
```
**User Story:** As a student, I can see a weekly calendar showing all my scheduled lessons organised into Monday to Friday columns, so that I always know exactly what I am supposed to study each day.

**Tasks:**
```
T1: tracker/views.py — calendar_view:
    @login_required @role_required('student')
    Parse year/week from URL params (default: current ISO week)
    Query ScheduledLessons for student's child for that week
    Build context: {monday: [lessons], tuesday: [lessons], ...} + week_dates
    Include for each lesson: scheduled_lesson, lesson_log (if exists), enrolled_subject.colour_hex
    commit: "feat(tracker): add weekly calendar view with day-keyed lesson context"

T2: templates/tracker/calendar.html (extends base):
    5-column CSS Grid (Mon–Fri)
    Day column header: day name + date (e.g. "Monday 9 Jan")
    Empty state per column if no lessons
    Lesson card placeholder (title + subject label — colours in next story)
    {% block extra_css %} — calendar grid CSS
    commit: "feat(templates): add weekly calendar template with 5-column CSS grid layout"

T3: tracker/urls.py: path('calendar/', ...) + path('calendar/<int:year>/<int:week>/', ...)
    Include in edutrack/urls.py
    commit: "feat(tracker): wire calendar URLs with week navigation parameters"
```

**Acceptance Criteria:**
- [ ] Calendar shows 5 columns Mon–Fri with correct dates
- [ ] Lessons appear in correct day column
- [ ] Empty day shows "No lessons scheduled" message
- [ ] View inaccessible to parent role directly
- [ ] W3C valid

**Definition of Done:** Calendar renders for current week. Lessons in correct columns. Empty state shown.

---

### STORY S2.2 — Calendar Week Navigation
```yaml
id: S2.2
epic: E4
sprint: 2
priority: P0
points: 1
status: NOT_STARTED
depends_on: [S2.1]
```
**User Story:** As a student, I can navigate to previous and next weeks, so that I can review past lessons and see upcoming lessons without leaving the calendar.

**Tasks:**
```
T1: tracker/views.py — compute prev_week and next_week ISO year/week tuples
    Add to context: prev_url, next_url, today_url, week_display (e.g. "9–13 Jan 2025")
    commit: "feat(tracker): add week navigation logic to calendar view"

T2: templates/tracker/calendar.html — add to header: ← prev link, → next link, "Today" button
    commit: "feat(templates): add week navigation controls to calendar header"
```

**Acceptance Criteria:**
- [ ] ← navigates to previous week with correct dates
- [ ] → navigates to next week with correct dates
- [ ] "Today" always returns to current ISO week
- [ ] Week date range displayed in header updates correctly

**Definition of Done:** Navigation works. Today button works. URL reflects active week.

---

### STORY S2.3 — Subject Colour Cards
```yaml
id: S2.3
epic: E4
sprint: 2
priority: P0
points: 2
status: NOT_STARTED
depends_on: [S2.2]
```
**User Story:** As a student, I can see each lesson card styled with its subject's colour, so that I can instantly identify subjects and the calendar is visually clear.

**Tasks:**
```
T1: templates/tracker/calendar.html — update lesson card markup:
    <div class="lesson-card" style="--subject-colour: {{ scheduled_lesson.enrolled_subject.colour_hex }}">
      <div class="card-header">{{ scheduled_lesson.enrolled_subject.subject_name }}</div>
      <div class="card-body">{{ scheduled_lesson.lesson.lesson_title }}</div>
      <div class="card-footer">
        {% if log.status == 'complete' %}<span class="badge bg-success">✓ Complete</span>{% endif %}
        {% if log.status == 'skipped' %}<span class="badge bg-secondary">Skipped</span>{% endif %}
        {% if log.mastery == 'green' %}<span class="mastery-dot green"></span>{% endif %}
      </div>
    </div>
    commit: "feat(templates): apply subject colour system to calendar lesson cards"

T2: static/css/custom.css — add card styles:
    .lesson-card { border-left: 4px solid var(--subject-colour); border-radius: 6px; ... }
    .card-header { background-color: var(--subject-colour); color: white; ... }
    .mastery-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
    .mastery-dot.green { background: #16A34A; } .amber { background: #D97706; } .red { background: #DC2626; }
    commit: "style: add lesson card CSS with coloured header band and mastery dot"
```

**Acceptance Criteria:**
- [ ] Same subject always uses same colour across all cards
- [ ] Card header band shows subject colour
- [ ] Complete badge visible on completed lessons
- [ ] Mastery dot visible on lessons with mastery set
- [ ] Text contrast is readable on all subject colours

**Definition of Done:** Colour system applied. Status badges visible. Contrast readable.

---

## 📋 EPIC E5 — Lesson Tracking
**Sprint:** Sprint 2 (Days 7–9) | **LO Coverage:** LO2.2, LO2.3, LO2.4

---

### STORY S2.4 — Lesson Detail Modal
```yaml
id: S2.4
epic: E5
sprint: 2
priority: P0
points: 3
status: NOT_STARTED
depends_on: [S2.3]
```
**User Story:** As a student, I can click a lesson card to see lesson details in a modal panel, so that I can interact with a lesson without leaving the calendar.

**Tasks:**
```
T1: tracker/views.py — lesson_detail_view:
    @login_required @role_required('student')
    Verify lesson belongs to student's child
    Return JSON: {id, lesson_title, unit_title, subject_name, scheduled_date, lesson_url,
                  colour_hex, status, mastery, student_notes, evidence_count}
    commit: "feat(tracker): add lesson detail JSON endpoint for modal population"

T2: Add URL: path('lessons/<int:scheduled_id>/detail/', ..., name='lesson_detail')
    commit: "feat(tracker): wire lesson detail JSON URL"

T3: templates/tracker/calendar.html — add Bootstrap Modal markup:
    <div id="lesson-modal" class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
    Sections: header (title + coloured band), body (details + Oak URL link + action buttons)
    Action buttons placeholder: Complete, Skip, mastery toggles
    commit: "feat(templates): add lesson modal structure with ARIA attributes"

T4: static/js/calendar.js (new file):
    document.querySelectorAll('.lesson-card').forEach(card => {
      card.addEventListener('click', async () => {
        const data = await fetch(`/lessons/${card.dataset.id}/detail/`).then(r => r.json());
        // populate modal fields from data
        // show modal: new bootstrap.Modal(document.getElementById('lesson-modal')).show()
      });
    });
    commit: "style: add calendar.js with card click handler and modal population via fetch"
```

**Acceptance Criteria:**
- [ ] Clicking card opens modal with correct lesson data
- [ ] Oak lesson URL opens in new tab (target="_blank" rel="noopener")
- [ ] Modal has aria-modal="true" and aria-labelledby
- [ ] Modal closes on X click and backdrop click
- [ ] Student cannot open modal for another child's lessons

**Definition of Done:** Modal opens with correct data. ARIA present. Oak URL works. Ownership enforced.

---

### STORY S2.5 — Mark Lesson Complete or Skip
```yaml
id: S2.5
epic: E5
sprint: 2
priority: P0
points: 3
status: NOT_STARTED
depends_on: [S2.4]
```
**User Story:** As a student, I can mark a lesson as complete or skip it from the modal, so that my progress is recorded and my parent can see what I have done.

**Tasks:**
```
T1: tracker/views.py — update_lesson_status_view:
    @login_required @role_required('student')
    POST: {status: 'complete'|'skipped'} + CSRF token
    LessonLog.objects.get_or_create(scheduled_lesson=...)
    Update status; if complete: set completed_at = timezone.now()
    Return JSON: {success: true, status: ..., message: ...}
    Verify ownership before save
    commit: "feat(tracker): add lesson status update view for complete and skip actions"

T2: Add URL: path('lessons/<int:scheduled_id>/update/', ...)
    commit: "feat(tracker): wire lesson status update URL"

T3: static/js/calendar.js — add click handlers:
    Complete button → fetch POST to /lessons/{id}/update/ with {status: 'complete'}
    Skip button → fetch POST with {status: 'skipped'}
    On success: update card badge in DOM without page reload
    Include CSRF token from cookie in headers: 'X-CSRFToken': getCookie('csrftoken')
    commit: "style: add AJAX lesson status update with immediate card badge refresh in calendar.js"
```

**Acceptance Criteria:**
- [ ] Clicking Complete: LessonLog.status='complete', completed_at set
- [ ] Clicking Skip: LessonLog.status='skipped'
- [ ] Card badge updates immediately (no page reload)
- [ ] CSRF token included in all AJAX POST requests
- [ ] Ownership enforced (student cannot update another's lesson)

**Definition of Done:** Status saves. Card updates without reload. CSRF present. Ownership checked.

---

### STORY S2.6 — Mastery Score
```yaml
id: S2.6
epic: E5
sprint: 2
priority: P0
points: 2
status: NOT_STARTED
depends_on: [S2.5]
```
**User Story:** As a student, I can set a mastery score of Green, Amber, or Red for any lesson, so that I and my parent can track how confident I feel about each topic.

**Tasks:**
```
T1: tracker/views.py — update_mastery_view:
    POST: {mastery: 'green'|'amber'|'red'}
    get_or_create LessonLog; update mastery; return JSON success
    commit: "feat(tracker): add mastery score update view"

T2: Add URL: path('lessons/<int:scheduled_id>/mastery/', ...)
    commit: "feat(tracker): wire mastery update URL"

T3: templates/tracker/calendar.html modal — add mastery button group:
    Three buttons with data-mastery="green"|"amber"|"red"
    Active state class on currently selected mastery
    commit: "feat(templates): add mastery score button group to lesson modal"

T4: static/js/calendar.js — mastery button click → fetch POST → update active state + card dot
    commit: "style: add AJAX mastery update with active button state and card dot refresh"
```

**Acceptance Criteria:**
- [ ] Selecting mastery saves to LessonLog.mastery
- [ ] Only selected button shows active state (others deselected)
- [ ] Card mastery dot updates immediately
- [ ] Mastery can be changed after initial selection

**Definition of Done:** Mastery saves and shows on card. Active state updates. Changeable.

---

### STORY S2.7 — Student Notes
```yaml
id: S2.7
epic: E5
sprint: 2
priority: P0
points: 2
status: NOT_STARTED
depends_on: [S2.6]
```
**User Story:** As a student, I can add a personal note to any lesson, so that my portfolio reflects my genuine engagement with the content.

**Tasks:**
```
T1: tracker/views.py — save_notes_view:
    POST: {notes: string (max 1000 chars)}
    get_or_create LessonLog; update student_notes; return JSON success
    commit: "feat(tracker): add student notes save view"

T2: Update lesson_detail_view to include student_notes in JSON response
    commit: "feat(tracker): include saved notes in lesson detail endpoint response"

T3: templates/tracker/calendar.html modal — add notes textarea with char counter
    <textarea maxlength="1000"> + <span id="char-count">0/1000</span>
    commit: "feat(templates): add notes textarea with character counter to lesson modal"

T4: static/js/calendar.js — populate textarea on modal open; save on button click; update char counter
    commit: "style: add notes population and save handler in calendar.js"
```

**Acceptance Criteria:**
- [ ] Notes save to LessonLog.student_notes
- [ ] Notes re-appear when modal reopened for same lesson
- [ ] Character counter updates in real-time
- [ ] Empty notes are valid (field is optional)
- [ ] Notes > 1000 chars are rejected

**Definition of Done:** Notes save and reload. Char limit enforced. Empty is valid.

---

### STORY S2.8 — Reschedule a Lesson
```yaml
id: S2.8
epic: E5
sprint: 2
priority: P1
points: 2
status: NOT_STARTED
depends_on: [S2.7]
```
**User Story:** As a student, I can move a lesson to a different date, so that my calendar stays accurate when I cannot complete something on the scheduled day.

**Tasks:**
```
T1: tracker/views.py — reschedule_lesson_view:
    POST: {new_date: 'YYYY-MM-DD'}
    Validate new_date > today
    Update ScheduledLesson.scheduled_date
    get_or_create LessonLog; set rescheduled_to = new_date
    Return JSON success
    commit: "feat(tracker): add lesson reschedule view with future-date validation"

T2: Add URL: path('lessons/<int:scheduled_id>/reschedule/', ...)
    commit: "feat(tracker): wire lesson reschedule URL"

T3: templates/tracker/calendar.html modal — add reschedule section: date input (min=tomorrow) + button
    commit: "feat(templates): add reschedule section with date picker to lesson modal"

T4: static/js/calendar.js — reschedule submit → fetch POST → close modal → reload calendar
    commit: "style: add reschedule AJAX handler in calendar.js"
```

**Acceptance Criteria:**
- [ ] Rescheduling to a past date is rejected
- [ ] Lesson disappears from original day after reschedule
- [ ] Lesson appears on new date when navigating to that week
- [ ] LessonLog.rescheduled_to is set for audit trail

**Definition of Done:** Reschedule moves lesson. Past dates rejected. Audit field set.

---

### STORY S2.9 — Parent Read-Only Calendar
```yaml
id: S2.9
epic: E5
sprint: 2
priority: P0
points: 2
status: NOT_STARTED
depends_on: [S2.8]
```
**User Story:** As a parent, I can view my child's weekly calendar in read-only mode, so that I can monitor progress without logging in as the student.

**Tasks:**
```
T1: tracker/views.py — parent_calendar_view:
    @login_required @role_required('parent')
    Accept child_id param; verify child.parent == request.user (403 if not)
    Same query as student calendar view; pass is_readonly=True to context
    commit: "feat(tracker): add parent read-only calendar view with ownership check"

T2: templates/tracker/calendar.html — conditional rendering:
    {% if not is_readonly %} … action buttons … {% endif %}
    commit: "feat(templates): conditionally hide action buttons in read-only calendar mode"

T3: Add URLs: /parent/calendar/<int:child_id>/ and /parent/calendar/<int:child_id>/<int:year>/<int:week>/
    commit: "feat(tracker): wire parent calendar URLs"
```

**Acceptance Criteria:**
- [ ] Parent sees child's calendar with correct lessons
- [ ] Complete/Skip/Mastery buttons are NOT visible to parent
- [ ] Accessing another parent's child returns 403
- [ ] Week navigation works in parent view

**Definition of Done:** Parent sees read-only calendar. No action buttons. Ownership enforced.

---

## 📁 EPIC E6 — Evidence & Files
**Sprint:** Sprint 2 (Days 7–9) | **LO Coverage:** LO2.2

---

### STORY S2.10 — Evidence File Upload
```yaml
id: S2.10
epic: E6
sprint: 2
priority: P0
points: 3
status: NOT_STARTED
depends_on: [S2.9]
```
**User Story:** As a student, I can upload a file as evidence of my work for any lesson, so that my portfolio contains tangible proof of my learning.

**Tasks:**
```
T1: tracker/views.py — upload_evidence_view:
    @login_required @role_required('student')
    POST: multipart form with file
    Validate file type (image/*, application/pdf, .doc, .docx)
    get_or_create LessonLog
    EvidenceFile.objects.create(lesson_log=log, file=request.FILES['file'],
      original_filename=file.name, uploaded_by=request.user)
    Return JSON: {success: true, file_id, filename, uploaded_at}
    commit: "feat(tracker): add evidence file upload view with Cloudinary storage"

T2: Add URL: path('lessons/<int:scheduled_id>/upload/', ...)
    commit: "feat(tracker): wire evidence upload URL"

T3: templates/tracker/calendar.html modal — add evidence section:
    <input type="file" accept="image/*,.pdf,.doc,.docx">
    Upload button + evidence count badge
    commit: "feat(templates): add evidence upload form to lesson modal"

T4: Update lesson_detail_view to include evidence_count in response
    static/js/calendar.js — handle file upload via FormData + fetch; update count badge
    commit: "style: add evidence file upload handler in calendar.js"
```

**Acceptance Criteria:**
- [ ] Valid file types upload to Cloudinary; EvidenceFile record created
- [ ] Invalid file types (e.g. .exe) show validation error; not uploaded
- [ ] Evidence count badge increments after upload
- [ ] LessonLog is created if it does not yet exist

**Definition of Done:** Files upload to Cloudinary. Record created. Invalid types rejected. Count updates.

---

### STORY S2.11 — Evidence File List and Delete
```yaml
id: S2.11
epic: E6
sprint: 2
priority: P0
points: 2
status: NOT_STARTED
depends_on: [S2.10]
```
**User Story:** As a student, I can see all uploaded evidence files for a lesson and delete incorrect ones, so that I maintain an accurate portfolio.

**Tasks:**
```
T1: tracker/views.py — delete_evidence_view:
    @login_required @role_required('student')
    Verify EvidenceFile.uploaded_by == request.user (403 if not)
    Delete from Cloudinary (cloudinary.uploader.destroy(public_id))
    Delete EvidenceFile record
    Return JSON success
    commit: "feat(tracker): add evidence file deletion view with Cloudinary cleanup"

T2: Add URL: path('evidence/<int:file_id>/delete/', ...)
    commit: "feat(tracker): wire evidence delete URL"

T3: Update lesson_detail_view to include file list: [{id, original_filename, uploaded_at}, ...]
    commit: "feat(tracker): include evidence file list in lesson detail endpoint"

T4: static/js/calendar.js — render file list in modal; delete handler with confirm()
    commit: "style: add evidence file list rendering and delete confirmation handler"
```

**Acceptance Criteria:**
- [ ] File list shows filename + upload date for each file
- [ ] Delete button with confirm prompt removes file from DB and Cloudinary
- [ ] Deleting another student's file returns 403
- [ ] File list updates after deletion without page reload

**Definition of Done:** File list renders. Delete removes from DB and Cloudinary. Ownership enforced.

---

### STORY S2.12 — Sprint 2 Deployment
```yaml
id: S2.12
epic: E6
sprint: 2
priority: P0
points: 1
status: NOT_STARTED
depends_on: [S2.11]
```
**User Story:** As a developer, I can deploy Sprint 2 to Heroku and verify the full student lesson interaction loop works in production.

**Tasks:**
```
T1: git push heroku main; heroku run python manage.py migrate
    Smoke test: student full interaction loop + parent read-only
    Verify Cloudinary uploads work in production
    commit: "chore: verify Sprint 2 deployment — full lesson interaction loop live"
```

**Acceptance Criteria (Smoke Test):**
- [ ] Student marks lesson complete; card updates immediately
- [ ] Mastery scores save and show on card
- [ ] Notes save and reload on modal reopen
- [ ] File uploads to Cloudinary in production
- [ ] Parent calendar shows correct read-only view
- [ ] No 500 errors

**Definition of Done:** All Sprint 2 features work on Heroku. Cloudinary uploads confirmed.

---

## 📄 EPIC E7 — Reports & LA Sharing
**Sprint:** Sprint 3 (Days 10–12) | **LO Coverage:** LO2.2, LO2.4, LO3.1, LO3.3

---

### STORY S3.1 — Report Creation Form
```yaml
id: S3.1
epic: E7
sprint: 3
priority: P0
points: 2
status: NOT_STARTED
depends_on: [S2.12]
```
**User Story:** As a parent, I can fill in a form to specify a report's date range and type, so that I can generate exactly the evidence the LA requires.

**Tasks:**
```
T1: reports/forms.py — ReportForm(ModelForm):
    Fields: date_from (DateField), date_to (DateField), report_type (ChoiceField)
    clean(): validate date_from < date_to
    commit: "feat(reports): add ReportForm with date range validation"

T2: reports/views.py — create_report_view:
    @login_required @role_required('parent')
    GET: render form + preview (count completed lessons in date range for child)
    POST: validate form → proceed to PDF generation (next story)
    commit: "feat(reports): add report creation view with completed lesson preview"

T3: templates/reports/create_report.html — crispy form + preview stats
    commit: "feat(templates): add report creation page with parameter form and preview"

T4: Add URL: path('reports/create/<int:child_id>/', ...)
    commit: "feat(reports): wire report creation URL"
```

**Acceptance Criteria:**
- [ ] date_from > date_to shows validation error
- [ ] Preview shows number of completed lessons in the selected date range
- [ ] Both report types (Summary / Full Portfolio) available in dropdown
- [ ] View inaccessible to student role

**Definition of Done:** Form renders. Date validation works. Preview accurate. Role protected.

---

### STORY S3.2 — PDF Report Generation
```yaml
id: S3.2
epic: E7
sprint: 3
priority: P0
points: 5
status: NOT_STARTED
depends_on: [S3.1]
```
**User Story:** As a parent, I can generate and download a PDF evidence report, so that I can submit a professional document to the Local Authority.

**Tasks:**
```
T1: pip install xhtml2pdf; pip freeze > requirements.txt
    commit: "chore: add xhtml2pdf to requirements.txt"

T2: reports/services.py — generate_pdf(report) function:
    """Generates PDF from report data using xhtml2pdf."""
    Query LessonLogs in report.date_from..date_to for report.child
    Render reports/pdf_template.html with context
    Use xhtml2pdf pisa.CreatePDF() to generate PDF bytes
    Upload bytes to Cloudinary; save public_url to report.pdf_file
    Return download URL
    commit: "feat(reports): implement PDF generation service with xhtml2pdf"

T3: templates/reports/pdf_template.html — clean print-ready HTML:
    Child name, school year, date range, report type
    Per-subject table: subject name, lessons completed, completion %, mastery breakdown
    If report_type=='portfolio': per-lesson rows with notes and mastery colour
    (Keep layout simple — tables and text only for xhtml2pdf compatibility)
    commit: "feat(reports): add HTML-to-PDF report template"

T4: reports/views.py — update create_report_view POST:
    Create Report record → call generate_pdf() → redirect to report_detail
    Add success message: "Report generated! Download below."
    commit: "feat(reports): wire PDF generation to report creation POST"

T5: reports/views.py — report_detail_view:
    Show report metadata + PDF download link + share token URL
    Add URL: path('reports/<int:report_id>/', ...)
    commit: "feat(reports): add report detail view with download link and share URL"
```

**Acceptance Criteria:**
- [ ] PDF downloads on click
- [ ] PDF contains child name, date range, and subject breakdown
- [ ] Full Portfolio type includes per-lesson notes and mastery
- [ ] Summary type contains totals only
- [ ] PDF file stored in Cloudinary; Report.pdf_file is set

**Definition of Done:** PDF downloads with correct content. Both types render. Stored in Cloudinary.

---

### STORY S3.3 — LA Share Token Link
```yaml
id: S3.3
epic: E7
sprint: 3
priority: P0
points: 3
status: NOT_STARTED
depends_on: [S3.2]
```
**User Story:** As a parent, I can share a report via a secure link that does not require the LA to log in, so that the LA officer can view the evidence instantly.

**Tasks:**
```
T1: reports/views.py — token_report_view:
    No @login_required
    URL param: <uuid:token>
    Lookup Report by share_token; 404 if not found
    Check token_expires_at: if set and past → 403 with "This link has expired" message
    Render reports/shared_report.html (read-only, no navbar auth links)
    commit: "feat(reports): add LA share token view with UUID validation and expiry check"

T2: Add URL: path('reports/share/<uuid:token>/', ...)
    commit: "feat(reports): wire LA share token URL"

T3: templates/reports/shared_report.html:
    Standalone template (no {% extends 'base.html' %})
    EduTrack branding only; no navbar login/logout
    Report content + "Generated by EduTrack" footer
    commit: "feat(templates): add standalone LA report template for token access"

T4: templates/reports/report_detail.html — add share section:
    Display full token URL + copy-to-clipboard button (JS)
    commit: "feat(templates): add share URL display and copy button to report detail page"
```

**Acceptance Criteria:**
- [ ] Valid token URL renders report without any login
- [ ] Invalid UUID returns 404
- [ ] Expired token returns 403 with clear message
- [ ] Shared report page has no navbar login/logout links
- [ ] Share URL is copyable from parent's report detail page

**Definition of Done:** Token URL works without login. Invalid = 404. Expired = 403. Copy button works.

---

## 💳 EPIC E8 — Payments (Stripe Stub)
**Sprint:** Sprint 3 (Days 10–12) | **LO Coverage:** LO1.1, LO2.2

---

### STORY S3.4 — Stripe Pricing Page
```yaml
id: S3.4
epic: E8
sprint: 3
priority: P0
points: 2
status: NOT_STARTED
depends_on: [S3.3]
```
**User Story:** As a parent, I can view available subscription plans and understand what each tier includes, so that I can make an informed decision about upgrading.

**Tasks:**
```
T1: payments/views.py — pricing_page_view (no auth required):
    Context: {plans: [{name, price, features, cta}, ...]}
    commit: "feat(payments): add Stripe pricing page view"

T2: templates/payments/pricing.html:
    Two-column card layout: Free tier + Pro tier
    Feature comparison lists
    "Choose Pro" CTA button → links to /payments/checkout/
    commit: "feat(templates): add pricing page with Free and Pro tier comparison cards"

T3: Add URL: path('payments/plans/', ...)
    Add pricing link to base.html navbar
    commit: "feat(payments): wire pricing page URL and add to navbar"
```

**Acceptance Criteria:**
- [ ] Accessible without login
- [ ] Free and Pro tier features clearly listed
- [ ] "Choose Pro" links to checkout
- [ ] Responsive, W3C valid

**Definition of Done:** Pricing page renders. Two tiers visible. Links to checkout.

---

### STORY S3.5 — Stripe Checkout Stub
```yaml
id: S3.5
epic: E8
sprint: 3
priority: P1
points: 3
status: NOT_STARTED
depends_on: [S3.4]
```
**User Story:** As a parent, I can click "Choose Pro" and be taken through a subscription upgrade journey, so that the payment flow is complete even if live charging is not yet active.

**Tasks:**
```
T1: Add STRIPE_ENABLED = config('STRIPE_ENABLED', cast=bool, default=False) to settings.py
    Add STRIPE_PUBLISHABLE_KEY = config('STRIPE_PUBLISHABLE_KEY', default='')
    commit: "chore: add Stripe configuration to settings with STRIPE_ENABLED feature flag"

T2: payments/views.py — checkout_view:
    @login_required @role_required('parent')
    Context: {stripe_enabled: settings.STRIPE_ENABLED, stripe_key: settings.STRIPE_PUBLISHABLE_KEY}
    commit: "feat(payments): add Stripe checkout view with STRIPE_ENABLED feature flag"

T3: templates/payments/checkout.html:
    If STRIPE_ENABLED: show Stripe.js payment form
    If not STRIPE_ENABLED: show "⚠️ Test Mode — Payments are currently disabled" banner + plan summary
    commit: "feat(templates): add checkout template with feature flag test mode banner"

T4: payments/views.py — success_view + templates/payments/success.html
    Add subscription_gate to reports/views.py:
      if not request.user.userprofile.subscription_active: redirect to pricing with message
    commit: "feat(payments): add success page and subscription gate on report generation"

T5: Add URLs: /payments/checkout/, /payments/success/
    commit: "feat(payments): wire checkout and success URLs"
```

**Acceptance Criteria:**
- [ ] STRIPE_ENABLED=False shows test mode banner (not a broken form)
- [ ] Success page exists and renders
- [ ] Subscription gate on report creation redirects unsubscribed parents to pricing
- [ ] subscription_active field settable in Django admin (for testing)

**Definition of Done:** Pricing→checkout flow complete. Feature flag works. Gate on reports.

---

## 🧪 EPIC E9 — Testing, Documentation & Final Deploy
**Sprint:** Sprint 3 (Days 10–12)  
**LO Coverage:** LO1.5, LO4.1, LO4.2, LO4.3, LO6.1, LO6.2, LO6.3, LO8.1–LO8.5

---

### STORY S3.6 — Automated Python Tests
```yaml
id: S3.6
epic: E9
sprint: 3
priority: P0
points: 5
status: NOT_STARTED
depends_on: [S3.5]
```
**User Story:** As a developer, I can run an automated test suite covering all critical paths, so that the codebase is verified and testing competency is demonstrated.

**Tasks:**
```
T1: scheduler/tests.py — 3 test cases:
    test_schedule_generates_correct_count: setUp with Child+2 subjects → call generate_schedule → assertEqual count
    test_no_weekend_lessons: assert all ScheduledLesson.scheduled_date.weekday() < 5
    test_respects_weekly_pace: assert no subject has >pace lessons in any single ISO week
    commit: "test(scheduler): add automated tests for schedule generation algorithm"

T2: tracker/tests.py — 2 test cases:
    test_lesson_log_created_on_complete: POST to update_lesson_status → assert LessonLog created with status=complete
    test_status_update: create LessonLog(status=pending) → POST skip → assert status=skipped
    commit: "test(tracker): add automated tests for lesson log status updates"

T3: accounts/tests.py — 3 test cases:
    test_registration_creates_parent_role: POST to register → assert UserProfile.role=='parent'
    test_student_blocked_from_parent_views: login as student → GET /children/ → assert 302
    test_parent_blocked_from_student_views: login as parent → GET /calendar/ → assert 302
    commit: "test(accounts): add role-based access control tests"

T4: reports/tests.py — 3 test cases:
    test_valid_token_renders_report: GET /reports/share/<valid_token>/ → assert 200
    test_invalid_token_returns_404: GET /reports/share/00000000-0000-0000-0000-000000000000/ → assert 404
    test_expired_token_returns_403: create Report with token_expires_at=yesterday → GET → assert 403
    commit: "test(reports): add share token validation tests"

T5: Run python manage.py test — confirm all 11 tests pass
    commit: "test: final test run — all 11 tests passing"
```

**Acceptance Criteria:**
- [ ] `python manage.py test` exits with 0 failures
- [ ] Minimum 11 test cases across 4 test files
- [ ] Each test file has a module-level docstring
- [ ] All tests use setUp / TestCase fixtures (no live database dependency)
- [ ] Tests cover: scheduler, tracker, accounts, reports

**Definition of Done:** All 11+ tests pass. No live DB dependency. Each file docstrung.

---

### STORY S3.7 — README: UX and Design Documentation
```yaml
id: S3.7
epic: E9
sprint: 3
priority: P0
points: 2
status: NOT_STARTED
depends_on: [S3.6]
```
**User Story:** As a developer, I can document the UX design process and design rationale in the README, so that the assessor can follow the thinking from concept to implementation. *(Satisfies LO1.5)*

**Tasks:**
```
T1: README.md — add UX Design section:
    ## UX Design
    ### Project Purpose
    ### Target User (Personas)
    ### Design Rationale (reference Syllabird inspiration)
    ### Wireframes (text descriptions or embedded images)
    ### Colour System (table of CSS variables + usage)
    ### Accessibility Decisions
    commit: "docs(readme): add UX design section with wireframes and design rationale"
```

**Acceptance Criteria:**
- [ ] UX Design section present in README
- [ ] Wireframes for: calendar, lesson modal, dashboard, subject selection
- [ ] Colour system table documents all CSS variables
- [ ] Syllabird reference and adaptation explained
- [ ] Accessibility decisions documented

**Definition of Done:** README UX section complete. Wireframes described. Colour system documented.

---

### STORY S3.8 — README: Testing Documentation
```yaml
id: S3.8
epic: E9
sprint: 3
priority: P0
points: 1
status: NOT_STARTED
depends_on: [S3.7]
```
**User Story:** As a developer, I can document all test procedures and results in the README, so that the assessor can see what was tested and the outcomes. *(Satisfies LO4.3)*

**Tasks:**
```
T1: README.md — add Testing section:
    ## Testing
    ### Automated Tests (table: test name | what it tests | result)
    ### Manual JavaScript Tests (table: scenario | steps | expected | actual | pass/fail)
    ### How to Run Tests: `python manage.py test`
    Fill in actual pass/fail results after running all tests
    commit: "docs(readme): add testing section with automated and manual test results"
```

**Acceptance Criteria:**
- [ ] Automated test table lists all 11+ tests with pass/fail
- [ ] Manual JS test table has 8+ scenarios with actual results filled in
- [ ] Test run command documented
- [ ] All results are accurate (not placeholder text)

**Definition of Done:** Testing section complete. All results filled in. Commands documented.

---

### STORY S3.9 — README: Deployment and AI Reflection
```yaml
id: S3.9
epic: E9
sprint: 3
priority: P0
points: 2
status: NOT_STARTED
depends_on: [S3.8]
```
**User Story:** As a developer, I can document the deployment process and AI tool usage in the README, so that the assessor can reproduce the deployment and see how AI contributed. *(Satisfies LO6.2, LO8.1–LO8.5)*

**Tasks:**
```
T1: README.md — add Deployment section:
    ## Deployment
    ### Prerequisites
    ### Environment Variables (reference .env.example)
    ### Step-by-step Heroku deployment (heroku create → config vars → git push → migrate → seed → createsuperuser)
    ### How to run locally
    commit: "docs(readme): add complete deployment documentation with step-by-step guide"

T2: README.md — add AI Tools section:
    ## AI Tools in Development
    ### Code Generation (LO8.1): [specific example — e.g. "Claude generated the scheduler algorithm in services.py"]
    ### Debugging (LO8.2): [specific example — e.g. "Claude identified the CSRF token missing from AJAX requests"]
    ### Optimisation (LO8.3): [specific example — e.g. "Claude suggested bulk_create for scheduler performance"]
    ### Unit Tests (LO8.4): [how Copilot/Claude generated test stubs]
    ### Workflow Reflection (LO8.5): [2–3 sentences on overall AI impact on workflow]
    (All reflections outcome-focused — no detailed prompt logs needed)
    commit: "docs(readme): add AI tools reflection covering all LO8 criteria"

T3: README.md — add Features section and final review:
    ## Features (with brief descriptions of each implemented feature)
    Review all README sections for completeness and professional tone
    commit: "docs(readme): finalise README — all sections complete"
```

**Acceptance Criteria:**
- [ ] Deployment section has complete step-by-step Heroku instructions
- [ ] AI section addresses all 5 LO8 criteria with specific examples
- [ ] Features section lists all implemented features
- [ ] README reads as professional documentation throughout

**Definition of Done:** README complete. Deployment reproducible from instructions. All LO8 points covered.

---

### STORY S3.10 — Final Production Deployment
```yaml
id: S3.10
epic: E9
sprint: 3
priority: P0
points: 2
status: NOT_STARTED
depends_on: [S3.9]
```
**User Story:** As a developer, I can perform the final production deployment with all security settings verified, so that the submitted application is fully functional, secure, and meets all deployment requirements. *(Satisfies LO6.1, LO6.3)*

**Tasks:**
```
T1: Run python manage.py test — all tests must pass before final push
    commit: "test: final test run — all tests passing before production deployment"

T2: Security audit checklist:
    [ ] .env not in git log: `git log --all --full-history -- .env` returns nothing
    [ ] DEBUG=False in Heroku config vars
    [ ] ALLOWED_HOSTS does not include '*'
    [ ] No hardcoded credentials in any file: `git grep -r "password\|secret\|api_key" -- '*.py'`
    commit: "chore: final security audit before production deployment"

T3: git push heroku main
    heroku run python manage.py migrate
    heroku open — confirm app loads
    Full smoke test (all sprint smoke tests end-to-end)
    commit: "chore: final production deployment — EduTrack v1.0"
```

**Acceptance Criteria (Final Smoke Test):**
- [ ] Register parent → add child → select subjects → generate schedule
- [ ] Create student login → student logs in → views calendar
- [ ] Student marks lesson complete with mastery + notes + file upload
- [ ] Parent views read-only calendar
- [ ] Parent generates PDF report → downloads → copies LA share URL
- [ ] LA share URL opens in incognito without login
- [ ] Stripe pricing page renders; checkout shows test mode banner
- [ ] `python manage.py test` passes locally
- [ ] DEBUG=False, no secrets in repo

**Definition of Done:** Full end-to-end smoke test passes on Heroku. All security checks pass. Tests pass.

---

## PART 4 — HANDOVER PROTOCOL

> **This section is read by the AI agent at the START of every new session.**  
> **Follow these steps in order before taking any other action.**

---

### STEP 1 — PARSE PROJECT STATE

```
READ the ## PROJECT STATE block at the top of this document.
IDENTIFY: current_sprint, current_story, current_story_status.
IF current_story_status == "DONE": advance to the next story in the backlog order.
IF current_story_status == "IN_PROGRESS": read the story, identify which tasks are complete (check git log), resume from the next incomplete task.
IF current_story_status == "NOT_STARTED": read the story's DoR checklist. If all dependencies are DONE: begin. If not: report blocked to human.
```

### STEP 2 — INITIALISE SESSION

```
ANNOUNCE to the human:
  "Session starting. Current story: [ID] — [Title]
   Status: [status]
   Next action: [first incomplete task]
   Sprint: [sprint name] | Epic: [epic name]"

ASK the human: "Confirmed? Shall I proceed with [task description]?"
WAIT for confirmation before writing any code.
```

### STEP 3 — INITIALISE PROJECT BOARD (first session only)

```
IF this is the first session (no GitHub repo URL in PROJECT STATE):
  1. Instruct human to create GitHub repo and paste URL
  2. Instruct human to create GitHub Projects board with columns:
       📋 Backlog | 🔍 In Analysis | 🛠 In Progress | 👀 In Review | ✅ Done
  3. Create 9 Milestones: E1 Foundation | E2 Auth | E3 Scheduling | E4 Calendar |
       E5 Tracking | E6 Evidence | E7 Reports | E8 Payments | E9 Testing & Deploy
  4. Create Labels: must-have | should-have | frontend | backend | devops | testing | docs |
       sprint-0 | sprint-1 | sprint-2 | sprint-3
  5. Create all 40 GitHub Issues from this document using the template below
  6. Start all issues in Backlog column
  7. Generate requirements.txt from Section 1.7 of this document
  8. Generate README.md skeleton from Section 1.4 directory structure
  9. Generate .env.example from Section 1.2 environment variables list
```

**GitHub Issue Template:**
```markdown
## User Story
As a [role], I can [action] so that [outcome].

## Acceptance Criteria
- [ ] criterion 1
- [ ] criterion 2

## Tasks
- [ ] T1: description  →  commit: "type(app): message"
- [ ] T2: description  →  commit: "type(app): message"

## Definition of Done
[story-specific DoD statement]

## LO Coverage
[LO codes]
```

### STEP 4 — EXECUTE CURRENT TASK

```
FOR each task in the current story (in order):
  1. READ the task specification fully
  2. WRITE the implementation code
  3. VERIFY: python manage.py check passes
  4. VERIFY: if template — W3C validation passes
  5. COMMIT with the exact commit message specified in the task
  6. ANNOUNCE: "Task T[N] complete. Committed: '[commit message]'"
  7. ASK: "Shall I proceed to T[N+1]: [next task description]?"
  8. WAIT for confirmation

IF a task fails (error, test failure, check failure):
  STOP immediately
  REPORT the exact error to the human
  DO NOT proceed to next task
  WAIT for resolution instructions
```

### STEP 5 — STORY COMPLETION

```
WHEN all tasks in a story are committed:
  1. RUN the Acceptance Criteria checklist (announce each item pass/fail)
  2. RUN the Definition of Done checklist
  3. IF all pass:
       - Move GitHub issue to ✅ Done column
       - Update ## PROJECT STATE block:
           current_story → next story ID
           current_story_status → NOT_STARTED
           stories_done → append completed story ID
           last_commit → paste commit hash
       - ANNOUNCE: "[STORY-ID] complete. Next story: [NEXT-ID] — [Title]"
  4. IF any AC fails:
       - Report which criterion failed
       - Fix before marking Done
       - Do NOT advance to next story
```

### STEP 6 — SPRINT END PROTOCOL

```
WHEN all stories in a sprint are marked DONE:
  1. Execute the Sprint deployment story (S0.8, S1.10, S2.12, S3.10)
  2. Run the sprint smoke test checklist from Part 3
  3. Announce all smoke test results to human
  4. Update sprint status in PROJECT STATE to DONE
  5. Update current_sprint to next sprint
  6. ANNOUNCE sprint completion summary:
       Stories completed: [N]
       Commits made: [N]
       Heroku URL: [url]
       Next sprint: [name]
```

---

## APPENDIX — STORY EXECUTION ORDER

```
Sprint 0 (Days 1–3):   S0.1 → S0.2 → S0.3 → S0.4 → S0.5 → S0.6 → S0.7 → S0.8
Sprint 1 (Days 4–6):   S1.1 → S1.2 → S1.3 → S1.4 → S1.5 → S1.6 → S1.7 → S1.8 → S1.9 → S1.10
Sprint 2 (Days 7–9):   S2.1 → S2.2 → S2.3 → S2.4 → S2.5 → S2.6 → S2.7 → S2.8 → S2.9 → S2.10 → S2.11 → S2.12
Sprint 3 (Days 10–12): S3.1 → S3.2 → S3.3 → S3.4 → S3.5 → S3.6 → S3.7 → S3.8 → S3.9 → S3.10
```

## APPENDIX — LO TRACEABILITY QUICK REFERENCE

| LO | Story IDs |
|----|-----------|
| LO1.1 | S0.7, S1.9, S2.1, S2.2, S2.3, S2.9, S3.4 |
| LO1.2 | S0.2, S0.4 |
| LO1.4 | S0.6, S1.3, S1.7 |
| LO1.5 | S3.7 |
| LO2.1 | S0.4 |
| LO2.2 | S1.5, S1.6, S1.8, S2.4, S2.5, S2.6, S2.7, S2.8, S2.9, S2.10, S2.11, S3.1, S3.2, S3.5 |
| LO2.3 | S1.8, S2.5, S2.8 |
| LO2.4 | S1.1, S1.5, S1.6, S2.7, S3.1 |
| LO3.1 | S0.5, S1.1, S1.2, S1.4, S3.3 |
| LO3.2 | S1.2 |
| LO3.3 | S1.3, S1.4, S1.9, S2.1, S2.9, S3.3 |
| LO4.1 | S3.6 |
| LO4.3 | S3.8 |
| LO5.1 | S0.1 |
| LO5.2 | S0.1, S0.2, S0.3, S0.8, S3.10 |
| LO6.1 | S0.3, S0.8, S1.10, S2.12, S3.10 |
| LO6.2 | S0.8, S3.9 |
| LO6.3 | S0.2, S0.8, S3.10 |
| LO7.1 | S0.4, S1.7 |
| LO8.1–LO8.5 | S3.9 |

---

*End of EduTrack Agent Execution Document v1.0*  
*Next action: Read PROJECT STATE → Confirm current story → Begin execution*
