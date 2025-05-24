from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from diary.models import Entry, Tag, LifeChapter

class Command(BaseCommand):
    help = 'Migrate and fix user data inconsistencies'

    def add_arguments(self, parser):
        parser.add_argument('--fix-tags', action='store_true', help='Fix orphaned tags')
        parser.add_argument('--fix-chapters', action='store_true', help='Fix chapter relationships')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be fixed')

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write('DRY RUN - No changes will be made')

        if options['fix_tags']:
            self.fix_orphaned_tags(dry_run)

        if options['fix_chapters']:
            self.fix_chapter_relationships(dry_run)

    def fix_orphaned_tags(self, dry_run=False):
        # Find tags not associated with any entries
        orphaned_tags = Tag.objects.filter(entries__isnull=True)

        if orphaned_tags.exists():
            count = orphaned_tags.count()
            self.stdout.write(f'Found {count} orphaned tags')

            if not dry_run:
                orphaned_tags.delete()
                self.stdout.write(self.style.SUCCESS(f'Removed {count} orphaned tags'))

    def fix_chapter_relationships(self, dry_run=False):
        # Find entries with invalid chapter references
        invalid_entries = Entry.objects.filter(
            chapter__isnull=False
        ).exclude(
            chapter__user=models.F('user')
        )

        if invalid_entries.exists():
            count = invalid_entries.count()
            self.stdout.write(f'Found {count} entries with invalid chapter references')

            if not dry_run:
                invalid_entries.update(chapter=None)
                self.stdout.write(self.style.SUCCESS(f'Fixed {count} chapter references'))
