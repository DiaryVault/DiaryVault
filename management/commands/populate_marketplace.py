# management/commands/populate_marketplace.py
import random
import lorem
from datetime import datetime, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.text import slugify
from diary.models import (
    Journal, JournalTag, JournalEntry, JournalLike,
    JournalPurchase, JournalReview, Tip, Entry
)

class Command(BaseCommand):
    help = 'Populate the marketplace with realistic journal data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--users',
            type=int,
            default=50,
            help='Number of users to create'
        )
        parser.add_argument(
            '--journals',
            type=int,
            default=100,
            help='Number of journals to create'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing marketplace data before creating new'
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing marketplace data...')
            self.clear_data()

        self.stdout.write('Creating journal categories...')
        self.create_categories()

        self.stdout.write(f'Creating {options["users"]} users...')
        self.create_users(options['users'])

        self.stdout.write(f'Creating {options["journals"]} journals...')
        self.create_journals(options['journals'])

        self.stdout.write('Creating journal interactions...')
        self.create_interactions()

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully populated marketplace with {options["journals"]} journals!'
            )
        )

    def clear_data(self):
        """Clear existing marketplace data"""
        JournalReview.objects.all().delete()
        JournalPurchase.objects.all().delete()
        JournalLike.objects.all().delete()
        Tip.objects.all().delete()
        JournalEntry.objects.all().delete()
        Journal.objects.all().delete()
        JournalTag.objects.all().delete()
        # Don't delete users as they might have other data

    def create_categories(self):
        """Create journal categories"""
        categories = [
            ('travel', 'Travel & Adventure', 'Journeys, adventures, and travel experiences'),
            ('mindfulness', 'Mindfulness & Wellness', 'Meditation, self-care, and mental health'),
            ('creativity', 'Creative Writing', 'Fiction, poetry, and creative expression'),
            ('personal-growth', 'Personal Growth', 'Self-improvement and life lessons'),
            ('food', 'Food & Cooking', 'Recipes, dining experiences, and culinary adventures'),
            ('relationships', 'Relationships', 'Love, friendship, and human connections'),
            ('career', 'Career & Business', 'Professional growth and entrepreneurship'),
            ('parenting', 'Parenting & Family', 'Family life and raising children'),
            ('education', 'Learning & Education', 'Academic pursuits and knowledge sharing'),
            ('health', 'Health & Fitness', 'Physical wellness and fitness journeys'),
            ('technology', 'Technology', 'Digital life and tech experiences'),
            ('nature', 'Nature & Environment', 'Outdoor adventures and environmental awareness'),
            ('spirituality', 'Spirituality', 'Faith, spirituality, and philosophical reflections'),
            ('arts', 'Arts & Culture', 'Music, art, literature, and cultural experiences'),
            ('lifestyle', 'Lifestyle', 'Daily life and personal interests')
        ]

        for slug, name, description in categories:
            tag, created = JournalTag.objects.get_or_create(
                slug=slug,
                defaults={
                    'name': name,
                    'description': description,
                    'color': random.choice(['blue', 'green', 'purple', 'red', 'yellow', 'indigo'])
                }
            )
            if created:
                self.stdout.write(f'Created category: {name}')

    def create_users(self, count):
        """Create realistic user accounts"""
        # Common first and last names for realistic usernames
        first_names = [
            'Emma', 'Liam', 'Olivia', 'Noah', 'Ava', 'Ethan', 'Sophia', 'Mason',
            'Isabella', 'William', 'Mia', 'James', 'Charlotte', 'Benjamin', 'Amelia',
            'Lucas', 'Harper', 'Henry', 'Evelyn', 'Alexander', 'Abigail', 'Michael',
            'Emily', 'Daniel', 'Elizabeth', 'Matthew', 'Sofia', 'Aiden', 'Avery',
            'Jackson', 'Ella', 'Sebastian', 'Madison', 'David', 'Scarlett', 'Carter',
            'Victoria', 'Wyatt', 'Aria', 'Jayden', 'Grace', 'John', 'Chloe', 'Owen',
            'Camila', 'Dylan', 'Penelope', 'Luke', 'Riley'
        ]

        last_names = [
            'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller',
            'Davis', 'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez',
            'Wilson', 'Anderson', 'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin',
            'Lee', 'Perez', 'Thompson', 'White', 'Harris', 'Sanchez', 'Clark',
            'Ramirez', 'Lewis', 'Robinson', 'Walker', 'Young', 'Allen', 'King',
            'Wright', 'Scott', 'Torres', 'Nguyen', 'Hill', 'Flores', 'Green',
            'Adams', 'Nelson', 'Baker', 'Hall', 'Rivera', 'Campbell', 'Mitchell',
            'Carter', 'Roberts'
        ]

        created_users = []
        for i in range(count):
            first_name = random.choice(first_names)
            last_name = random.choice(last_names)
            username = f"{first_name.lower()}{last_name.lower()}{random.randint(1, 999)}"
            email = f"{username}@example.com"

            # Ensure unique username
            counter = 1
            original_username = username
            while User.objects.filter(username=username).exists():
                username = f"{original_username}{counter}"
                counter += 1

            user = User.objects.create_user(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                password='testpass123'
            )
            created_users.append(user)

        self.stdout.write(f'Created {len(created_users)} users')
        return created_users

    def create_journals(self, count):
        """Create realistic journals with entries"""
        users = list(User.objects.all())
        categories = list(JournalTag.objects.all())

        if not users:
            self.stdout.write(self.style.ERROR('No users found. Create users first.'))
            return

        # Journal title templates by category
        title_templates = {
            'travel': [
                "My {year} European Adventure",
                "Backpacking Through {destination}",
                "Solo Travel Chronicles: {destination}",
                "Road Trip Across {destination}",
                "Digital Nomad Life in {destination}",
                "{days} Days in {destination}",
                "Cultural Immersion: Living in {destination}",
                "The {destination} Experience"
            ],
            'mindfulness': [
                "My Meditation Journey",
                "Finding Inner Peace: A {year} Reflection",
                "Mindful Living in {year}",
                "The Path to Self-Discovery",
                "Daily Gratitude Practice",
                "Healing Through Mindfulness",
                "My Mental Health Journey",
                "Zen and the Art of Living"
            ],
            'creativity': [
                "The Writer's Block Chronicles",
                "My Creative Renaissance",
                "Art, Life, and Everything Between",
                "Poetry from the Heart",
                "The Creative Process Unveiled",
                "Stories from My Imagination",
                "Finding My Voice",
                "Creative Chaos: My {year} Journey"
            ],
            'personal-growth': [
                "Becoming My Best Self",
                "Life Lessons at {age}",
                "The Growth Mindset Journey",
                "Personal Revolution: My {year}",
                "Learning to Love Myself",
                "The Courage to Change",
                "My Transformation Story",
                "Rising from the Ashes"
            ]
        }

        destinations = ['Thailand', 'Japan', 'Italy', 'Iceland', 'Peru', 'Morocco', 'New Zealand', 'France', 'Greece', 'Nepal']

        created_journals = []
        for i in range(count):
            author = random.choice(users)
            category = random.choice(categories)

            # Select title template based on category
            templates = title_templates.get(category.slug, [
                "My {year} Journal",
                "Daily Reflections",
                "Life Chronicles",
                "Personal Thoughts",
                "My Story"
            ])

            title_template = random.choice(templates)
            title = title_template.format(
                year=random.randint(2020, 2024),
                destination=random.choice(destinations),
                age=random.randint(18, 65),
                days=random.choice([7, 14, 21, 30, 60, 90])
            )

            # Generate description based on category
            description = self.generate_description(category.slug, title)

            # Determine if journal is premium
            is_premium = random.choice([True, False, False, False])  # 25% premium
            price = Decimal(str(round(random.uniform(2.99, 29.99), 2))) if is_premium else Decimal('0.00')

            # Create journal
            journal = Journal.objects.create(
                title=title,
                description=description,
                author=author,
                price=price,
                is_published=True,
                date_published=timezone.now() - timedelta(days=random.randint(1, 365)),
                is_staff_pick=random.choice([True] + [False] * 9),  # 10% staff picks
                view_count=random.randint(10, 5000),
                total_tips=Decimal(str(random.randint(0, 500))),
                privacy_setting='public'
            )

            # Add category tags
            journal.marketplace_tags.add(category)

            # Add additional random tags
            additional_tags = random.sample(categories, random.randint(0, 2))
            for tag in additional_tags:
                journal.marketplace_tags.add(tag)

            # Create journal entries
            self.create_journal_entries(journal, category.slug)

            created_journals.append(journal)

        self.stdout.write(f'Created {len(created_journals)} journals')
        return created_journals

    def generate_description(self, category_slug, title):
        """Generate realistic descriptions based on category"""
        descriptions = {
            'travel': [
                "Join me on an incredible journey through breathtaking landscapes and vibrant cultures. This journal captures authentic moments, local encounters, and personal reflections from my travels.",
                "An honest account of solo adventures, cultural discoveries, and life-changing experiences. Includes practical tips, hidden gems, and personal growth insights.",
                "Travel through my eyes as I document unforgettable experiences, meet fascinating people, and discover the beauty of our world. Perfect for fellow wanderers and dreamers."
            ],
            'mindfulness': [
                "A deeply personal exploration of mindfulness practices, meditation insights, and the journey toward inner peace. Discover practical techniques and honest reflections.",
                "My authentic journey through mental health challenges and triumphs. Sharing practices that brought clarity, peace, and self-compassion into my daily life.",
                "Daily mindfulness practices, gratitude exercises, and reflections on finding balance in a chaotic world. A guide to peaceful living."
            ],
            'creativity': [
                "Raw, unfiltered creative expression through poetry, short stories, and artistic reflections. A window into the creative mind and process.",
                "The ups and downs of creative life, from inspiration to creative blocks and breakthrough moments. Honest insights into the artistic journey.",
                "Original creative works paired with reflections on the creative process, inspiration, and the role of art in daily life."
            ],
            'personal-growth': [
                "An honest account of personal transformation, life lessons learned, and the ongoing journey of self-discovery and growth.",
                "Real stories of overcoming challenges, building resilience, and creating positive change. Insights and inspiration for anyone on their own growth journey.",
                "Personal reflections on life changes, career transitions, relationship growth, and the continuous process of becoming who we're meant to be."
            ]
        }

        category_descriptions = descriptions.get(category_slug, [
            "Personal reflections and experiences shared with honesty and authenticity. Real stories from real life.",
            "An intimate look into daily thoughts, experiences, and life lessons. Perfect for anyone seeking genuine human connection.",
            "Heartfelt writing about life's journey, challenges, and victories. Authentic storytelling at its finest."
        ])

        return random.choice(category_descriptions)

    def create_journal_entries(self, journal, category_slug):
        """Create realistic entries for a journal"""
        entry_count = random.randint(5, 50)

        # Entry content templates by category
        content_templates = {
            'travel': [
                "Today I explored the bustling markets of the city center. The colors, sounds, and smells were overwhelming in the best possible way. I tried local street food and had conversations with vendors who shared stories about their families and traditions. It's moments like these that remind me why I love traveling - it's not just about the places, but the people you meet along the way.",
                "Woke up early to catch the sunrise from the mountain peak. The hike was challenging, but the view was absolutely worth it. There's something magical about watching the world wake up from such a high vantage point. I sat there for an hour, just breathing and taking it all in. These quiet moments of solitude are precious.",
                "Had an unexpected adventure today when I missed my bus and ended up in a small village I'd never heard of. Sometimes the best experiences come from things not going according to plan. The locals were incredibly welcoming and I ended up staying for dinner with a family who spoke no English. We communicated through smiles, gestures, and shared laughter."
            ],
            'mindfulness': [
                "This morning's meditation was particularly powerful. I focused on breath awareness and noticed how my mind kept wandering to tomorrow's to-do list. Instead of fighting it, I practiced gentle redirection. It's becoming easier to observe my thoughts without judgment. The practice is slowly changing how I respond to stress in daily life.",
                "Practiced walking meditation in the park today. Each step was intentional, each breath conscious. I noticed the texture of the path under my feet, the sound of leaves rustling, the warmth of sunlight on my face. These simple moments of presence are transforming my relationship with the world around me.",
                "Reflecting on the concept of impermanence today. Everything changes - our thoughts, emotions, circumstances. This realization brings both comfort and urgency. Comfort in knowing difficult times will pass, urgency in appreciating beautiful moments while they're here."
            ],
            'creativity': [
                "Started a new piece today inspired by the morning light streaming through my window. There's something about that golden hour that makes everything feel possible. The blank canvas felt intimidating at first, but once I made the first mark, the creative energy began to flow. Art has this way of surprising me with what emerges.",
                "Writer's block hit hard today. Sat at my desk for two hours with nothing meaningful appearing on the page. Sometimes the creative process involves these dry spells. I reminded myself that not every day will be productive, and that's okay. Tomorrow I'll try again with fresh eyes and an open heart.",
                "Had a breakthrough moment while working on my poetry collection. The piece I'd been struggling with for weeks suddenly clicked. It's fascinating how the subconscious mind works on problems even when we're not actively thinking about them. The patience required for creative work is both challenging and rewarding."
            ]
        }

        default_content = [
            "Today was one of those days that reminded me why I keep this journal. Life has a way of surprising us when we least expect it.",
            "Reflecting on recent events and how they've shaped my perspective. Growth often comes from the most unexpected places.",
            "Sometimes the most ordinary days hold the most extraordinary moments. Today was proof of that.",
            "Had an interesting conversation that got me thinking about life, purpose, and what really matters.",
            "The weather matched my mood perfectly today. There's something comforting about when the external world mirrors our internal state."
        ]

        templates = content_templates.get(category_slug, default_content)

        for i in range(entry_count):
            entry_date = journal.date_published + timedelta(days=i)

            # Create diverse entry titles
            titles = [
                f"Day {i+1}: New Discoveries",
                f"Week {(i//7)+1} Reflections",
                f"Morning Thoughts - {entry_date.strftime('%B %d')}",
                f"Evening Reflection",
                f"Unexpected Moments",
                f"Learning and Growing",
                f"Daily Observations",
                f"Personal Insights"
            ]

            content = random.choice(templates)
            # Add some variety to content length
            if random.choice([True, False, False]):  # 33% chance of longer content
                content += "\n\n" + lorem.paragraph()

            JournalEntry.objects.create(
                journal=journal,
                title=random.choice(titles),
                content=content,
                entry_date=entry_date.date(),
                is_included=True
            )

        # Update cached counts
        journal.entry_count_cached = entry_count
        journal.save(update_fields=['entry_count_cached'])

    def create_interactions(self):
        """Create likes, reviews, purchases, and tips"""
        journals = list(Journal.objects.all())
        users = list(User.objects.all())

        if not journals or not users:
            return

        # Create likes
        for journal in journals:
            # Each journal gets 0-100 likes
            like_count = random.randint(0, 100)
            likers = random.sample(users, min(like_count, len(users)))

            for user in likers:
                if user != journal.author:  # Don't let authors like their own journals
                    JournalLike.objects.get_or_create(
                        user=user,
                        journal=journal
                    )

        # Create purchases for premium journals
        premium_journals = [j for j in journals if j.price > 0]
        for journal in premium_journals:
            # Each premium journal gets 0-50 purchases
            purchase_count = random.randint(0, 50)
            buyers = random.sample(users, min(purchase_count, len(users)))

            for user in buyers:
                if user != journal.author:
                    JournalPurchase.objects.get_or_create(
                        user=user,
                        journal=journal,
                        defaults={'amount': journal.price}
                    )

        # Create reviews
        for journal in journals:
            # Each journal gets 0-20 reviews
            review_count = random.randint(0, 20)
            reviewers = random.sample(users, min(review_count, len(users)))

            for user in reviewers:
                if user != journal.author:
                    rating = random.choices(
                        [1, 2, 3, 4, 5],
                        weights=[5, 10, 20, 35, 30]  # Skewed toward positive reviews
                    )[0]

                    review_texts = {
                        5: ["Amazing journal! Really inspiring and well-written.", "Absolutely loved this. Couldn't put it down!", "Beautiful writing and authentic storytelling."],
                        4: ["Really enjoyed this journal. Great insights.", "Well-written and engaging. Highly recommend.", "Good read with valuable perspectives."],
                        3: ["Decent journal. Some interesting parts.", "It was okay. Had its moments.", "Average read but still worthwhile."],
                        2: ["Not my cup of tea but might appeal to others.", "Had potential but didn't quite deliver.", "Struggled to connect with this one."],
                        1: ["Disappointing. Expected more.", "Couldn't get into it.", "Not what I was hoping for."]
                    }

                    JournalReview.objects.get_or_create(
                        user=user,
                        journal=journal,
                        defaults={
                            'rating': rating,
                            'review_text': random.choice(review_texts[rating])
                        }
                    )

        # Create tips
        for journal in journals:
            # Each journal gets 0-10 tips
            tip_count = random.randint(0, 10)
            tippers = random.sample(users, min(tip_count, len(users)))

            for user in tippers:
                if user != journal.author:
                    tip_amounts = [1.00, 2.00, 3.00, 5.00, 10.00, 20.00]
                    amount = Decimal(str(random.choice(tip_amounts)))

                    Tip.objects.create(
                        journal=journal,
                        tipper=user,
                        recipient=journal.author,
                        amount=amount
                    )

        # Update journal statistics
        for journal in journals:
            journal.update_cached_counts()
            journal.calculate_popularity()

        self.stdout.write('Created interactions (likes, reviews, purchases, tips)')


