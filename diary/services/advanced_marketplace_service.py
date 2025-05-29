from decimal import Decimal
from django.db.models import Avg, Sum, Count, Q
from django.utils import timezone
from datetime import timedelta
import json

class MarketplaceEnhancementService:
    """
    Advanced marketplace features based on 2025 best practices:
    - Marketplace 2.0 monetization strategies
    - Data monetization
    - Dynamic pricing
    - Enhanced advertising placements
    """

    @staticmethod
    def calculate_dynamic_pricing(journal, base_price, market_demand=None):
        """
        Implement dynamic pricing based on demand, popularity, and market trends
        Based on 2025 research showing 15-30% revenue increase with dynamic pricing
        """
        if not market_demand:
            # Calculate demand based on views, likes, and recent activity
            recent_views = getattr(journal, 'view_count', 0)
            recent_likes = journal.likes.count() if hasattr(journal, 'likes') else 0
            recent_purchases = journal.purchases.filter(
                created_at__gte=timezone.now() - timedelta(days=7)
            ).count() if hasattr(journal, 'purchases') else 0

            # Demand score (0-100)
            demand_score = min(100, (recent_views * 0.1) + (recent_likes * 2) + (recent_purchases * 10))
        else:
            demand_score = market_demand

        # Pricing multiplier based on demand
        if demand_score >= 80:
            multiplier = 1.3  # High demand - 30% increase
        elif demand_score >= 60:
            multiplier = 1.15  # Medium-high demand - 15% increase
        elif demand_score >= 40:
            multiplier = 1.0   # Normal demand - base price
        elif demand_score >= 20:
            multiplier = 0.85  # Low demand - 15% discount
        else:
            multiplier = 0.7   # Very low demand - 30% discount

        suggested_price = base_price * Decimal(str(multiplier))

        # Round to reasonable price points
        if suggested_price < 1:
            suggested_price = Decimal('0.99')
        elif suggested_price < 10:
            suggested_price = suggested_price.quantize(Decimal('0.01'))
        else:
            suggested_price = suggested_price.quantize(Decimal('0.1'))

        return {
            'suggested_price': suggested_price,
            'demand_score': demand_score,
            'multiplier': multiplier,
            'reasoning': f"Based on {demand_score}% demand score"
        }

    @staticmethod
    def generate_seller_analytics_package(user):
        """
        Monetize data by providing paid analytics to authors
        Research shows data monetization can add 20-40% additional revenue
        """
        from ..models import Journal, Entry, JournalPurchase, Tip

        journals = Journal.objects.filter(author=user, is_published=True)

        analytics = {
            'performance_metrics': {
                'total_revenue': 0,
                'revenue_trend': [],
                'top_performing_content': [],
                'audience_demographics': {},
                'peak_activity_times': []
            },
            'market_insights': {
                'category_performance': {},
                'competitor_analysis': {},
                'pricing_recommendations': []
            },
            'growth_opportunities': {
                'content_gaps': [],
                'trending_topics': [],
                'monetization_suggestions': []
            }
        }

        # Calculate revenue metrics
        total_sales = JournalPurchase.objects.filter(
            journal__author=user
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        total_tips = Tip.objects.filter(
            recipient=user
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        analytics['performance_metrics']['total_revenue'] = total_sales + total_tips

        # Revenue trend (last 12 months)
        for i in range(12):
            month_start = timezone.now() - timedelta(days=30 * (i + 1))
            month_end = timezone.now() - timedelta(days=30 * i)

            month_revenue = JournalPurchase.objects.filter(
                journal__author=user,
                created_at__gte=month_start,
                created_at__lt=month_end
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

            analytics['performance_metrics']['revenue_trend'].append({
                'month': month_start.strftime('%Y-%m'),
                'revenue': float(month_revenue)
            })

        # Top performing content
        for journal in journals.annotate(
            purchase_count=Count('purchases'),
            total_revenue=Sum('purchases__amount')
        ).order_by('-total_revenue')[:5]:
            analytics['performance_metrics']['top_performing_content'].append({
                'title': journal.title,
                'revenue': float(journal.total_revenue or 0),
                'purchases': journal.purchase_count,
                'views': journal.view_count or 0
            })

        # Pricing recommendations using dynamic pricing
        for journal in journals:
            pricing_data = MarketplaceEnhancementService.calculate_dynamic_pricing(
                journal, journal.price
            )
            analytics['market_insights']['pricing_recommendations'].append({
                'journal': journal.title,
                'current_price': float(journal.price),
                'suggested_price': float(pricing_data['suggested_price']),
                'reasoning': pricing_data['reasoning']
            })

        return analytics

    @staticmethod
    def create_premium_placement_opportunities():
        """
        Monetize product placement - research shows this can generate 25% additional revenue
        """
        placements = {
            'featured_homepage': {
                'price_per_week': Decimal('25.00'),
                'description': 'Featured placement on homepage hero section',
                'max_slots': 3,
                'estimated_views': 5000
            },
            'category_spotlight': {
                'price_per_week': Decimal('15.00'),
                'description': 'Highlighted in relevant category pages',
                'max_slots': 5,
                'estimated_views': 1500
            },
            'newsletter_feature': {
                'price_per_edition': Decimal('10.00'),
                'description': 'Featured in weekly newsletter to subscribers',
                'max_slots': 2,
                'estimated_views': 800
            },
            'search_boost': {
                'price_per_week': Decimal('8.00'),
                'description': 'Boosted ranking in search results',
                'max_slots': 10,
                'estimated_views': 1000
            }
        }
        return placements

    @staticmethod
    def implement_subscription_tiers():
        """
        Multiple subscription models for different user types
        Research shows hybrid models increase retention by 35%
        """
        tiers = {
            'reader_basic': {
                'price_monthly': Decimal('4.99'),
                'benefits': [
                    'Ad-free reading experience',
                    'Access to 3 premium journals per month',
                    'Basic bookmarking features'
                ]
            },
            'reader_premium': {
                'price_monthly': Decimal('9.99'),
                'benefits': [
                    'All basic benefits',
                    'Unlimited premium journal access',
                    'Advanced search and filtering',
                    'Offline reading capability',
                    'Early access to new releases'
                ]
            },
            'author_starter': {
                'price_monthly': Decimal('14.99'),
                'benefits': [
                    'Publish up to 3 journals',
                    'Basic analytics dashboard',
                    'Standard marketplace visibility',
                    '90% revenue share (vs 85% standard)'
                ]
            },
            'author_professional': {
                'price_monthly': Decimal('29.99'),
                'benefits': [
                    'Unlimited journal publishing',
                    'Advanced analytics and insights',
                    'Priority customer support',
                    'Premium placement opportunities',
                    '95% revenue share',
                    'Custom branding options'
                ]
            }
        }
        return tiers
