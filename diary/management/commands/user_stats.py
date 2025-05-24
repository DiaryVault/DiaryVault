from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db.models import Count, Sum
from django.utils import timezone
from datetime import timedelta

from diary.models import Entry, Journal, Tip

class Command(BaseCommand):
    help = 'Display user statistics and activity'

    def add_arguments(self, parser):
        parser.add_argument('--username', help='Show stats for specific user')
        parser.add_argument('--top', type=int, default=10, help='Number of top users to show')

    def handle(self, *args, **options):
        if options['username']:
            self.show_user_stats(options['username'])
        else:
            self.show_top_users(options['top'])

    def show_user_stats(self, username):
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'User {username} not found'))
            return

        # Basic stats
        entry_count = Entry.objects.filter(user=user).count()
        journal_count = Journal.objects.filter(author=user, is_published=True).count()

        # Recent activity
        last_7_days = timezone.now() - timedelta(days=7)
        recent_entries = Entry.objects.filter(user=user, created_at__gte=last_7_days).count()

        # Earnings
        try:
            total_earnings = Journal.objects.filter(
                author=user, is_published=True
            ).aggregate(total=Sum('total_tips'))['total'] or 0
        except:
            total_earnings = 0

        self.stdout.write(f"\n=== USER STATS: {username} ===")
        self.stdout.write(f"Email: {user.email}")
        self.stdout.write(f"Joined: {user.date_joined.strftime('%Y-%m-%d')}")
        self.stdout.write(f"Total Entries: {entry_count}")
        self.stdout.write(f"Published Journals: {journal_count}")
        self.stdout.write(f"Recent Entries (7 days): {recent_entries}")
        self.stdout.write(f"Total Earnings: ${total_earnings:.2f}")

    def show_top_users(self, count):
        self.stdout.write(f"\n=== TOP {count} USERS BY ACTIVITY ===")

        # Users with most entries
        top_writers = User.objects.annotate(
            entry_count=Count('diary_entries')
        ).filter(entry_count__gt=0).order_by('-entry_count')[:count]

        self.stdout.write("\nTOP WRITERS:")
        for i, user in enumerate(top_writers, 1):
            self.stdout.write(f"{i}. {user.username}: {user.entry_count} entries")

        # Top earning authors
        try:
            top_earners = User.objects.annotate(
                total_earnings=Sum('journals__total_tips')
            ).filter(total_earnings__gt=0).order_by('-total_earnings')[:count]

            if top_earners:
                self.stdout.write("\nTOP EARNERS:")
                for i, user in enumerate(top_earners, 1):
                    earnings = user.total_earnings or 0
                    self.stdout.write(f"{i}. {user.username}: ${earnings:.2f}")
        except:
            pass
