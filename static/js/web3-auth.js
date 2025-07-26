// static/js/web3-auth.js - Simplified companion to base.html Reown AppKit
// This extends the modern Reown AppKit integration from base.html

class DiaryVaultWeb3Helper {
  constructor() {
    this.isInitialized = false
    this.init()
  }

  async init() {
    // Wait for base.html wallet system to be ready
    this.waitForBaseWalletSystem()
  }

  waitForBaseWalletSystem() {
    if (window.getWalletInfo && window.connectWallet && window.openWalletModal) {
      this.isInitialized = true
      this.setupEnhancements()
    } else {
      // Retry in 100ms
      setTimeout(() => this.waitForBaseWalletSystem(), 100)
    }
  }

  setupEnhancements() {
    // Listen for wallet connection events from base.html
    window.addEventListener('walletConnectionChanged', (event) => {
      this.handleWalletChange(event.detail)
    })

    // Auto-check connection on page load
    setTimeout(() => this.checkAndUpdateUI(), 500)
  }

  handleWalletChange({ isConnected, address, chainId, wasConnected }) {
    // Update UI elements specific to login/signup pages
    this.updateConnectionUI(isConnected, address, chainId)
    
    // Handle successful connections
    if (isConnected && !wasConnected) {
      this.handleSuccessfulConnection(address)
    }
  }

  updateConnectionUI(isConnected, address, chainId) {
    // Update status indicators
    const statusElement = document.getElementById('web3Status')
    const statusIndicator = document.getElementById('statusIndicator') 
    const statusText = document.getElementById('statusText')

    if (statusElement && statusIndicator && statusText) {
      if (isConnected && address) {
        statusElement.classList.remove('hidden')
        statusIndicator.className = 'web3-status ready'
        statusText.textContent = `Connected: ${this.getShortAddress(address)}`
      } else {
        statusElement.classList.add('hidden')
      }
    }

    // Update button states
    this.updateButtonStates(isConnected, chainId)
  }

  updateButtonStates(isConnected, chainId) {
    const metamaskStatus = document.getElementById('metamask-status')
    const reownStatus = document.getElementById('reown-status')
    
    if (metamaskStatus) {
      if (isConnected) {
        metamaskStatus.textContent = 'Connected & Earning!'
        metamaskStatus.className = 'text-sm text-green-200'
      } else if (window.ethereum) {
        metamaskStatus.textContent = 'Ready to connect'
        metamaskStatus.className = 'text-sm text-white/80'
      } else {
        metamaskStatus.textContent = 'Click to install'
        metamaskStatus.className = 'text-sm text-orange-200'
      }
    }

    if (reownStatus) {
      if (isConnected) {
        reownStatus.textContent = 'Connected & Earning!'
        reownStatus.className = 'text-sm text-green-200'
      } else {
        reownStatus.textContent = 'Email, Social, or 300+ wallets'
        reownStatus.className = 'text-sm text-white/80'
      }
    }

    // Update wrong network warning
    if (isConnected && chainId !== 8453) {
      this.showNetworkWarning()
    }
  }

  handleSuccessfulConnection(address) {
    // Show success message
    if (window.showToast) {
      window.showToast('🎉 Wallet connected! You can now earn rewards!', 'success')
    }

    // Save connection info for session
    this.saveConnectionInfo(address)

    // Redirect after success (if on login/signup page)
    if (this.shouldRedirectAfterConnection()) {
      setTimeout(() => {
        const isFirstTime = window.location.pathname.includes('signup')
        const dashboardUrl = isFirstTime ? '/dashboard/?first_time=true' : '/dashboard/'
        window.location.href = dashboardUrl
      }, 2000)
    }
  }

  shouldRedirectAfterConnection() {
    const path = window.location.pathname
    return path.includes('login') || path.includes('signup') || path.includes('connect')
  }

  showNetworkWarning() {
    if (window.showToast) {
      window.showToast('Please switch to Base network for earning rewards', 'warning', 8000)
    }
  }

  checkAndUpdateUI() {
    const walletInfo = window.getWalletInfo?.()
    if (walletInfo) {
      this.updateConnectionUI(
        walletInfo.isConnected, 
        walletInfo.address, 
        walletInfo.chainId
      )
    }
  }

