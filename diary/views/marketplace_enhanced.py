from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from ..services.advanced_marketplace_service import MarketplaceEnhancementService

@login_required
def dynamic_pricing_suggestions(request, journal_id):
    """API endpoint for dynamic pricing suggestions"""
    journal = get_object_or_404(Journal, id=journal_id, author=request.user)

    pricing_data = MarketplaceEnhancementService.calculate_dynamic_pricing(
        journal, journal.price
    )

    return JsonResponse({
        'success': True,
        'current_price': float(journal.price),
        'suggested_price': float(pricing_data['suggested_price']),
        'demand_score': pricing_data['demand_score'],
        'reasoning': pricing_data['reasoning'],
        'potential_increase': float(pricing_data['suggested_price'] - journal.price)
    })

@login_required
def purchase_analytics_package(request):
    """Purchase advanced analytics for authors"""
    if request.method == 'POST':
        package_type = request.POST.get('package_type', 'basic_insights')

        # Generate analytics data
        analytics_data = MarketplaceEnhancementService.generate_seller_analytics_package(
            request.user
        )

        # Pricing for analytics packages
        package_prices = {
            'basic_insights': Decimal('9.99'),
            'advanced_analytics': Decimal('19.99'),
            'market_intelligence': Decimal('39.99')
        }

        price = package_prices.get(package_type, Decimal('9.99'))

        # Create analytics package record
        package = AnalyticsPackage.objects.create(
            user=request.user,
            package_type=package_type,
            data=analytics_data,
            amount_paid=price,
            valid_until=timezone.now() + timedelta(days=30)
        )

        return JsonResponse({
            'success': True,
            'package_id': package.id,
            'data': analytics_data
        })

    return render(request, 'diary/purchase_analytics.html')

@login_required
def premium_placements(request):
    """Manage premium placement opportunities"""
    placements = MarketplaceEnhancementService.create_premium_placement_opportunities()

    user_journals = Journal.objects.filter(
        author=request.user,
        is_published=True
    )

    active_placements = MarketplacePlacement.objects.filter(
        journal__author=request.user,
        is_active=True,
        end_date__gt=timezone.now()
    )

    context = {
        'placements': placements,
        'journals': user_journals,
        'active_placements': active_placements
    }

    return render(request, 'diary/premium_placements.html', context)

@login_required
def subscription_management(request):
    """Manage user subscriptions"""
    tiers = MarketplaceEnhancementService.implement_subscription_tiers()

    current_subscription = None
    try:
        current_subscription = request.user.marketplace_subscription
    except:
        pass

    context = {
        'tiers': tiers,
        'current_subscription': current_subscription
    }

    return render(request, 'diary/subscription_management.html', context)
