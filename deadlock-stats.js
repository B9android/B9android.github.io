class RateLimiter {
    constructor(requestsPerSecond = 1) {
        this.delay = 1000 / requestsPerSecond;
        this.lastRequest = 0;
    }

    async throttle() {
        const now = Date.now();
        const timeSinceLastRequest = now - this.lastRequest;

        if (timeSinceLastRequest < this.delay) {
            await new Promise(resolve =>
                setTimeout(resolve, this.delay - timeSinceLastRequest)
            );
        }

        this.lastRequest = Date.now();
    }
}

const limiter = new RateLimiter(1);
async function fetchWithRateLimit(url) {
    await limiter.throttle();
    return fetch(url);
}

const DeadlockStats = (() => {
    const CACHE_KEY = 'deadlock-stats';
    const CACHE_DURATION = 3600000;

    async function fetchStats(accountId, useCache = true) {
        if (useCache) {
            const cached = getCache();
            if (cached) return cached;
        }

        try {
            const res = await fetchWithRateLimit(`https://api.deadlock-api.com/v1/players/${accountId}/match-history`);
            if (!res.ok) throw new Error('API Error');

            const matches = await res.json();
            const stats = calculateStats(matches);

            setCache(stats);
            return stats;
        } catch (err) {
            console.error('Failed to fetch stats:', err);
            return null;
        }
    }

    function calculateStats(matches) {
        const wins = matches.filter(m => m.match_result).length;
        const losses = matches.length - wins;
        const kills = matches.reduce((sum, m) => sum + (m.player_kills || 0), 0);
        const deaths = matches.reduce((sum, m) => sum + (m.player_deaths || 0), 0);
        const assists = matches.reduce((sum, m) => sum + (m.player_assists || 0), 0);

        return {
            totalMatches: matches.length,
            wins,
            losses,
            winRate: (wins / matches.length * 100).toFixed(1),
            kda: ((kills + assists) / Math.max(deaths, 1)).toFixed(2),
            avgKills: (kills / matches.length).toFixed(1),
            avgDeaths: (deaths / matches.length).toFixed(1),
            avgAssists: (assists / matches.length).toFixed(1),
            recentMatches: matches.slice(0, 10),
            lastUpdated: Date.now()
        };
    }

    function getCache() {
        try {
            const cached = localStorage.getItem(CACHE_KEY);
            if (!cached) return null;

            const data = JSON.parse(cached);
            if (Date.now() - data.lastUpdated > CACHE_DURATION) {
                localStorage.removeItem(CACHE_KEY);
                return null;
            }
            return data;
        } catch {
            return null;
        }
    }

    function setCache(data) {
        try {
            localStorage.setItem(CACHE_KEY, JSON.stringify(data));
        } catch {}
    }

    return {
        fetch: fetchStats,
        clearCache: () => localStorage.removeItem(CACHE_KEY)
    };
})();