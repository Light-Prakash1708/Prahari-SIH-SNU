# PRAHARI — production weather configuration

Written 17 November 2026. Prices and limits were read from the providers' own pages on that date (sources at the end). Check them again before paying.

## Why risk does not run on production today

- **The models need 21 days of past hourly weather:** temperature, relative humidity and rain. A shorter series changes what TOMCAST and the degree-day models compute, so PRAHARI refuses to run them on one.
- **WeatherAPI free plan:** history is "Past day" only.
- **Open-Meteo free tier:** answers HTTP 429 to Render's shared outbound IP, even on the first request after a restart (Render logs, 17 Nov 05:29 UTC).
- **The archive (migration 008):** it keeps every observed past day it receives, per cell of about 1 km. In production it has not been filled for any cell yet (`missing: 20, found: 0`).
- **Result:** production shows the forecast but no disease-risk level. It says why, and it does not invent one. `WEATHER_DEMO_FALLBACK` is off on the live service, and the code ignores it in production anyway.

## Option A — Open-Meteo commercial API (recommended)

**How PRAHARI asks for history:**
- It uses the **Forecast API** with `past_days=21` (`OpenMeteoProvider`).
- Open-Meteo documents `past_days` as "Integer (0-92)". 21 is well inside that.
- One request returns the full 21-day hourly history plus the forecast.
- PRAHARI does **not** use the separate Historical Weather (archive) API.

**Which plan:**
- Open-Meteo's pricing page puts the Historical Weather API on Professional or higher. PRAHARI does not need that API, so **API Standard is sufficient**.
- Paid plans use a key on the dedicated `customer-api.open-meteo.com` host.

| Plan | Calls / month | Historical (archive) API | Price |
|---|---|---|---|
| Free | 300,000 (10,000/day); non-commercial only | Yes | Free |
| API Standard | 1M | No (not needed by PRAHARI) | Shown at Stripe checkout; not printed on the page |
| API Professional | 5M | Yes | Shown at checkout |

**What the data is:**
- Past days from the Forecast API are the provider's archived model data for that grid point. They are not readings from a station in the field.
- That was already true of the free tier PRAHARI used before.
- The payload names the source on every day.

**Configuration** (Render dashboard → `prahari` → Environment; never commit the key):

```
OPEN_METEO_API_KEY=<from your Open-Meteo account>
WEATHER_API_URL=https://customer-api.open-meteo.com/v1/forecast
```

The code already sends `apikey` whenever `OPEN_METEO_API_KEY` is set (`weather.py`, `OpenMeteoProvider.series`).

**Volume:**
- One call covers one field cell for the 90-minute cache window.
- Even 500 fields refreshed every 90 minutes is about 240,000 calls a month, inside Standard's 1M.

## Option B — WeatherAPI paid plan

| Plan | Price | Calls / month | History depth |
|---|---|---|---|
| Free | $0 | 100,000 | Past day |
| Starter | $7 / month | 3 million | **Past 7 days**: not enough for 21 days |
| Pro+ | $25 / month | 5 million | Past 365 days |
| Business | $65 / month | 10 million | Since 1 Jan 2010 |

- **Pro+ is the cheapest WeatherAPI plan that covers 21 days.**
- **Request cost:** WeatherAPI returns one past day per history request, so a 21-day window costs 21 calls per cell per refresh.
- **Data source:** WeatherAPI's FAQ states its historical data "is made up of forecast data and not from actual data". Say this if asked where risk-model inputs come from.

**Configuration:**
```
WEATHER_API_KEY=<WeatherAPI key, already set>
WEATHERAPI_HISTORY_DAYS=21
WEATHERAPI_MAX_HISTORY_CALLS=21
```

## Option C — let the archive build the window (no cost, slow)

- **How it fills:** the archive stores each observed past day a live provider returns. On the free WeatherAPI plan that is one day ("yesterday") per request. A cell fills in after **21 consecutive days in which that cell was requested at least once**.
- **Gaps:** a missed day stays a gap until it ages out of the window. PRAHARI never interpolates it.
- **Starter (7-day history):** the first request stores 7 days, and the cell completes 14 days later.
- **What this needs:** something to request each active field at least once a day. Today only farmer traffic does that.
- **Verdict:** honest, but slow and fragile for a launch. Use it alongside A or B, not instead of them.

## Recommendation

**Open-Meteo API Standard (Option A).**
- It needs no code change.
- One request per cell per refresh.
- Hourly history up to 92 days.
- Well inside the call limits.

**If Open-Meteo's checkout price is unacceptable,** use WeatherAPI Pro+ ($25/month) with the three variables above.

**Under either option, keep:**
- the 21-day requirement;
- refusal when history is short;
- `WEATHER_DEMO_FALLBACK` unset or `false` on production.

## How to verify after setting credentials

1. **Readiness:** `/api/ready` → `checks.weather.historical.cooling_down_seconds` is absent.
2. **History length:** `/api/fields/<id>/weather` → `history_days` is 21 or more, and every day names its provider.
3. **Risk runs:** the "What should I do?" screen shows a model level instead of "Risk forecast needs more past weather than is available".
4. **Logs:** Render logs contain no "serving GENERATED weather" and no "rate limited".

## Sources

- Open-Meteo pricing: https://open-meteo.com/en/pricing
- Open-Meteo Forecast API (`past_days` 0–92): https://open-meteo.com/en/docs
- Open-Meteo Historical Weather API (delays, archive host): https://open-meteo.com/en/docs/historical-weather-api
- WeatherAPI pricing: https://www.weatherapi.com/pricing.aspx
