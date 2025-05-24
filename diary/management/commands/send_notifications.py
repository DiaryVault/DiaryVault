from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.utils import timezone
from datetime import timedelta

from diary.models import Entry

class Command(BaseCommand):
    help = 'Send email notifications to inactive users'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Days of inactivity before sending notification'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show who would receive emails without sending'
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']

        cutoff_date = timezone.now() - timedelta(days=days)

        # Find users who haven't created entries recently
        inactive_users = User.objects.filter(
            date_joined__lt=cutoff_date
        ).exclude(
            diary_entries__created_at__gte=cutoff_date
        ).filter(email__isnull=False).exclude(email='')

        if dry_run:
            self.stdout.write(f'Would notify {inactive_users.count()} inactive users:')
            for user in inactive_users:
                last_entry = Entry.objects.filter(user=user).order_by('-created_at').first()
                last_activity = last_entry.created_at if last_entry else user.date_joined
                self.stdout.write(f'- {user.username} ({user.email}) - Last activity: {last_activity.date()}')
            return

        sent_count = 0
        for user in inactive_users:
            try:
                send_mail(
                    subject='We miss your stories at DiaryVault',
                    message=f'''Hi {user.first_name or user.username},

We noticed you haven't written in your diary recently. Your thoughts and experiences are valuable - why not capture a moment from your day?

Visit DiaryVault to continue your journaling journey.

Best regards,
The DiaryVault Team''',
                    from_email='noreply@diaryvault.com',
                    recipient_list=[user.email],
                    fail_silently=False,
                )
                sent_count += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Failed to send email to {user.username}: {str(e)}')
                )

        self.stdout.write(
            self.style.SUCCESS(f'Sent {sent_count} notification emails')
        )
