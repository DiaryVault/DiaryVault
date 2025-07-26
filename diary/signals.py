from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import UserProfile, Entry, Tag, WalletSession, Web3Nonce
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

# ============================================================================
# User Profile Signals
# ============================================================================

@receiver(post_save, sender=User)
def manage_user_profile(sender, instance, created, **kwargs):
    """
    Consolidated signal to handle user profile creation and updates.
    Creates profile on user creation, ensures profile exists on user save.
    """
    if created:
        # Create profile for new users
        try:
            UserProfile.objects.create(user=instance)
            logger.info(f"Created profile for new user: {instance.username}")
        except Exception as e:
            logger.error(f"Error creating profile for user {instance.username}: {str(e)}")
    else:
        # Ensure profile exists for existing users and save it
        try:
            if hasattr(instance, 'userprofile'):
                instance.userprofile.save()
            else:
                # Create profile if it doesn't exist
                UserProfile.objects.create(user=instance)
                logger.info(f"Created missing profile for user: {instance.username}")
        except Exception as e:
            logger.error(f"Error managing profile for user {instance.username}: {str(e)}")

# ============================================================================
# Journal Entry Signals
# ============================================================================

@receiver(post_save, sender=Entry)
def update_tag_usage_count(sender, instance, created, **kwargs):
    """Update usage count for tags when an entry is saved."""
    if created:
        # Update usage count for all tags associated with this entry
        for tag in instance.tags.all():
            tag.update_usage_count()
        
        logger.info(f"Updated tag usage counts for new entry: {instance.title}")

@receiver(post_delete, sender=Entry)
def cleanup_tag_usage_on_delete(sender, instance, **kwargs):
    """Update tag usage counts when an entry is deleted."""
    try:
        # Update usage count for all tags that were associated with this entry
        for tag in instance.tags.all():
            tag.update_usage_count()
        
        logger.info(f"Updated tag usage counts after deleting entry: {instance.title}")
    except Exception as e:
        logger.error(f"Error updating tag usage after entry deletion: {str(e)}")

# ============================================================================
# Web3 Authentication Signals
# ============================================================================

@receiver(post_save, sender=User)
def handle_web3_user_creation(sender, instance, created, **kwargs):
    """Handle Web3-specific setup for new users."""
    if created and instance.wallet_address:
        try:
            # Log Web3 user creation
            logger.info(f"New Web3 user created: {instance.username} with wallet {instance.wallet_address}")
            
            # Initialize user rewards if applicable
            if hasattr(instance, 'total_rewards_earned') and instance.total_rewards_earned is None:
                instance.total_rewards_earned = 0
                instance.save(update_fields=['total_rewards_earned'])
                
        except Exception as e:
            logger.error(f"Error handling Web3 user creation for {instance.username}: {str(e)}")

@receiver(post_delete, sender=WalletSession)
def cleanup_wallet_session(sender, instance, **kwargs):
    """Clean up when a wallet session is deleted."""
    try:
        logger.info(f"Wallet session deleted for user {instance.user.username}, wallet {instance.wallet_address}")
    except Exception as e:
        logger.error(f"Error during wallet session cleanup: {str(e)}")

@receiver(post_delete, sender=Web3Nonce)
def log_nonce_cleanup(sender, instance, **kwargs):
    """Log when nonces are cleaned up."""
    try:
        logger.debug(f"Web3 nonce cleaned up for wallet {instance.wallet_address}")
    except Exception as e:
        logger.error(f"Error during nonce cleanup logging: {str(e)}")

# ============================================================================
# Tag Management Signals
# ============================================================================

@receiver(post_save, sender=Tag)
def handle_tag_creation(sender, instance, created, **kwargs):
    """Handle tag creation and updates."""
    if created:
        logger.info(f"New tag created: {instance.name} by user {instance.user.username}")

@receiver(post_delete, sender=Tag)
def handle_tag_deletion(sender, instance, **kwargs):
    """Handle tag deletion."""
    try:
        logger.info(f"Tag deleted: {instance.name} by user {instance.user.username}")
    except Exception as e:
        logger.error(f"Error handling tag deletion: {str(e)}")

# ============================================================================
# User Activity Signals
# ============================================================================

@receiver(post_save, sender=Entry)
def update_user_streak(sender, instance, created, **kwargs):
    """Update user streak when a new entry is created."""
    if created:
        try:
            user = instance.user
            # Update streak logic here
            if hasattr(user, 'streak_days'):
                # You can implement streak calculation logic here
                # For now, just log the activity
                logger.info(f"Entry created by {user.username}, checking streak status")
                
        except Exception as e:
            logger.error(f"Error updating user streak: {str(e)}")

# ============================================================================
# Marketplace Signals (Optional - if marketplace models exist)
# ============================================================================

try:
    from .models import Journal, JournalLike, JournalPurchase
    
    @receiver(post_save, sender=JournalLike)
    def update_journal_popularity_on_like(sender, instance, created, **kwargs):
        """Update journal popularity when liked."""
        if created:
            try:
                journal = instance.journal
                # Update popularity score
                journal.update_popularity_score()
                logger.info(f"Journal {journal.title} liked by {instance.user.username}")
            except Exception as e:
                logger.error(f"Error updating journal popularity on like: {str(e)}")
    
    @receiver(post_save, sender=JournalPurchase)
    def handle_journal_purchase(sender, instance, created, **kwargs):
        """Handle journal purchase events."""
        if created:
            try:
                logger.info(f"Journal {instance.journal.title} purchased by {instance.buyer.username}")
                # You can add additional purchase handling logic here
            except Exception as e:
                logger.error(f"Error handling journal purchase: {str(e)}")

except ImportError:
    # Marketplace models not available yet
    logger.debug("Marketplace models not available, skipping marketplace signals")
    pass