# diary/views/__init__.py

# Core views
from .core import home, signup, dashboard, custom_login, CustomLoginView

# Entry views
from .entries import (
    journal, entry_detail, edit_entry, delete_entry,
    library, time_period_view
)

# Insights views
from .insights import (
    insights, generate_mood_distribution, generate_tag_distribution,
    generate_mood_trends, generate_user_insights
)

# API views (existing functionality)
from .api import (
    # Original API views
    demo_journal, regenerate_summary_ajax, save_generated_entry, chat_with_ai,

    # NEW: Journal Compiler API views (AJAX endpoints)
    analyze_entries_ajax as api_analyze_entries,
    generate_journal_structure as api_generate_structure,
    publish_compiled_journal as api_publish_journal,
    quick_analyze_for_publishing, get_price_suggestion, generate_marketing_copy,
    get_journal_templates_api, save_journal_draft, load_journal_draft,
    validate_journal_data
)

# User views
from .user import (
    account_settings, preferences, save_pending_entry
)

# Marketplace views
from .marketplace import (
    marketplace_view, publish_journal, marketplace_monetization,
    marketplace_contest, marketplace_faq, marketplace_journal_detail,
    marketplace_author_profile, like_journal, tip_author, purchase_journal,
    quick_view_journal, add_to_wishlist, add_to_comparison,
    marketplace_search_suggestions
)

# Smart Journal Compiler views (main page view + backend services)
try:
    from .journal_compiler import (
        # Main view for the compiler page
        smart_journal_compiler,
        # Backend services (not conflicting with API endpoints)
        preview_journal_structure,
        # Journal editing functionality
        edit_journal,
        # Service classes
        JournalAnalysisService,
        JournalCompilerAI,
        JournalTemplateService
    )

    # Use API versions for AJAX endpoints to avoid conflicts
    analyze_entries_ajax = api_analyze_entries
    generate_journal_structure = api_generate_structure
    publish_compiled_journal = api_publish_journal

except ImportError:
    # Journal compiler views not yet created
    smart_journal_compiler = None
    preview_journal_structure = None

# Import modules for URL patterns (only if they exist)
try:
    from . import journal_compiler
except ImportError:
    journal_compiler = None

try:
    from . import marketplace as marketplace_views
except ImportError:
    marketplace_views = None

try:
    from . import api as api_views
except ImportError:
    api_views = None

# Make all API functions available at package level for easier importing
__all__ = [
    # Core views
    'home', 'signup', 'dashboard', 'custom_login', 'CustomLoginView',

    # Entry views
    'journal', 'entry_detail', 'edit_entry', 'delete_entry',
    'library', 'time_period_view',

    # Insights views
    'insights', 'generate_mood_distribution', 'generate_tag_distribution',
    'generate_mood_trends', 'generate_user_insights',

    # Original API views
    'demo_journal', 'regenerate_summary_ajax', 'save_generated_entry', 'chat_with_ai',

    # New Journal Compiler API views (using api_ prefix to avoid conflicts)
    'api_analyze_entries', 'api_generate_structure', 'api_publish_journal',
    'analyze_entries_ajax', 'generate_journal_structure', 'publish_compiled_journal',
    'quick_analyze_for_publishing', 'get_price_suggestion', 'generate_marketing_copy',
    'get_journal_templates_api', 'save_journal_draft', 'load_journal_draft',
    'validate_journal_data',

    # User views
    'account_settings', 'preferences', 'save_pending_entry',

    # Marketplace views
    'marketplace_view', 'publish_journal', 'marketplace_monetization',
    'marketplace_contest', 'marketplace_faq', 'marketplace_journal_detail',
    'marketplace_author_profile', 'like_journal', 'tip_author', 'purchase_journal',
    'quick_view_journal', 'add_to_wishlist', 'add_to_comparison',
    'marketplace_search_suggestions',

    # Smart Journal Compiler views and services
    'smart_journal_compiler', 'preview_journal_structure',
    'JournalAnalysisService', 'JournalCompilerAI', 'JournalTemplateService',

    # Module references
    'journal_compiler', 'marketplace_views', 'api_views',
]