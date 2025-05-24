from django.core.management.base import BaseCommand
from diary.models import Journal

class Command(BaseCommand):
    help = 'Change the featured journal to something more delightful'

    def handle(self, *args, **options):
        # Get all published journals
        journals = Journal.objects.filter(is_published=True)

        self.stdout.write('🔍 Finding more delightful journals for featuring...\n')

        # Look for journals with positive/uplifting themes
        positive_keywords = [
            'journey', 'adventure', 'travel', 'growth', 'creative', 'art',
            'discovery', 'wellness', 'mindful', 'inspiration', 'dream',
            'wonder', 'explore', 'happiness', 'joy', 'success', 'achievement',
            'transformation', 'awakening', 'beautiful', 'amazing', 'incredible'
        ]

        # Find journals with uplifting titles or themes
        delightful_journals = []

        for journal in journals:
            title_lower = journal.title.lower()
            description_lower = journal.description.lower() if journal.description else ""

            # Check for positive keywords in title or description
            has_positive_keywords = any(keyword in title_lower or keyword in description_lower
                                     for keyword in positive_keywords)

            # Avoid heavy/dark topics
            heavy_keywords = ['addiction', 'depression', 'death', 'loss', 'trauma', 'abuse', 'divorce']
            has_heavy_keywords = any(keyword in title_lower or keyword in description_lower
                                   for keyword in heavy_keywords)

            if has_positive_keywords and not has_heavy_keywords:
                delightful_journals.append(journal)

        # Display options
        self.stdout.write('📚 Found these delightful journals:')
        for i, journal in enumerate(delightful_journals[:10], 1):
            likes = journal.likes.count() if hasattr(journal, 'likes') else 0
            views = getattr(journal, 'view_count', 0)
            entries = journal.entries.count() if hasattr(journal, 'entries') else 0

            self.stdout.write(f'\n{i}. "{journal.title}"')
            self.stdout.write(f'   by {journal.author.get_full_name() or journal.author.username}')
            self.stdout.write(f'   📊 {likes} likes, {views} views, {entries} entries')
            if journal.description:
                desc = journal.description[:100] + "..." if len(journal.description) > 100 else journal.description
                self.stdout.write(f'   📝 {desc}')

        if not delightful_journals:
            self.stdout.write('❌ No particularly delightful journals found. Showing top journals by engagement:')

            # Fall back to most engaging journals
            top_journals = sorted(journals,
                                key=lambda j: (j.likes.count() if hasattr(j, 'likes') else 0) +
                                            (getattr(j, 'view_count', 0) / 10),
                                reverse=True)[:5]

            for i, journal in enumerate(top_journals, 1):
                likes = journal.likes.count() if hasattr(journal, 'likes') else 0
                views = getattr(journal, 'view_count', 0)
                self.stdout.write(f'{i}. "{journal.title}" - {likes} likes, {views} views')

            delightful_journals = top_journals

        # Automatically feature the best one
        if delightful_journals:
            # Clear current featured status
            Journal.objects.filter(featured=True).update(featured=False, featured_rank=None)

            # Feature the top choice
            best_journal = delightful_journals[0]
            best_journal.featured = True
            best_journal.featured_rank = 1
            best_journal.save()

            self.stdout.write(f'\n🌟 Featured journal changed to:')
            self.stdout.write(f'   "{best_journal.title}"')
            self.stdout.write(f'   by {best_journal.author.get_full_name() or best_journal.author.username}')

            # Also mark it as staff pick if not already
            if hasattr(best_journal, 'is_staff_pick'):
                best_journal.is_staff_pick = True
                best_journal.save()
                self.stdout.write('   ⭐ Also marked as staff pick')

        self.stdout.write('\n✅ Done! Your marketplace now features a more delightful journal.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--journal-id',
            type=int,
            help='Specify a journal ID to feature directly'
        )
        parser.add_argument(
            '--list-only',
            action='store_true',
            help='Only list options without changing anything'
        )

    def handle(self, *args, **options):
        journal_id = options.get('journal_id')
        list_only = options.get('list_only')

        if journal_id:
            # Feature specific journal
            try:
                journal = Journal.objects.get(id=journal_id, is_published=True)

                # Clear current featured
                Journal.objects.filter(featured=True).update(featured=False, featured_rank=None)

                # Feature this one
                journal.featured = True
                journal.featured_rank = 1
                if hasattr(journal, 'is_staff_pick'):
                    journal.is_staff_pick = True
                journal.save()

                self.stdout.write(f'✅ Featured journal changed to: "{journal.title}"')
                return

            except Journal.DoesNotExist:
                self.stdout.write(f'❌ Journal with ID {journal_id} not found')
                return

        # Get all published journals
        journals = Journal.objects.filter(is_published=True)

        if not journals.exists():
            self.stdout.write('❌ No published journals found')
            return

        self.stdout.write('🔍 Finding delightful journals for featuring...\n')

        # Look for uplifting journals
        positive_keywords = [
            'journey', 'adventure', 'travel', 'growth', 'creative', 'art',
            'discovery', 'wellness', 'mindful', 'inspiration', 'dream',
            'wonder', 'explore', 'happiness', 'joy', 'success', 'achievement',
            'transformation', 'awakening', 'beautiful', 'amazing', 'incredible',
            'life', 'story', 'experience', 'reflection', 'diary', 'chronicles'
        ]

        # Find positive journals
        scored_journals = []

        for journal in journals:
            title_lower = journal.title.lower()
            description_lower = journal.description.lower() if journal.description else ""
            combined_text = f"{title_lower} {description_lower}"

            # Score based on positive keywords
            positive_score = sum(1 for keyword in positive_keywords if keyword in combined_text)

            # Avoid heavy topics
            heavy_keywords = ['addiction', 'depression', 'death', 'loss', 'trauma', 'abuse', 'divorce', 'anxiety', 'struggle']
            heavy_score = sum(1 for keyword in heavy_keywords if keyword in combined_text)

            # Engagement score
            likes = journal.likes.count() if hasattr(journal, 'likes') else 0
            views = getattr(journal, 'view_count', 0)
            entries = journal.entries.count() if hasattr(journal, 'entries') else 0
            engagement_score = likes + (views / 10) + entries

            # Overall score (higher is better)
            overall_score = positive_score + (engagement_score / 10) - (heavy_score * 2)

            if overall_score > 0:  # Only include journals with positive scores
                scored_journals.append((journal, overall_score, positive_score, engagement_score))

        # Sort by score
        scored_journals.sort(key=lambda x: x[1], reverse=True)

        # Display top options
        self.stdout.write('📚 Top delightful journal options:\n')

        for i, (journal, score, pos_score, eng_score) in enumerate(scored_journals[:8], 1):
            likes = journal.likes.count() if hasattr(journal, 'likes') else 0
            views = getattr(journal, 'view_count', 0)
            entries = journal.entries.count() if hasattr(journal, 'entries') else 0

            self.stdout.write(f'{i}. "{journal.title}"')
            self.stdout.write(f'   👤 by {journal.author.get_full_name() or journal.author.username}')
            self.stdout.write(f'   📊 {likes} likes • {views} views • {entries} entries')
            self.stdout.write(f'   🎯 Score: {score:.1f} (positivity: {pos_score}, engagement: {eng_score:.1f})')

            if journal.description:
                desc = journal.description[:120] + "..." if len(journal.description) > 120 else journal.description
                self.stdout.write(f'   📝 {desc}')

            # Show tags if available
            if hasattr(journal, 'marketplace_tags') and journal.marketplace_tags.exists():
                tags = ", ".join([tag.name for tag in journal.marketplace_tags.all()[:3]])
                self.stdout.write(f'   🏷️  {tags}')

            self.stdout.write('')

        if not scored_journals:
            self.stdout.write('❌ No particularly uplifting journals found. Showing most popular:')
            popular = journals.annotate(
                popularity=models.Count('likes') + models.F('view_count') / 10
            ).order_by('-popularity')[:3]

            for journal in popular:
                self.stdout.write(f'• "{journal.title}" by {journal.author.username}')

            scored_journals = [(j, 0, 0, 0) for j in popular]

        if not list_only and scored_journals:
            # Feature the top choice
            best_journal = scored_journals[0][0]

            # Clear current featured
            Journal.objects.filter(featured=True).update(featured=False, featured_rank=None)

            # Feature the best one
            best_journal.featured = True
            best_journal.featured_rank = 1
            if hasattr(best_journal, 'is_staff_pick'):
                best_journal.is_staff_pick = True
            best_journal.save()

            self.stdout.write('🌟 FEATURED JOURNAL UPDATED:')
            self.stdout.write(f'   "{best_journal.title}"')
            self.stdout.write(f'   by {best_journal.author.get_full_name() or best_journal.author.username}')
            self.stdout.write('   ⭐ Also marked as staff pick')

        self.stdout.write('\n✅ Done!')
