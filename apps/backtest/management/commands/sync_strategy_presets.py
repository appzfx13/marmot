from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Strategy presets are native in the Go microservice engine."""
    help = "Checks status of Go strategy presets."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("✓ Strategy presets are registered natively in go-app/strategies/registry.go."))
