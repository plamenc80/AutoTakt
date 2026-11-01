from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Една команда за пускане: базата се създава/обновява и попълва автоматично."""

    help = "Създава/обновява базата, попълва демо данни и пуска сървъра."

    def add_arguments(self, parser):
        parser.add_argument("address", nargs="?", default="127.0.0.1:8000")

    def handle(self, *args, address, **options):
        call_command("migrate", interactive=False, verbosity=0)
        call_command("seed")
        # insecure - дизайнът (static) се отдава и без режим за разработка;
        # use_reloader=False - един процес (по-надеждно спиране, особено под Windows).
        call_command("runserver", address, insecure=True, use_reloader=False)
