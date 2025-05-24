from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from diary.models import Journal, JournalLike, Tip

class Command(BaseCommand):
    help = 'Clean up marketplace data and fix inconsistencies'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned without making changes'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write('DRY RUN - No changes will be made')

        self.stdout.write('Starting marketplace cleanup...')

        # Fix journals without publication dates
        journals_without_dates = Journal.objects.filter(
            is_published=True,
            date_published__isnull=True
        )

        if journals_without_dates.exists():
            count = journals_without_dates.count()
            self.stdout.write(f'Found {count} published journals without publication dates')

            if not dry_run:
                for journal in journals_without_dates:
                    journal.date_published = journal.created_at
                    journal.save(update_fields=['date_published'])

                self.stdout.write(self.style.SUCCESS(f'Fixed {count} journal publication dates'))

        # Remove duplicate likes
        duplicate_likes = []
        seen_combinations = set()

        for like in JournalLike.objects.all():
            combination = (like.user_id, like.journal_id)
            if combination in seen_combinations:
                duplicate_likes.append(like.id)
            else:
                seen_combinations.add(combination)

        if duplicate_likes:
            count = len(duplicate_likes)
            self.stdout.write(f'Found {count} duplicate likes')

            if not dry_run:
                JournalLike.objects.filter(id__in=duplicate_likes).delete()
                self.stdout.write(self.style.SUCCESS(f'Removed {count} duplicate likes'))

        # Update journal statistics
        journals_to_update = Journal.objects.filter(is_published=True)

        if not dry_run:
            updated_count = 0
            for journal in journals_to_update:
                try:
                    if hasattr(journal, 'update_cached_counts'):
                        journal.update_cached_counts()
                        updated_count += 1
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'Error updating journal {journal.id}: {str(e)}')
                    )

            self.stdout.write(self.style.SUCCESS(f'Updated statistics for {updated_count} journals'))

        self.stdout.write(self.style.SUCCESS('Marketplace cleanup completed'))