# management/commands/create_sample_users.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from diary.models import Entry, Tag, LifeChapter
import random
from datetime import datetime, timedelta
from django.utils import timezone

class Command(BaseCommand):
    help = 'Create sample users with diary entries for marketplace testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=10,
            help='Number of sample users to create'
        )

    def handle(self, *args, **options):
        self.stdout.write('Creating sample users with diary entries...')

        # Sample user data
        user_profiles = [
            ('sarah_traveler', 'Sarah', 'Johnson', 'Avid traveler and digital nomad'),
            ('mindful_mike', 'Michael', 'Chen', 'Meditation teacher and wellness coach'),
            ('creative_kate', 'Katherine', 'Williams', 'Artist and creative writer'),
            ('fitness_fred', 'Frederick', 'Davis', 'Personal trainer and fitness enthusiast'),
            ('foodie_anna', 'Anna', 'Rodriguez', 'Chef and food blogger'),
            ('tech_tom', 'Thomas', 'Anderson', 'Software developer and tech enthusiast'),
            ('nature_nina', 'Nina', 'Thompson', 'Environmental scientist and nature lover'),
            ('bookworm_ben', 'Benjamin', 'Wilson', 'Literature professor and book reviewer'),
            ('yoga_yuki', 'Yuki', 'Tanaka', 'Yoga instructor and mindfulness practitioner'),
            ('adventure_alex', 'Alexander', 'Brown', 'Rock climber and adventure sports enthusiast')
        ]

        created_users = []
        for i in range(min(options['count'], len(user_profiles))):
            username, first_name, last_name, bio = user_profiles[i]

            # Create user if doesn't exist
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': f'{username}@example.com',
                    'first_name': first_name,
                    'last_name': last_name,
                    'password': 'pbkdf2_sha256$600000$test$test'  # "testpass123"
                }
            )

            if created:
                # Create life chapters for user
                self.create_life_chapters(user)

                # Create diary entries
                self.create_diary_entries(user, bio)

                created_users.append(user)
                self.stdout.write(f'Created user: {username}')

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully created {len(created_users)} sample users with diary entries!'
            )
        )

    def create_life_chapters(self, user):
        """Create life chapters for a user"""
        chapters = [
            ('Early Life', 'Childhood and teenage years', 'blue'),
            ('Education', 'College and learning years', 'green'),
            ('Career', 'Professional development and work life', 'purple'),
            ('Personal Growth', 'Self-discovery and development', 'amber'),
            ('Current Life', 'Present day experiences', 'indigo')
        ]

        for title, description, color in chapters:
            LifeChapter.objects.get_or_create(
                user=user,
                title=title,
                defaults={
                    'description': description,
                    'color': color,
                    'start_date': timezone.now().date() - timedelta(days=random.randint(365, 3650))
                }
            )

    def create_diary_entries(self, user, bio):
        """Create diary entries for a user"""
        chapters = list(LifeChapter.objects.filter(user=user))

        # Entry templates based on user type
        entry_templates = {
            'traveler': [
                "Today I explored a new city and discovered hidden gems off the beaten path.",
                "Reflecting on my journey through Southeast Asia and the people I've met.",
                "Travel has taught me so much about myself and the world around us.",
                "Sometimes the best adventures happen when you least expect them."
            ],
            'mindful': [
                "My morning meditation brought such clarity to my thoughts today.",
                "Practicing mindfulness in daily activities is transforming my perspective.",
                "Gratitude practice: Today I'm thankful for simple moments of peace.",
                "Learning to be present has been the greatest gift I've given myself."
            ],
            'creative': [
                "Inspiration struck while walking through the art museum today.",
                "Working on a new piece that explores themes of identity and belonging.",
                "The creative process is messy, beautiful, and endlessly surprising.",
                "Every blank canvas is a possibility waiting to be explored."
            ],
            'fitness': [
                "Pushed myself to a new personal record in today's workout.",
                "The mind-body connection during exercise never ceases to amaze me.",
                "Rest days are just as important as training days for overall wellness.",
                "Helping clients achieve their fitness goals brings me so much joy."
            ]
        }

        # Determine user type from username
        user_type = 'mindful' if 'mindful' in user.username else \
                   'traveler' if 'travel' in user.username else \
                   'creative' if 'creative' in user.username else \
                   'fitness' if 'fitness' in user.username else 'mindful'

        templates = entry_templates.get(user_type, entry_templates['mindful'])

        # Create 10-30 entries per user
        entry_count = random.randint(10, 30)

        for i in range(entry_count):
            # Create entry date (spread over last year)
            entry_date = timezone.now() - timedelta(days=random.randint(1, 365))

            # Select random chapter
            chapter = random.choice(chapters) if chapters else None

            # Create entry
            entry = Entry.objects.create(
                user=user,
                title=f"Daily Reflection #{i+1}",
                content=random.choice(templates),
                created_at=entry_date,
                mood=random.choice(['happy', 'reflective', 'excited', 'peaceful', 'grateful']),
                chapter=chapter
            )

            # Add tags
            self.create_tags_for_entry(entry, user_type)

    def create_tags_for_entry(self, entry, user_type):
        """Create relevant tags for an entry"""
        tag_sets = {
            'traveler': ['travel', 'adventure', 'culture', 'exploration', 'journey'],
            'mindful': ['mindfulness', 'meditation', 'gratitude', 'peace', 'wellness'],
            'creative': ['art', 'creativity', 'inspiration', 'writing', 'expression'],
            'fitness': ['fitness', 'health', 'training', 'wellness', 'strength']
        }

        tags = tag_sets.get(user_type, ['reflection', 'personal', 'growth'])
        selected_tags = random.sample(tags, random.randint(1, 3))

        for tag_name in selected_tags:
            tag, created = Tag.objects.get_or_create(
                name=tag_name,
                user=entry.user
            )
            entry.tags.add(tag)
