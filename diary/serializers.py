from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Web3Nonce, WalletSession

User = get_user_model()

class NonceRequestSerializer(serializers.Serializer):
    wallet_address = serializers.CharField(max_length=42)
    
    def validate_wallet_address(self, value):
        """Validate Ethereum address format"""
        if not value.startswith('0x') or len(value) != 42:
            raise serializers.ValidationError("Invalid wallet address format")
        return value.lower()


class Web3LoginSerializer(serializers.Serializer):
    wallet_address = serializers.CharField(max_length=42)
    signature = serializers.CharField(max_length=132)
    nonce = serializers.CharField(max_length=64)
    wallet_type = serializers.CharField(max_length=20, required=False)
    chain_id = serializers.IntegerField(required=False, default=8453)


class UserProfileSerializer(serializers.ModelSerializer):
    display_address = serializers.CharField(source='get_display_address', read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'wallet_address', 'display_address',
            'wallet_type', 'is_web3_verified', 'total_rewards_earned',
            'diary_entries_count', 'streak_days', 'preferred_chain_id',
            'is_anonymous_mode', 'encryption_enabled', 'created_at'
        ]
        read_only_fields = [
            'id', 'wallet_address', 'is_web3_verified', 'total_rewards_earned',
            'diary_entries_count', 'streak_days', 'created_at'
        ]