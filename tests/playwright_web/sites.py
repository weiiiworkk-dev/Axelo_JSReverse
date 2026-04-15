"""
高难度目标站点配置 — 面向系统通用逆向能力的极限压测。

选取依据（均来自平台官方声明）：
  - Google Search/Maps  : "Unusual traffic" → reCAPTCHA
  - LinkedIn            : 明确禁止第三方自动化 scraping，账号风控成熟
  - Instagram           : 未经许可不得以自动化方式收集信息（Meta 官方条款）
  - X / Twitter         : 非 API 路径自动化可能导致永久封号
  - Ticketmaster        : 票务反爬军备竞赛最激烈类型之一
  - Airbnb              : 禁止 bots/crawlers/scrapers（官方条款）
  - Booking.com         : 禁止 automated means / automated assistants（官方条款）
  - Zillow              : 明确禁止 automated queries 与 CAPTCHA 绕过（官方条款）
  - Indeed              : 禁止 automation/scripting/bots（官方条款）

所有 goal 描述以"逆向工程机制"为核心，符合系统定位：
不绑定任何特定 API 路径，系统须凭通用逆向能力自主发现。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SiteConfig:
    name: str
    url: str
    goal: str
    stealth: str = "high"
    js_rendering: str = "auto"
    verify: bool = True
    # 额外描述：反爬难度特征，用于测试报告
    challenge_profile: str = ""
    # 预期挑战类型（用于断言宽松化）
    expected_challenges: list[str] = field(default_factory=list)
    # 高风险站点超时更长（秒）
    mission_timeout_sec: int = 720  # 12 分钟


SITES: list[SiteConfig] = [
    SiteConfig(
        name="google_search",
        url="https://www.google.com/search?q=laptop+review+2024",
        goal=(
            "Reverse engineer Google Search's result API transport mechanism. "
            "Identify: (1) how search results are fetched (XHR/fetch vs SSR), "
            "(2) session/auth tokens in request headers, "
            "(3) anti-bot challenge type and resolution mechanism (reCAPTCHA v2/v3/Enterprise), "
            "(4) request signing or fingerprinting parameters. "
            "Extract schema: title, url, snippet, position for organic results."
        ),
        stealth="high",
        js_rendering="auto",
        challenge_profile="reCAPTCHA Enterprise, behavioral analysis, IP reputation",
        expected_challenges=["recaptcha", "challenge", "unusual_traffic"],
        mission_timeout_sec=600,
    ),
    SiteConfig(
        name="google_maps",
        url="https://www.google.com/maps/search/coffee+shop+near+me",
        goal=(
            "Reverse engineer Google Maps' Place search API transport. "
            "Identify: (1) the internal RPC/proto API endpoint for place search, "
            "(2) request payload structure (protobuf/JSON), "
            "(3) session tokens, device fingerprinting, and behavioral anti-abuse signals, "
            "(4) how location context is embedded in requests. "
            "Schema: place_id, name, rating, address, lat/lng, review_count."
        ),
        stealth="high",
        js_rendering="auto",
        challenge_profile="reCAPTCHA, behavioral/location signals, protobuf transport",
        expected_challenges=["recaptcha", "automated_queries"],
        mission_timeout_sec=720,
    ),
    SiteConfig(
        name="linkedin_jobs",
        url="https://www.linkedin.com/jobs/search/?keywords=software+engineer&location=United+States",
        goal=(
            "Reverse engineer LinkedIn's job search API and authentication mechanism. "
            "Identify: (1) the job search API endpoint and request signing (JSESSIONID, li_at cookie), "
            "(2) anti-scraping token generation in JS (voyager API), "
            "(3) rate-limiting signals and account-based access gates, "
            "(4) fingerprinting based on device identity and behavioral graph. "
            "Schema: job_id, title, company, location, posted_at, applicant_count."
        ),
        stealth="high",
        js_rendering="auto",
        challenge_profile="Account-dependent, identity graph, voyager API auth, behavioral model",
        expected_challenges=["login_required", "auth_gate", "rate_limit"],
        mission_timeout_sec=720,
    ),
    SiteConfig(
        name="instagram_explore",
        url="https://www.instagram.com/explore/tags/technology/",
        goal=(
            "Reverse engineer Instagram's explore/hashtag API transport. "
            "Identify: (1) the GraphQL or internal API endpoint for hashtag content, "
            "(2) session tokens (csrftoken, sessionid, ds_user_id) and how they're generated, "
            "(3) device fingerprint signals (ig_did, mid, app_id), "
            "(4) login wall detection and bypass feasibility analysis. "
            "Schema: post_id, shortcode, owner_id, like_count, comment_count, media_url."
        ),
        stealth="high",
        js_rendering="auto",
        challenge_profile="Meta login wall, ig_did device fingerprint, GraphQL API, CSRF rotation",
        expected_challenges=["login_required", "auth_gate", "graphql_auth"],
        mission_timeout_sec=600,
    ),
    SiteConfig(
        name="twitter_search",
        url="https://twitter.com/search?q=artificial+intelligence&src=typed_query&f=live",
        goal=(
            "Reverse engineer X/Twitter's search API transport mechanism. "
            "Identify: (1) the internal GraphQL endpoint for search (SearchTimeline), "
            "(2) bearer token generation and ct0 CSRF token rotation, "
            "(3) guest token vs authenticated token paths, "
            "(4) rate limit headers and retry-after signals, "
            "(5) anti-automation detection via JS challenge or behavioral analysis. "
            "Schema: tweet_id, author, text, created_at, retweet_count, like_count."
        ),
        stealth="high",
        js_rendering="auto",
        challenge_profile="GraphQL API, bearer token, ct0 CSRF, guest_token gate, rate limits",
        expected_challenges=["auth_gate", "rate_limit", "challenge"],
        mission_timeout_sec=600,
    ),
    SiteConfig(
        name="ticketmaster",
        url="https://www.ticketmaster.com/search?q=concert+2024",
        goal=(
            "Reverse engineer Ticketmaster's event search and inventory API. "
            "Identify: (1) the Discovery API or internal endpoint for event search, "
            "(2) anti-bot challenge chain: queue-it, Arkose Labs / FunCaptcha, or reCAPTCHA, "
            "(3) session token and device fingerprint generation in JS bundle, "
            "(4) inventory polling mechanism and signing parameters. "
            "Schema: event_id, name, date, venue, price_range, available_tickets."
        ),
        stealth="high",
        js_rendering="auto",
        challenge_profile="Queue-it, Arkose Labs/FunCaptcha, device reputation, inventory anti-bot",
        expected_challenges=["captcha", "queue", "challenge", "arkose"],
        mission_timeout_sec=720,
    ),
    SiteConfig(
        name="airbnb",
        url="https://www.airbnb.com/s/New-York--NY--United-States/homes?checkin=2024-12-01&checkout=2024-12-05",
        goal=(
            "Reverse engineer Airbnb's listing search API transport. "
            "Identify: (1) the StaysSearch GraphQL operation and variable schema, "
            "(2) session/device tokens (X-Airbnb-API-Key, _csrf_token, XSRF-TOKEN), "
            "(3) anti-scraping measures: Sift fraud signals, CDN challenge, behavioral fingerprint, "
            "(4) price/calendar API signing parameters. "
            "Schema: listing_id, name, price_per_night, rating, review_count, lat/lng, host_id."
        ),
        stealth="high",
        js_rendering="auto",
        challenge_profile="GraphQL API, Sift fraud detection, XSRF token, CDN WAF",
        expected_challenges=["challenge", "rate_limit", "waf"],
        mission_timeout_sec=720,
    ),
    SiteConfig(
        name="booking_com",
        url="https://www.booking.com/searchresults.html?ss=New+York&checkin=2024-12-01&checkout=2024-12-05",
        goal=(
            "Reverse engineer Booking.com's hotel search API transport. "
            "Identify: (1) the internal search API endpoint (searchresults.en-gb.json or similar), "
            "(2) session management: bkng cookie, auth token, XSRF token rotation, "
            "(3) anti-automation fingerprint (Akamai Bot Manager, device signals), "
            "(4) rate limit and IP reputation signals. "
            "Schema: hotel_id, name, price_per_night, star_rating, review_score, location, availability."
        ),
        stealth="high",
        js_rendering="auto",
        challenge_profile="Akamai Bot Manager, bkng session, XSRF rotation, geo-pricing",
        expected_challenges=["challenge", "rate_limit", "akamai"],
        mission_timeout_sec=720,
    ),
    SiteConfig(
        name="zillow",
        url="https://www.zillow.com/new-york-ny/",
        goal=(
            "Reverse engineer Zillow's property listing API transport. "
            "Identify: (1) the GraphQL or REST endpoint for listing search (GetSearchPageState), "
            "(2) zgsession / x-zg-api-key token generation in JS bundle, "
            "(3) anti-scraping measures: CAPTCHA triggers, IP blocking, behavioral signals, "
            "(4) map-based search tile API and pagination mechanism. "
            "Schema: zpid, address, price, beds, baths, sqft, lat/lng, zestimate, days_on_zillow."
        ),
        stealth="high",
        js_rendering="auto",
        challenge_profile="GraphQL API, zgsession token, CAPTCHA on automation detection",
        expected_challenges=["captcha", "challenge", "rate_limit"],
        mission_timeout_sec=720,
    ),
    SiteConfig(
        name="indeed_jobs",
        url="https://www.indeed.com/jobs?q=software+engineer&l=New+York%2C+NY",
        goal=(
            "Reverse engineer Indeed's job search API transport. "
            "Identify: (1) the Mosaic/Volley API endpoint for job search, "
            "(2) session tokens: CTK, indeed_rcc, authtoken and their generation logic, "
            "(3) anti-automation measures: PerimeterX / HUMAN Security bot protection, "
            "(4) sponsored vs organic result differentiation in API response. "
            "Schema: job_key, title, company, location, salary_range, posted_at, easy_apply."
        ),
        stealth="high",
        js_rendering="auto",
        challenge_profile="PerimeterX/HUMAN Security, CTK token, behavioral JS fingerprint",
        expected_challenges=["challenge", "perimeter_x", "rate_limit"],
        mission_timeout_sec=720,
    ),
]

SITE_MAP: dict[str, SiteConfig] = {s.name: s for s in SITES}
