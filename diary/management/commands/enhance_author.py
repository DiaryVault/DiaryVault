from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from diary.models import Biography
from django.utils import timezone
from datetime import timedelta
import random

class Command(BaseCommand):
    help = 'Enhance author profiles with realistic bios and stats'

    def handle(self, *args, **options):
        sample_users = User.objects.filter(username__startswith='sample_user')

        author_bios = [
            {
                'title': 'Digital Nomad & Storyteller',
                'content': 'Sarah has been documenting her journey as a digital nomad for the past 3 years, traveling to over 25 countries while building her freelance writing career. Her authentic stories about the ups and downs of remote work and solo travel have inspired thousands of readers to pursue their own adventures.',
                'specialties': 'travel, remote work, personal growth'
            },
            {
                'title': 'Mindfulness Practitioner & Life Coach',
                'content': 'Michael discovered meditation during a particularly stressful period in his corporate career. Now a certified mindfulness coach, he shares daily insights about finding peace in chaos and building sustainable wellness habits. His practical approach to mindfulness has helped hundreds of people transform their daily routines.',
                'specialties': 'mindfulness, wellness, stress management'
            },
            {
                'title': 'Working Parent & Family Advocate',
                'content': 'Emma juggles a full-time marketing career with raising two young children. Her honest reflections about modern parenthood, work-life balance, and family dynamics resonate with parents everywhere. She believes in the power of vulnerability and authentic storytelling to build community.',
                'specialties': 'parenting, work-life balance, family life'
            }
        ]

        for i, user in enumerate(sample_users[:len(author_bios)]):
            bio_data = author_bios[i]

            # Update user profile
            user.first_name = ['Sarah', 'Michael', 'Emma'][i]
            user.last_name = ['Mitchell', 'Chen', 'Rodriguez'][i]
            user.save()

            # Create or update biography
            biography, created = Biography.objects.get_or_create(
                user=user,
                defaults={
                    'title': bio_data['title'],
                    'content': bio_data['content'],
                    'time_period_start': timezone.now().date() - timedelta(days=365),
                    'time_period_end': timezone.now().date()
                }
            )

            if created:
                self.stdout.write(f'Created biography for {user.first_name} {user.last_name}')

        self.stdout.write(self.style.SUCCESS('Enhanced author profiles!'))
