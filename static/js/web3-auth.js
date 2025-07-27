/**
 * Web3 Authentication for DiaryVault
 * Simplified and reliable implementation
 */

(function() {
    'use strict';

    // Global state
    window.walletState = {
        isConnected: false,
        address: null,
        chainId: null,
        provider: null
    };

    // Base network configuration
    const BASE_NETWORK = {
        chainId: '0x2105', // 8453 in hex
        chainName: 'Base',
        nativeCurrency: {
            name: 'Ether',
            symbol: 'ETH',
            decimals: 18
        },
        rpcUrls: ['https://mainnet.base.org'],
        blockExplorerUrls: ['https://basescan.org']
    };

    // Check if MetaMask is installed
    function isMetaMaskInstalled() {
        return typeof window.ethereum !== 'undefined' && window.ethereum.isMetaMask;
    }

    // Initialize wallet detection
    function initializeWallet() {
        console.log('🚀 Initializing wallet detection...');

        if (isMetaMaskInstalled()) {
            console.log('✅ MetaMask detected');
            setupMetaMaskListeners();
            checkExistingConnection();
        } else {
            console.log('⚠️ MetaMask not detected');
        }
    }

    // Setup MetaMask event listeners
    function setupMetaMaskListeners() {
        if (!window.ethereum) return;

        window.ethereum.on('accountsChanged', handleAccountsChanged);
        window.ethereum.on('chainChanged', handleChainChanged);
        window.ethereum.on('disconnect', handleDisconnect);
    }

    // Check for existing connection
    async function checkExistingConnection() {
        try {
            if (!window.ethereum) return;

            const accounts = await window.ethereum.request({ method: 'eth_accounts' });
            const chainId = await window.ethereum.request({ method: 'eth_chainId' });

            if (accounts.length > 0) {
                updateWalletState(true, accounts[0], parseInt(chainId, 16));
            }
        } catch (error) {
            console.error('Error checking existing connection:', error);
        }
    }

    // Handle account changes
    function handleAccountsChanged(accounts) {
        if (accounts.length === 0) {
            updateWalletState(false, null, null);
        } else {
            updateWalletState(true, accounts[0], window.walletState.chainId);
        }
    }

    // Handle chain changes
    function handleChainChanged(chainId) {
        const chainIdNumber = parseInt(chainId, 16);
        updateWalletState(window.walletState.isConnected, window.walletState.address, chainIdNumber);
    }

    // Handle disconnect
    function handleDisconnect() {
        updateWalletState(false, null, null);
    }

    // Update wallet state
    function updateWalletState(isConnected, address, chainId) {
        const wasConnected = window.walletState.isConnected;
        
        window.walletState.isConnected = isConnected;
        window.walletState.address = address;
        window.walletState.chainId = chainId;

        // Update UI
        updateWalletUI(isConnected, address, chainId);

        // Dispatch events
        window.dispatchEvent(new CustomEvent('walletConnectionChanged', {
            detail: { isConnected, address, chainId, wasConnected }
        }));

        // Show notifications
        if (isConnected && !wasConnected && window.showToast) {
            window.showToast(`Wallet connected: ${address.slice(0, 6)}...${address.slice(-4)}`, 'success');
            
            if (chainId !== 8453) {
                window.showToast('Please switch to Base network', 'warning');
            }
        } else if (!isConnected && wasConnected && window.showToast) {
            window.showToast('Wallet disconnected', 'info');
        }
    }

    // Update UI elements
    function updateWalletUI(isConnected, address, chainId) {
        const walletStatus = document.getElementById('wallet-status');
        const walletAddress = document.getElementById('wallet-address');

        if (walletStatus && walletAddress) {
            if (isConnected) {
                walletStatus.classList.remove('hidden', 'disconnected');
                walletAddress.textContent = `${address.slice(0, 6)}...${address.slice(-4)}`;
                
                if (chainId !== 8453) {
                    walletStatus.classList.add('disconnected');
                    walletAddress.textContent += ' (Wrong Network)';
                }
            } else {
                walletStatus.classList.add('hidden');
            }
        }

        // Update connection status indicators
        const statusElements = document.querySelectorAll('[id*="status"]');
        statusElements.forEach(element => {
            if (element.id.includes('reown') || element.id.includes('metamask')) {
                if (isConnected) {
                    element.textContent = `Connected: ${address.slice(0, 6)}...${address.slice(-4)}`;
                } else {
                    const originalText = element.id.includes('reown') 
                        ? 'Email, Social, or 300+ wallets'
                        : 'Direct connection';
                    element.textContent = originalText;
                }
            }
        });
    }

    // Connect wallet with button feedback
    async function connectWallet(walletType = 'metamask', button = null) {
        try {
            if (button) {
                button.classList.add('loading');
                button.disabled = true;
            }

            if (!isMetaMaskInstalled()) {
                if (window.showToast) {
                    window.showToast('Please install MetaMask to connect your wallet', 'warning');
                }
                showWalletOptions();
                return;
            }

            console.log(`🔗 Connecting ${walletType} wallet...`);

            // Request account access
            const accounts = await window.ethereum.request({
                method: 'eth_requestAccounts'
            });

            if (accounts.length > 0) {
                const chainId = await window.ethereum.request({ method: 'eth_chainId' });
                updateWalletState(true, accounts[0], parseInt(chainId, 16));

                // Switch to Base network if needed
                if (parseInt(chainId, 16) !== 8453) {
                    await switchToBaseNetwork();
                }
            }

        } catch (error) {
            console.error('Error connecting wallet:', error);
            
            if (error.code === 4001) {
                if (window.showToast) {
                    window.showToast('Wallet connection rejected by user', 'info');
                }
            } else {
                if (window.showToast) {
                    window.showToast('Failed to connect wallet', 'error');
                }
            }
        } finally {
            if (button) {
                button.classList.remove('loading');
                button.disabled = false;
            }
        }
    }

    // Switch to Base network
    async function switchToBaseNetwork() {
        try {
            if (!window.ethereum) {
                throw new Error('No wallet provider found');
            }

            await window.ethereum.request({
                method: 'wallet_switchEthereumChain',
                params: [{ chainId: BASE_NETWORK.chainId }],
            });

            if (window.showToast) {
                window.showToast('Switched to Base network', 'success');
            }

        } catch (error) {
            // If the chain hasn't been added to MetaMask, add it
            if (error.code === 4902) {
                try {
                    await window.ethereum.request({
                        method: 'wallet_addEthereumChain',
                        params: [BASE_NETWORK],
                    });
                    
                    if (window.showToast) {
                        window.showToast('Base network added and switched', 'success');
                    }
                } catch (addError) {
                    console.error('Error adding Base network:', addError);
                    if (window.showToast) {
                        window.showToast('Failed to add Base network', 'error');
                    }
                }
            } else {
                console.error('Error switching to Base network:', error);
                if (window.showToast) {
                    window.showToast('Please switch to Base network manually', 'warning');
                }
            }
        }
    }

    // Disconnect wallet
    async function disconnectWallet() {
        try {
            // MetaMask doesn't have a disconnect method, so we just update our state
            updateWalletState(false, null, null);
            
            if (window.showToast) {
                window.showToast('Wallet disconnected successfully', 'info');
            }
        } catch (error) {
            console.error('Error disconnecting wallet:', error);
            if (window.showToast) {
                window.showToast('Failed to disconnect wallet', 'error');
            }
        }
    }

    // Show wallet options for users without wallets
    function showWalletOptions() {
        const message = `
            <div class="text-center">
                <h3 class="font-semibold mb-3">Get a Crypto Wallet</h3>
                <p class="text-sm text-gray-600 mb-4">You'll need a crypto wallet to use DiaryVault's Web3 features.</p>
                <div class="space-y-2">
                    <a href="https://metamask.io/download/" target="_blank" class="block p-3 bg-orange-500 text-white rounded-lg hover:bg-orange-600 transition-colors">
                        📱 Install MetaMask (Recommended)
                    </a>
                    <a href="https://www.coinbase.com/wallet" target="_blank" class="block p-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors">
                        💼 Get Coinbase Wallet
                    </a>
                </div>
                <p class="text-xs text-gray-500 mt-3">These are free and take just a few minutes to set up.</p>
            </div>
        `;

        // Create a simple modal
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4';
        modal.innerHTML = `
            <div class="bg-white rounded-2xl p-6 max-w-sm w-full">
                ${message}
                <button onclick="this.closest('.fixed').remove()" class="mt-4 w-full p-2 bg-gray-200 text-gray-800 rounded-lg hover:bg-gray-300 transition-colors">
                    Close
                </button>
            </div>
        `;

        document.body.appendChild(modal);

        // Close on backdrop click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.remove();
            }
        });
    }

    // Get wallet info
    function getWalletInfo() {
        return {
            isConnected: window.walletState.isConnected,
            address: window.walletState.address,
            chainId: window.walletState.chainId,
            isCorrectNetwork: window.walletState.chainId === 8453,
            isMetaMaskInstalled: isMetaMaskInstalled()
        };
    }

    // Handle wallet connection with button feedback
    window.handleWalletConnection = async function(walletType, button) {
        await connectWallet(walletType, button);
    };

    // Make functions globally available
    window.connectWallet = connectWallet;
    window.openWalletModal = connectWallet; // Same function for simplicity
    window.disconnectWallet = disconnectWallet;
    window.getWalletInfo = getWalletInfo;
    window.switchToBaseNetwork = switchToBaseNetwork;
    window.showWalletOptions = showWalletOptions;

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeWallet);
    } else {
        initializeWallet();
    }

    console.log('✅ Web3 authentication module loaded');

})();