# Oak Homeschooling Planner — Landing Page

A fully self-contained static landing page for the Oak Homeschooling Planner product. Inside this repository it is the canonical logged-out homepage for the Django app, while still being structured so it can be extracted into its own standalone repository later with minimal changes.

## Structure

```
landing/
  index.html              # Complete landing page (13 sections)
  assets/
    css/styles.css        # All styles — CSS custom properties, mobile-first
    js/main.js            # Sticky nav, smooth scroll, FAQ accordion, mobile menu
    images/               # Brand assets (logo, icon)
  README.md               # This file
```

## Serving locally (within Django)

From the project root:

```bash
python manage.py runserver
```

Visit `http://localhost:8000/` while logged out. The landing page is served as raw HTML via `edutrack/urls.py`. Static assets are served from `/static/landing/...` via Django's development server.

Authenticated parent and student users are redirected away from `/` to the in-app assignments home at `/home/`.

## Routing notes

- `landing/index.html` is the source of truth for the public marketing page.
- `edutrack/urls.py` serves that file directly for anonymous visits to `/`.
- `templates/home.html` is a legacy placeholder template and is no longer used by the root route.

## Serving standalone (outside Django)

1. **Adjust asset paths** — In `index.html`, replace all occurrences of `/static/landing/` with `./assets/`:

   ```bash
   sed -i '' 's|/static/landing/|./assets/|g' index.html
   ```

2. **Serve with any static server:**

   ```bash
   # Python
   cd landing && python -m http.server 8080

   # Node
   npx serve landing

   # Or deploy to any static hosting (Netlify, Vercel, Cloudflare Pages, etc.)
   ```

3. **Update CTA links** — The page links to `/accounts/register/` and `/accounts/login/`. Update these to point to the live application URL when deploying separately.

## CTA links

All call-to-action buttons in `landing/index.html` point to live application routes:

| Action     | Path                   |
|------------|------------------------|
| Sign up    | `/accounts/register/`  |
| Log in     | `/accounts/login/`     |

Anchor navigation used by the landing page points to in-page sections such as `#features`, `#how-it-works`, `#pricing`, `#faq`, and `#footer-disclaimer`.

When separating from the main repository, update these to absolute URLs pointing at the application (e.g. `https://app.example.com/accounts/register/`).

## Brand assets

The repository currently uses these image assets:

- `app_logo.jpeg` — Wordmark logo used in the nav bar and footer
- `app_icon.jpeg` — App icon used as the favicon

## Dependencies

None. Plain HTML, CSS, and vanilla JavaScript. No build step required.
