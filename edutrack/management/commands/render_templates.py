from pathlib import Path

from django.core.management.base import BaseCommand
from django.test import Client


def _sanitize_path(p: str) -> str:
    if p in ("/", ""):
        return "index.html"
    name = p.strip("/")
    name = name.replace("/", "_")
    if not name.endswith(".html"):
        name = f"{name}.html"
    return name


class Command(BaseCommand):
    help = "Render a list of site pages to static HTML files for HTML validation in CI."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            dest="output",
            default="/tmp/ci_rendered_templates",
            help="Directory to write rendered HTML files",
        )
        parser.add_argument(
            "--pages-file",
            dest="pages_file",
            default=".ci_html_pages.txt",
            help="File listing site paths (one per line) to render",
        )

    def handle(self, *args, **options):
        outdir = Path(options["output"]).expanduser()
        outdir.mkdir(parents=True, exist_ok=True)
        pages_file = Path(options["pages_file"]).resolve()

        if not pages_file.exists():
            self.stderr.write(f"Pages file not found: {pages_file}")
            return

        client = Client()

        from django.contrib.auth.models import User

        user, created = User.objects.get_or_create(
            username="ci_test", email="ci@example.com"
        )
        if created:
            user.set_password("testpass")
            user.save()
        from accounts.models import UserProfile, ParentSettings

        profile, _ = UserProfile.objects.get_or_create(user=user)
        ParentSettings.objects.get_or_create(user_profile=profile)
        client.force_login(user)

        paths = []
        with pages_file.open("r", encoding="utf8") as fh:
            for l in fh:
                s = l.strip()
                if not s or s.startswith("#"):
                    continue
                paths.append(s)

        for path in paths:
            self.stdout.write(f"Rendering: {path}")
            resp = client.get(path)
            if resp.status_code != 200:
                self.stderr.write(f"Warning: GET {path} returned {resp.status_code}")
                if (
                    not resp.content
                    or b"<title>Page not found</title>" in resp.content
                    or resp.status_code in (301, 302)
                ):
                    self.stderr.write(
                        f"Skipping writing file for {path} due to error/redirect"
                    )
                    continue
            filename = _sanitize_path(path)
            target = outdir / filename
            target.write_bytes(resp.content)
            self.stdout.write(f"Wrote: {target}")
