from django.core.management.base import BaseCommand

from data.seeding.seeder import seed


class Command(BaseCommand):
    help = "Попълва базата с демо данни (ако е празна)."

    def handle(self, *args, **options):
        self.stdout.write("Демо данните са създадени." if seed() else "Базата вече има данни - пропуснато.")
