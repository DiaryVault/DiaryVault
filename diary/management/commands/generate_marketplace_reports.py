from django.core.management.base import BaseCommand
from django.db.models import Count, Sum, Avg
from django.utils import timezone
from datetime import timedelta
import json

from diary.models import Journal, User, JournalPurchase, Tip

class Command(BaseCommand):
    help = 'Generate marketplace analytics reports'

    def add_arguments(self, parser):
        parser.add_argument(
            '--format',
            choices=['json', 'text'],
            default='text',
            help='Output format'
        )
        parser.add_argument(
            '--output',
            help='Output file path'
        )

    def handle(self, *args, **options):
        self.stdout.write('Generating marketplace analytics...')

        # Calculate date ranges
        now = timezone.now()
        last_30_days = now - timedelta(days=30)
        last_7_days = now - timedelta(days=7)

        # Basic statistics
        stats = {
            'total_journals': Journal.objects.filter(is_published=True).count(),
            'total_authors': User.objects.filter(journals__is_published=True).distinct().count(),
            'journals_last_30_days': Journal.objects.filter(
                is_published=True,
                date_published__gte=last_30_days
            ).count(),
            'journals_last_7_days': Journal.objects.filter(
                is_published=True,
                date_published__gte=last_7_days
            ).count(),
        }

        # Revenue statistics
        try:
            revenue_stats = Journal.objects.filter(is_published=True).aggregate(
                total_tips=Sum('total_tips'),
                avg_tips=Avg('total_tips')
            )
            stats.update(revenue_stats)
        except:
            stats['total_tips'] = 0
            stats['avg_tips'] = 0

        # Top performing journals
        try:
            top_journals = list(Journal.objects.filter(
                is_published=True
            ).order_by('-total_tips')[:10].values(
                'title', 'author__username', 'total_tips', 'view_count'
            ))
            stats['top_journals'] = top_journals
        except:
            stats['top_journals'] = []

        # Top authors
        try:
            top_authors = list(User.objects.filter(
                journals__is_published=True
            ).annotate(
                total_earnings=Sum('journals__total_tips'),
                journal_count=Count('journals', filter=models.Q(journals__is_published=True))
            ).order_by('-total_earnings')[:10].values(
                'username', 'total_earnings', 'journal_count'
            ))
            stats['top_authors'] = top_authors
        except:
            stats['top_authors'] = []

        # Format output
        if options['format'] == 'json':
            output = json.dumps(stats, indent=2, default=str)
        else:
            output = self.format_text_report(stats)

        # Write to file or stdout
        if options['output']:
            with open(options['output'], 'w') as f:
                f.write(output)
            self.stdout.write(f'Report saved to {options["output"]}')
        else:
            self.stdout.write(output)

    def format_text_report(self, stats):
        """Format statistics as readable text"""
        report = []
        report.append("=== MARKETPLACE ANALYTICS REPORT ===\n")

        report.append("OVERVIEW:")
        report.append(f"Total Published Journals: {stats['total_journals']}")
        report.append(f"Total Authors: {stats['total_authors']}")
        report.append(f"New Journals (30 days): {stats['journals_last_30_days']}")
        report.append(f"New Journals (7 days): {stats['journals_last_7_days']}")
        report.append("")

        report.append("REVENUE:")
        report.append(f"Total Tips Earned: ${stats.get('total_tips', 0):.2f}")
        report.append(f"Average Tips per Journal: ${stats.get('avg_tips', 0):.2f}")
        report.append("")

        if stats['top_journals']:
            report.append("TOP 10 JOURNALS:")
            for i, journal in enumerate(stats['top_journals'][:10], 1):
                report.append(f"{i}. {journal['title']} by {journal['author__username']}")
                report.append(f"   Tips: ${journal.get('total_tips', 0):.2f}, Views: {journal.get('view_count', 0)}")
            report.append("")

        if stats['top_authors']:
            report.append("TOP 10 AUTHORS:")
            for i, author in enumerate(stats['top_authors'][:10], 1):
                report.append(f"{i}. {author['username']}")
                report.append(f"   Earnings: ${author.get('total_earnings', 0):.2f}, Journals: {author.get('journal_count', 0)}")

        return "\n".join(report)
