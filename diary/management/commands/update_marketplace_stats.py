from django.core.management.base import BaseCommand
from django.db.models import Count, Sum, Avg
from diary.models import Journal, JournalLike, Tip

class Command(BaseCommand):
    help = 'Update marketplace statistics and popularity scores'

    def handle(self, *args, **options):
        self.stdout.write('Updating marketplace statistics...')

        updated_count = 0

        # Update all published journals
        for journal in Journal.objects.filter(is_published=True):
            try:
                # Update cached counts
                if hasattr(journal, 'update_cached_counts'):
                    journal.update_cached_counts()

                # Calculate popularity score
                if hasattr(journal, 'calculate_popularity'):
                    journal.calculate_popularity()

                updated_count += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error updating journal {journal.id}: {str(e)}')
                )

        self.stdout.write(
            self.style.SUCCESS(f'Successfully updated {updated_count} journals')
        )
