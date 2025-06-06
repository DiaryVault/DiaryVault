# Core views
from .core import home, signup, dashboard, custom_login, CustomLoginView

# Entry views
from .entries import (
    journal, entry_detail, edit_entry, delete_entry,
    library, time_period_view, assign_to_chapter
)

# Insights views
from .insights import (
    insights, generate_mood_distribution, generate_tag_distribution,
    generate_mood_trends, generate_user_insights
)

# Biography views
from .biography import (
    biography, manage_chapters, edit_chapter, delete_chapter,
    generate_biography_api,
    regenerate_chapter,
)

# API views
from .api import (
    demo_journal, regenerate_summary_ajax, save_generated_entry, chat_with_ai
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
