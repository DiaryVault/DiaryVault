// web3-auth.js - Complete Web3 Authentication Integration

class Web3AuthManager {
    constructor() {
        this.apiBaseUrl = '/api/web3';
        this.provider = null;
        this.account = null;
        this.chainId = null;
        this.isConnecting = false;
        
        // Initialize on page load
        this.init();
    }

    async init() {
        try {
            // Check if wallet is already connected
            await this.checkExistingConnection();
            
            // Set up event listeners
            this.setupEventListeners();
            
            console.log('Web3 Auth Manager initialized');
        } catch (error) {
            console.error('Failed to initialize Web3 Auth Manager:', error);
        }
    }

    setupEventListeners() {
        // Listen for account changes
        if (window.ethereum) {
            window.ethereum.on('accountsChanged', (accounts) => {
                this.handleAccountsChanged(accounts);
            });

            window.ethereum.on('chainChanged', (chainId) => {
                this.handleChainChanged(chainId);
            });

            window.ethereum.on('disconnect', () => {
                this.handleDisconnect();
            });
        }

        // Listen for page visibility changes
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden && this.account) {
                this.checkConnectionStatus();
            }
        });
    }

    async checkExistingConnection() {
        if (typeof window.ethereum !== 'undefined') {
            try {
                const accounts = await window.ethereum.request({ method: 'eth_accounts' });
                if (accounts.length > 0) {
                    this.account = accounts[0];
                    this.provider = window.ethereum;
                    
                    // Get current chain
                    this.chainId = await window.ethereum.request({ method: 'eth_chainId' });
                    
                    // Update UI
                    this.updateConnectionStatus('connected');
                    
                    return true;
                }
            } catch (error) {
                console.error('Error checking existing connection:', error);
            }
        }
        return false;
    }

    async connectWallet(walletType) {
        if (this.isConnecting) {
            console.log('Connection already in progress');
            return;
        }

        this.isConnecting = true;

        try {
            let success = false;

            switch (walletType) {
                case 'metamask':
                    success = await this.connectMetaMask();
                    break;
                case 'walletconnect':
                    success = await this.connectWalletConnect();
                    break;
                default:
                    throw new Error(`Unsupported wallet type: ${walletType}`);
            }

            if (success) {
                await this.authenticateWithBackend(walletType);
            }

        } catch (error) {
            console.error('Wallet connection failed:', error);
            this.showError('Failed to connect wallet: ' + error.message);
            throw error;
        } finally {
            this.isConnecting = false;
        }
    }

    async connectMetaMask() {
        if (typeof window.ethereum === 'undefined') {
            // Redirect to MetaMask installation
            window.open('https://metamask.io/download/', '_blank');
            throw new Error('MetaMask not installed. Please install MetaMask and try again.');
        }

        try {
            // Request account access
            const accounts = await window.ethereum.request({ 
                method: 'eth_requestAccounts' 
            });

            if (accounts.length === 0) {
                throw new Error('No accounts found. Please unlock MetaMask.');
            }

            this.account = accounts[0];
            this.provider = window.ethereum;

            // Get current chain
            this.chainId = await window.ethereum.request({ method: 'eth_chainId' });

            // Check if on Base network, switch if not
            await this.ensureBaseNetwork();

            return true;

        } catch (error) {
            if (error.code === 4001) {
                throw new Error('User rejected the connection request');
            }
            throw error;
        }
    }

    async connectWalletConnect() {
        // WalletConnect v2 implementation
        try {
            // This would require WalletConnect SDK
            // For now, show coming soon message
            throw new Error('WalletConnect integration coming soon! Please use MetaMask for now.');
            
            // Future implementation:
            /*
            const { WalletConnectModal } = await import('@walletconnect/modal');
            const { EthereumProvider } = await import('@walletconnect/ethereum-provider');
            
            const provider = await EthereumProvider.init({
                projectId: 'YOUR_PROJECT_ID', // Get from WalletConnect Cloud
                chains: [8453], // Base mainnet
                showQrModal: true,
            });

            await provider.connect();
            
            this.provider = provider;
            this.account = provider.accounts[0];
            this.chainId = provider.chainId;
            
            return true;
            */
        } catch (error) {
            throw error;
        }
    }

    async ensureBaseNetwork() {
        const baseChainId = '0x2105'; // Base mainnet (8453 in hex)
        
        if (this.chainId !== baseChainId) {
            try {
                // Try to switch to Base network
                await window.ethereum.request({
                    method: 'wallet_switchEthereumChain',
                    params: [{ chainId: baseChainId }],
                });
                
                this.chainId = baseChainId;
                
            } catch (switchError) {
                // If Base network isn't added, add it
                if (switchError.code === 4902) {
                    try {
                        await window.ethereum.request({
                            method: 'wallet_addEthereumChain',
                            params: [{
                                chainId: baseChainId,
                                chainName: 'Base',
                                nativeCurrency: {
                                    name: 'Ethereum',
                                    symbol: 'ETH',
                                    decimals: 18,
                                },
                                rpcUrls: ['https://mainnet.base.org'],
                                blockExplorerUrls: ['https://basescan.org'],
                            }],
                        });
                        
                        this.chainId = baseChainId;
                        
                    } catch (addError) {
                        throw new Error('Failed to add Base network to wallet');
                    }
                } else {
                    throw new Error('Failed to switch to Base network');
                }
            }
        }
    }

    async authenticateWithBackend(walletType) {
        try {
            // Step 1: Request nonce from backend
            const nonceResponse = await this.requestNonce();
            const { nonce, message } = nonceResponse;

            // Step 2: Sign the message
            const signature = await this.signMessage(message);

            // Step 3: Submit authentication
            const authResponse = await this.submitAuthentication({
                wallet_address: this.account,
                signature: signature,
                nonce: nonce,
                wallet_type: walletType,
                chain_id: parseInt(this.chainId, 16)
            });

            // Step 4: Handle successful authentication
            this.handleAuthSuccess(authResponse);

        } catch (error) {
            console.error('Backend authentication failed:', error);
            throw new Error('Authentication failed: ' + error.message);
        }
    }

    async requestNonce() {
        const response = await fetch(`${this.apiBaseUrl}/nonce/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken(),
            },
            body: JSON.stringify({
                wallet_address: this.account
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to get nonce');
        }

        return response.json();
    }

    async signMessage(message) {
        try {
            const signature = await window.ethereum.request({
                method: 'personal_sign',
                params: [message, this.account],
            });

            return signature;

        } catch (error) {
            if (error.code === 4001) {
                throw new Error('User rejected message signing');
            }
            throw new Error('Failed to sign message: ' + error.message);
        }
    }

    async submitAuthentication(authData) {
        const response = await fetch(`${this.apiBaseUrl}/login/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken(),
            },
            body: JSON.stringify(authData)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Authentication failed');
        }

        return response.json();
    }

    handleAuthSuccess(authResponse) {
        // Store auth token
        localStorage.setItem('auth_token', authResponse.token);
        localStorage.setItem('session_id', authResponse.session_id);
        localStorage.setItem('user_data', JSON.stringify(authResponse.user));

        // Update UI
        this.updateConnectionStatus('connected');
        
        // Show success message
        this.showSuccess('Wallet connected successfully! Redirecting...');

        // Redirect to dashboard
        setTimeout(() => {
            window.location.href = '/dashboard/';
        }, 1500);
    }

    async disconnect() {
        try {
            // Call backend disconnect
            const token = localStorage.getItem('auth_token');
            if (token) {
                await fetch(`${this.apiBaseUrl}/disconnect/`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Token ${token}`,
                        'X-CSRFToken': this.getCSRFToken(),
                    }
                });
            }

            // Clear local storage
            localStorage.removeItem('auth_token');
            localStorage.removeItem('session_id');
            localStorage.removeItem('user_data');

            // Reset state
            this.account = null;
            this.provider = null;
            this.chainId = null;

            // Update UI
            this.updateConnectionStatus('disconnected');
            
            this.showSuccess('Wallet disconnected successfully');

        } catch (error) {
            console.error('Disconnect failed:', error);
            this.showError('Failed to disconnect wallet');
        }
    }

    // Event handlers
    handleAccountsChanged(accounts) {
        if (accounts.length === 0) {
            this.handleDisconnect();
        } else if (accounts[0] !== this.account) {
            this.account = accounts[0];
            this.updateConnectionStatus('connected');
            
            // Re-authenticate with new account
            this.showInfo('Account changed. Please reconnect.');
            this.disconnect();
        }
    }

    handleChainChanged(chainId) {
        this.chainId = chainId;
        
        // Check if still on Base network
        if (chainId !== '0x2105') {
            this.showWarning('Please switch to Base network for full functionality');
        }
    }

    handleDisconnect() {
        this.account = null;
        this.provider = null;
        this.chainId = null;
        
        this.updateConnectionStatus('disconnected');
        
        // Clear stored data
        localStorage.removeItem('auth_token');
        localStorage.removeItem('session_id');
        localStorage.removeItem('user_data');
    }

    async checkConnectionStatus() {
        if (!this.account) return;

        try {
            const token = localStorage.getItem('auth_token');
            if (!token) {
                this.handleDisconnect();
                return;
            }

            // Verify session with backend
            const response = await fetch(`${this.apiBaseUrl}/profile/`, {
                headers: {
                    'Authorization': `Token ${token}`,
                }
            });

            if (!response.ok) {
                this.handleDisconnect();
            }

        } catch (error) {
            console.error('Connection status check failed:', error);
        }
    }

    // UI Helper methods
    updateConnectionStatus(status) {
        const statusElement = document.getElementById('connectionStatus');
        const indicatorElement = document.getElementById('statusIndicator');
        const textElement = document.getElementById('statusText');

        if (!statusElement || !indicatorElement || !textElement) return;

        statusElement.classList.remove('hidden');
        
        switch (status) {
            case 'connected':
                indicatorElement.className = 'connection-status connected';
                textElement.textContent = `Connected: ${this.getDisplayAddress()}`;
                break;
            case 'connecting':
                indicatorElement.className = 'connection-status connecting';
                textElement.textContent = 'Connecting...';
                break;
            case 'disconnected':
                indicatorElement.className = 'connection-status disconnected';
                textElement.textContent = 'Wallet not connected';
                break;
        }
    }

    setButtonLoading(button, loading) {
        if (!button) return;

        if (loading) {
            button.classList.add('loading');
            button.disabled = true;
        } else {
            button.classList.remove('loading');
            button.disabled = false;
        }
    }

    getDisplayAddress() {
        if (!this.account) return '';
        return `${this.account.slice(0, 6)}...${this.account.slice(-4)}`;
    }

    getCSRFToken() {
        const cookieValue = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrftoken='))
            ?.split('=')[1];
        return cookieValue || '';
    }

    // Toast notifications
    showSuccess(message) {
        this.showToast(message, 'success');
    }

    showError(message) {
        this.showToast(message, 'error');
    }

    showWarning(message) {
        this.showToast(message, 'warning');
    }

    showInfo(message) {
        this.showToast(message, 'info');
    }

    showToast(message, type = 'info') {
        // Use global toast system if available
        if (window.showToast) {
            window.showToast(message, type);
        } else {
            // Fallback to console and alert
            console.log(`${type.toUpperCase()}: ${message}`);
            if (type === 'error') {
                alert(`Error: ${message}`);
            }
        }
    }
}

// Initialize the Web3 Auth Manager
let web3Auth;

document.addEventListener('DOMContentLoaded', function() {
    web3Auth = new Web3AuthManager();
});

// Global functions for template usage
window.connectWallet = async function(walletType, button) {
    if (!web3Auth) {
        console.error('Web3 Auth Manager not initialized');
        return;
    }

    try {
        web3Auth.setButtonLoading(button, true);
        web3Auth.updateConnectionStatus('connecting');
        
        await web3Auth.connectWallet(walletType);
        
    } catch (error) {
        console.error('Connection failed:', error);
        web3Auth.setButtonLoading(button, false);
        web3Auth.updateConnectionStatus('disconnected');
    }
};

window.disconnectWallet = async function() {
    if (web3Auth) {
        await web3Auth.disconnect();
    }
};

window.showWalletOptions = function() {
    const options = [
        '🦊 MetaMask - Most popular wallet',
        '💙 Coinbase Wallet - Easy for beginners', 
        '🌈 Rainbow Wallet - Beautiful & simple',
        '',
        'All are free and take 2 minutes to set up!'
    ].join('\n');

    if (confirm(options + '\n\nWould you like to get MetaMask now?')) {
        window.open('https://metamask.io/download/', '_blank');
    }
};

// Utility functions
window.togglePassword = function(fieldId) {
    const passwordInput = document.getElementById(fieldId);
    const eyeClosed = document.getElementById('eye-closed-' + fieldId);
    const eyeOpen = document.getElementById('eye-open-' + fieldId);

    if (passwordInput.type === 'password') {
        passwordInput.type = 'text';
        eyeClosed.classList.add('hidden');
        eyeOpen.classList.remove('hidden');
    } else {
        passwordInput.type = 'password';
        eyeClosed.classList.remove('hidden');
        eyeOpen.classList.add('hidden');
    }
};

// Enhanced keyboard shortcuts
document.addEventListener('keydown', function(e) {
    // Alt + M for MetaMask
    if (e.altKey && e.key === 'm') {
        e.preventDefault();
        const metamaskBtn = document.getElementById('metamask-btn');
        if (metamaskBtn && !metamaskBtn.disabled) {
            metamaskBtn.click();
        }
    }

    // Alt + W for WalletConnect
    if (e.altKey && e.key === 'w') {
        e.preventDefault();
        const walletConnectBtn = document.getElementById('walletconnect-btn');
        if (walletConnectBtn && !walletConnectBtn.disabled) {
            walletConnectBtn.click();
        }
    }

    // Alt + D for Disconnect
    if (e.altKey && e.key === 'd') {
        e.preventDefault();
        if (web3Auth && web3Auth.account) {
            web3Auth.disconnect();
        }
    }

    // Escape to cancel any loading states
    if (e.key === 'Escape') {
        document.querySelectorAll('.wallet-btn.loading').forEach(btn => {
            web3Auth?.setButtonLoading(btn, false);
        });
    }
});

// Auto-focus and accessibility improvements
window.addEventListener('load', function() {
    const firstWalletBtn = document.getElementById('metamask-btn');
    if (firstWalletBtn) {
        setTimeout(() => firstWalletBtn.focus(), 500);
    }
});

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = Web3AuthManager;
}