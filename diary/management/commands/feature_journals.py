from django.core.management.base import BaseCommand
from django.db.models import Q
from diary.models import Journal

class Command(BaseCommand):
    help = 'Manage featured journals and staff picks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--feature',
            type=int,
            help='Journal ID to feature'
        )
        parser.add_argument(
            '--unfeature',
            type=int,
            help='Journal ID to unfeature'
        )
        parser.add_argument(
            '--staff-pick',
            type=int,
            help='Journal ID to make staff pick'
        )
        parser.add_argument(
            '--list-featured',
            action='store_true',
            help='List all featured journals'
        )
        parser.add_argument(
            '--auto-feature',
            action='store_true',
            help='Automatically feature top performing journals'
        )

    def handle(self, *args, **options):
        if options['feature']:
            self.feature_journal(options['feature'])

        elif options['unfeature']:
            self.unfeature_journal(options['unfeature'])

        elif options['staff_pick']:
            self.make_staff_pick(options['staff_pick'])

        elif options['list_featured']:
            self.list_featured_journals()

        elif options['auto_feature']:
            self.auto_feature_journals()

        else:
            self.stdout.write('Please specify an action. Use --help for options.')

    def feature_journal(self, journal_id):
        try:
            journal = Journal.objects.get(id=journal_id, is_published=True)
            journal.featured = True
            journal.save()
            self.stdout.write(
                self.style.SUCCESS(f'Featured journal: "{journal.title}"')
            )
        except Journal.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Journal {journal_id} not found or not published')
            )

    def unfeature_journal(self, journal_id):
        try:
            journal = Journal.objects.get(id=journal_id)
            journal.featured = False
            journal.save()
            self.stdout.write(
                self.style.SUCCESS(f'Unfeatured journal: "{journal.title}"')
            )
        except Journal.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Journal {journal_id} not found')
            )

    def make_staff_pick(self, journal_id):
        try:
            journal = Journal.objects.get(id=journal_id, is_published=True)
            if hasattr(journal, 'is_staff_pick'):
                journal.is_staff_pick = True
                journal.save()
                self.stdout.write(
                    self.style.SUCCESS(f'Made staff pick: "{journal.title}"')
                )
            else:
                self.stdout.write(
                    self.style.ERROR('Staff pick feature not available')
                )
        except Journal.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Journal {journal_id} not found or not published')
            )

    def list_featured_journals(self):
        featured = Journal.objects.filter(featured=True, is_published=True)

        if not featured.exists():
            self.stdout.write('No featured journals found')
            return

        self.stdout.write('FEATURED JOURNALS:')
        for journal in featured:
            tips = getattr(journal, 'total_tips', 0)
            views = getattr(journal, 'view_count', 0)
            self.stdout.write(f'- {journal.title} by {journal.author.username}')
            self.stdout.write(f'  Tips: ${tips:.2f}, Views: {views}')

    def auto_feature_journals(self):
        """Automatically feature top performing journals"""
        # Clear existing featured status
        Journal.objects.filter(featured=True).update(featured=False)

        # Feature top 5 journals by performance
        try:
            top_journals = Journal.objects.filter(
                is_published=True
            ).order_by('-total_tips', '-view_count')[:5]

            for journal in top_journals:
                journal.featured = True
                journal.save()

            self.stdout.write(
                self.style.SUCCESS(f'Auto-featured {len(top_journals)} top performing journals')
            )

        except Exception as e:
            # Fallback to basic ordering
            top_journals = Journal.objects.filter(
                is_published=True
            ).order_by('-created_at')[:5]

            for journal in top_journals:
                journal.featured = True
                journal.save()

            self.stdout.write(
                self.style.SUCCESS(f'Auto-featured {len(top_journals)} recent journals')
            )
