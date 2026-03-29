# EduTrack

Home Education, Evidenced.

## Database (Neon Postgres)

This project supports connecting to a Neon Postgres instance via `DATABASE_URL`.

- Add your connection string to `.env` as `DATABASE_URL=postgresql://user:pass@host:port/dbname`.
- Do NOT commit `.env` — secrets must never be stored in the repository.

To run migrations and verify connectivity:

```bash
# activate venv
source .venv/bin/activate

# run migrations
./.venv/bin/python manage.py migrate

# quick connectivity check
./.venv/bin/python scripts/check_db.py
```

If you prefer sqlite for local development, leave `DATABASE_URL` blank in `.env` and the project will fall back to `db.sqlite3`.

---

## UX Design

### Project Purpose

EduTrack is a home-education management platform for families practising structured home education. It gives parents a digital evidence trail — scheduled lessons, a student calendar view, lesson logs with mastery ratings, photo evidence uploads, and PDF progress reports — replacing paper portfolios and spreadsheet trackers.

The core problem: home-educating parents carry the administrative burden of proving educational progress to local authorities and to themselves. EduTrack makes this effortless and professional.

---

### Target Users (Personas)

| Persona | Description | Primary Goal |
|---------|-------------|--------------|
| **Parent (Alex, 38)** | Home-educating two children, previously a teacher. Wants a structured record system. | Create schedules, monitor child progress, generate PDF reports for LA review. |
| **Student (Sam, 12)** | Works independently with a weekly calendar. Wants to mark lessons as done and add notes. | View today's lessons, log completion, upload evidence photos. |

---

### Design Rationale

EduTrack's interface was inspired by **Syllabird** (syllabird.com), a US home-education planner praised for its clean weekly calendar layout and subject colour-coding. Key adaptations made for EduTrack:

- **Roles separated at login** — Syllabird uses a single parent view; EduTrack routes parents to the dashboard and students to the calendar immediately after login, reducing navigation friction.
- **Evidence layer added** — Syllabird provides lesson scheduling only; EduTrack extends this with photo uploads and mastery ratings on each lesson, creating a richer evidence trail.
- **PDF report export** — EduTrack adds a report generation and Cloudinary-hosted PDF download feature, absent from Syllabird, targeting the UK home-education compliance need.
- **Stripe subscription gate** — EduTrack introduces a freemium model (pricing page + subscription check on report generation) not present in Syllabird.

Bootstrap 5 was chosen over a custom CSS framework for rapid, accessible, mobile-responsive scaffolding. The dark navy (`#1B2A4A`) navbar and blue (`#2563EB`) primary action colour give EduTrack a professional, trustworthy feel appropriate for an education product.

---

### Wireframes

Wireframes are described in text/ASCII form below. The application implements these layouts.

#### Parent Dashboard (`/children/`)
```
┌──────────────────────────────────────────┐
│  EduTrack  [Dashboard] [Pricing] [Logout]│
├──────────────────────────────────────────┤
│  Good morning, Alex                      │
│                                          │
│  ┌──────────────┐  ┌──────────────┐      │
│  │  Sam         │  │  Lily        │      │
│  │  3/12 done   │  │  7/12 done   │      │
│  │  [View plan] │  │  [View plan] │      │
│  └──────────────┘  └──────────────┘      │
│                                          │
│  [+ Add Child]                           │
└──────────────────────────────────────────┘
```

#### Student Calendar (`/tracker/calendar/`)
```
┌──────────────────────────────────────────┐
│  EduTrack  [Calendar]  [Logout]          │
├──────────────────────────────────────────┤
│  ◀ Week 10    Mon 9 – Fri 13 Mar  ▶      │
│                                          │
│  Mon       Tue       Wed       Thu       │
│  ┌───────┐ ┌───────┐ ┌───────┐           │
│  │Maths  │ │English│ │Science│           │
│  │Lesson │ │Lesson │ │Lesson │           │
│  │[✓][→] │ │[✓][→] │ │[✓][→] │           │
│  └───────┘ └───────┘ └───────┘           │
└──────────────────────────────────────────┘
```

#### Lesson Detail Page (`/tracker/lesson/<id>/`)
```
┌────────────────────────────────┐
│  Maths — Fractions (Lesson 3)  │
│  Mon 9 Mar 2026                │
├────────────────────────────────┤
│  Status:  [Complete] [Skip]    │
│  Mastery: [🟢 Green][🟡 Amber] │
│           [🔴 Red]             │
│  Notes:   [textarea        ]   │
│  Evidence: [Upload photo]      │
│  [Save]                        │
└────────────────────────────────┘
```

#### Subject Selection (`/scheduler/<child>/subjects/`)
```
┌──────────────────────────────────────┐
│  Choose subjects for Sam             │
├──────────────────────────────────────┤
│  [✓] Maths      Lessons/week: [ 3 ]  │
│  [✓] English    Lessons/week: [ 3 ]  │
│  [ ] Science    Lessons/week: [ 2 ]  │
│  [ ] History    Lessons/week: [ 1 ]  │
│                                      │
│  [Save & Generate Schedule]          │
└──────────────────────────────────────┘
```

---

### Colour System

All colours are defined as CSS custom properties in [`static/css/custom.css`](static/css/custom.css) and referenced throughout templates via `var(--name)`.

| CSS Variable | Hex Value | Usage |
|--------------|-----------|-------|
| `--primary` | `#2563EB` | Primary buttons, links, active nav states |
| `--secondary` | `#EA580C` | Accent / call-to-action highlights |
| `--success` | `#16A34A` | "Complete" status badges, mastery green dot |
| `--warning` | `#D97706` | "Amber" mastery dot, warning alerts |
| `--danger` | `#DC2626` | "Red" mastery dot, error states, delete buttons |
| `--dark` | `#1B2A4A` | Navbar background, body text, headings |
| `--light-bg` | `#F8FAFC` | Page background colour |
| `--border` | `#E2E8F0` | Card borders, dividers, unset mastery badge |

Subject-specific colours for calendar lesson cards are assigned dynamically from a fixed 12-colour palette at schedule-generation time and stored as `colour_hex` on the `EnrolledSubject` model. This ensures each subject card has a consistent, distinct colour across the calendar view regardless of rendering order.

---

### Accessibility Decisions

| Decision | Implementation |
|----------|----------------|
| **Semantic HTML** | All pages use a correct heading hierarchy (`h1` → `h2` → `h3`). The main navigation uses `<nav>` with an `aria-label`. |
| **Keyboard navigation** | All interactive elements are native `<button>` or `<a>` tags — fully keyboard-focusable. No `div`-based click handlers are used. |
| **Colour contrast** | White text on `--dark` (#1B2A4A) and `--primary` (#2563EB) both exceed the WCAG AA 4.5:1 contrast ratio for normal text. |
| **Form labels** | Every form `<input>` has an associated `<label>`. Django's form-rendering pipeline outputs explicit label tags. |
| **Alt text** | Evidence images carry filename-derived `alt` attributes. Report-embedded images use descriptive captions. |
| **Role badges** | Parent/Student role badges use `<span class="badge">` inside labelled nav text — not standalone icon-only elements. |
| **Mobile responsive** | Bootstrap 5 grid and responsive utilities ensure the calendar, dashboard, and forms reflow correctly on screens from 320 px upward. |
| **CSRF protection** | Every POST form includes `{% csrf_token %}`, preventing cross-site request forgery and protecting user data integrity. |
