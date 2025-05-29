// DiaryVault Service Worker - Fixed Version
const CACHE_NAME = 'diaryvault-v2';

// Only cache files that actually exist
const urlsToCache = [
  '/',
  '/static/manifest.json',
  '/static/favicon.ico'
];

self.addEventListener('install', function(event) {
  console.log('Service Worker: Installing');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(function(cache) {
        console.log('Service Worker: Caching files');
        // Cache each file individually and handle failures
        const cachePromises = urlsToCache.map(url => {
          return fetch(url)
            .then(response => {
              if (response.ok) {
                return cache.put(url, response.clone());
              } else {
                console.warn('Service Worker: Failed to cache', url, response.status);
              }
            })
            .catch(err => {
              console.warn('Service Worker: Error caching', url, err.message);
            });
        });

        return Promise.all(cachePromises);
      })
      .then(() => {
        console.log('Service Worker: Installation completed');
        self.skipWaiting();
      })
      .catch(err => {
        console.error('Service Worker: Installation failed', err);
      })
  );
});

self.addEventListener('activate', function(event) {
  console.log('Service Worker: Activating');
  event.waitUntil(
    caches.keys().then(function(cacheNames) {
      return Promise.all(
        cacheNames.map(function(cacheName) {
          if (cacheName !== CACHE_NAME) {
            console.log('Service Worker: Deleting old cache', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => {
      console.log('Service Worker: Activated');
      return self.clients.claim();
    })
  );
});

self.addEventListener('fetch', function(event) {
  // Only handle GET requests
  if (event.request.method !== 'GET') {
    return;
  }

  event.respondWith(
    caches.match(event.request)
      .then(function(response) {
        if (response) {
          return response;
        }

        return fetch(event.request).catch(function(err) {
          console.warn('Service Worker: Fetch failed for', event.request.url);
        });
      })
  );
});
