import subprocess
import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Dev convenience: runs the Django dev server, Celery worker, and "
        "Celery beat together in one command. NOT for production -- this "
        "is a stand-in for `docker compose up` until Docker Compose is "
        "added at the end of the project."
    )

    def handle(self, *args, **options):
        commands = [
            [sys.executable, "manage.py", "runserver"],
            ["celery", "-A", "config", "worker", "-l", "info"],
            ["celery", "-A", "config", "beat", "-l", "info"],
        ]
        processes = [subprocess.Popen(cmd) for cmd in commands]
        self.stdout.write(
            self.style.SUCCESS("Started server, worker, and beat. Ctrl+C to stop all three.")
        )
        try:
            for process in processes:
                process.wait()
        except KeyboardInterrupt:
            self.stdout.write("\nStopping...")
            for process in processes:
                process.terminate()