  // Utility methods
  getShortAddress(address) {
    if (!address) return ''
    return `${address.slice(0, 6)}...${address.slice(-4)}`
  }

  saveConnectionInfo(address) {
    try {
      const connectionData = {
        address: address,
        timestamp: Date.now(),
        source: 'diaryvault-login'
      }
      sessionStorage.setItem('dv_wallet_connection', JSON.stringify(connectionData))
    } catch (error) {
      console.warn('Failed to save connection info:', error)
    }
  }

  loadConnectionInfo() {
    try {
      const saved = sessionStorage.getItem('dv_wallet_connection')
      if (saved) {
        const data = JSON.parse(saved)
        // Check if less than 24 hours old
        if (Date.now() - data.timestamp < 86400000) {
          return data
        } else {
          sessionStorage.removeItem('dv_wallet_connection')
        }
      }
    } catch (error) {
      console.warn('Failed to load connection info:', error)
    }
    return null
  }

  // Enhanced error handling for login pages
  handleConnectionError(error, button = null) {
    let message = 'Connection failed. Please try again.'
    
    if (error.message?.includes('rejected')) {
      message = 'Connection was rejected. Please try again.'
    } else if (error.message?.includes('not installed')) {
      message = 'Please install a wallet or use email login'
    } else if (error.message?.includes('timeout')) {
      message = 'Connection timed out. Please try again.'
    }
    
    if (window.showToast) {
      window.showToast(message, 'error')
    }
    
    if (button) {
      button.classList.remove('loading')
      button.disabled = false
    }
  }
}

// Initialize the helper
window.diaryVaultWeb3Helper = new DiaryVaultWeb3Helper()

// Legacy compatibility functions that delegate to base.html
window.connectWallet = async function(walletType, button) {
  try {
    if (button) {
      button.classList.add('loading')
      button.disabled = true
    }

    // Use the base.html functions
    if (walletType === 'metamask') {
      await window.connectWallet?.() // Direct MetaMask connection
    } else {
      await window.openWalletModal?.() // Reown AppKit modal
    }

  } catch (error) {
    console.error('Connection failed:', error)
    window.diaryVaultWeb3Helper?.handleConnectionError(error, button)
  } finally {
    if (button) {
      setTimeout(() => {
        button.classList.remove('loading')
        button.disabled = false
      }, 1000)
    }
  }
}

// Enhanced disconnect that works with base.html
window.disconnectWallet = function() {
  if (window.disconnectWallet) {
    window.disconnectWallet()
  }
  
  // Clear our session data too
  try {
    sessionStorage.removeItem('dv_wallet_connection')
  } catch (error) {
    console.warn('Failed to clear session data:', error)
  }
}

// Wallet education helper
window.showWalletOptions = function() {
  const message = `New to crypto wallets? Here are some free options:

🦊 MetaMask (Most popular)
📱 Coinbase Wallet (Easy for beginners) 
🔗 Rainbow Wallet (Beautiful & simple)

All are free and take 2 minutes to set up!

Or use the "Any Wallet" button above for email/social login!`
  
  if (confirm(message + '\n\nWould you like to get MetaMask now?')) {
    window.open('https://metamask.io/download/', '_blank')
  }
}

// Enhanced mobile detection and handling
function isMobileDevice() {
  return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent)
}

// Auto-focus enhancements for better UX
document.addEventListener('DOMContentLoaded', function() {
  // Auto-focus first wallet button on login/signup pages
  setTimeout(() => {
    const reownBtn = document.getElementById('reown-btn')
    const metamaskBtn = document.getElementById('metamask-btn')
    const firstBtn = reownBtn || metamaskBtn
    
    if (firstBtn && !window.diaryVaultWeb3Helper?.loadConnectionInfo()) {
      try {
        firstBtn.focus()
      } catch (e) {
        // Ignore focus errors
      }
    }
  }, 1000)
})

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
  // No cleanup needed - base.html handles it
})

// Export for debugging
window.DiaryVaultWeb3Helper = DiaryVaultWeb3Helper