# Marketing RAW Sources — Demo Dataset

A compact set of **un-modeled RAW source tables** for the Factoria manual demo.
Covers a fictional e-commerce company's marketing and order data for 2023–2024.

The agent workflow derives the star schema from these files — the operator uploads the
RAW CSVs and lets TICKET_INTAKE → DESIGN_REVIEW → BUILD → QA produce the dim/fact models.

Total rows: ~744 across 5 files.

---

## Tables

### `raw_customers.csv` (110 rows)
**Grain:** one row per customer lifecycle event (CDC feed — emails repeat with updated ltv/segment)
**Key column:** `customer_email` (not unique — use MAX(event_id) or latest signup_ts to deduplicate)

| Column | Type | Notes |
|---|---|---|
| `event_id` | string | Surrogate row key, e.g. `CE0001` |
| `customer_email` | string | Natural key; ~30 rows are updates to existing emails |
| `full_name` | string | May change across rows for same email |
| `signup_ts` | timestamp | ISO-8601 UTC, e.g. `2023-04-12T09:23:00Z` |
| `country_code` | string | ISO 2-letter |
| `segment_tag` | string | Enterprise / Mid-Market / SMB / Consumer |
| `lifetime_spend_usd` | decimal | Cumulative — later rows supersede earlier ones |

**Quirk:** ~30 update rows share an email with an earlier row but carry a newer `signup_ts` and higher `lifetime_spend_usd`. The DesignAgent should propose deduplication logic.

---

### `raw_campaign_spend.csv` (109 rows)
**Grain:** one row per campaign per day
**Key column:** `spend_id`

| Column | Type | Notes |
|---|---|---|
| `spend_id` | string | Surrogate row key, e.g. `SP0001` |
| `campaign_id` | string | e.g. `CAM01` — joins to `raw_orders.campaign_id` |
| `campaign_name` | string | Human-readable |
| `channel` | string | email / paid_search / social / display |
| `spend_date` | date | YYYY-MM-DD |
| `impressions` | integer | Daily impressions |
| `clicks` | integer | Daily clicks |
| `spend_usd` | decimal | Daily spend |
| `target_segment` | string | Matches `raw_customers.segment_tag` |

**Quirk:** Spend is daily-grain; ROI analysis requires aggregating to campaign-level before joining to orders.

---

### `raw_orders.csv` (150 rows)
**Grain:** one row per order
**Key column:** `order_id`
**Join keys:** `customer_email → raw_customers`, `campaign_id → raw_campaign_spend`

| Column | Type | Notes |
|---|---|---|
| `order_id` | string | e.g. `ORD0001` |
| `customer_email` | string | FK to raw_customers (use deduped dim_customer) |
| `order_ts` | timestamp | ISO-8601 UTC |
| `order_date` | date | YYYY-MM-DD |
| `channel` | string | Acquisition channel |
| `campaign_id` | string | Nullable — some orders not campaign-attributed |
| `campaign_name` | string | Denormalized; nullable |
| `status` | string | completed / returned / cancelled |
| `currency` | string | Always USD in this dataset |
| `amount_usd` | decimal | Order total |
| `is_refund` | integer | 1 if status = returned, else 0 |

---

### `raw_order_items.csv` (200 rows)
**Grain:** one row per line item
**Key column:** `item_id`
**Join key:** `order_id → raw_orders`

| Column | Type | Notes |
|---|---|---|
| `item_id` | string | e.g. `ITEM0001` |
| `order_id` | string | FK to raw_orders |
| `sku` | string | e.g. `SKU-001` |
| `product_name` | string | Display name |
| `category` | string | Electronics / Apparel / Software / Tools / Parts |
| `quantity` | integer | Units ordered |
| `unit_price_usd` | decimal | Price per unit |
| `line_total_usd` | decimal | quantity × unit_price_usd |

---

### `raw_web_sessions.csv` (175 rows)
**Grain:** one row per web session
**Key column:** `session_id`
**Join keys:** `customer_email → raw_customers` (nullable — anonymous visitors), `campaign_id → raw_campaign_spend` (nullable), `order_id → raw_orders` (nullable — only when converted=1)

| Column | Type | Notes |
|---|---|---|
| `session_id` | string | e.g. `SES0001` |
| `customer_email` | string | Nullable (anonymous sessions) |
| `session_ts` | timestamp | ISO-8601 UTC |
| `session_date` | date | YYYY-MM-DD |
| `utm_source` | string | google / direct / email / instagram / facebook / referral |
| `campaign_id` | string | Nullable |
| `page_views` | integer | Pages viewed in session |
| `duration_sec` | integer | Session length in seconds |
| `converted` | integer | 1 = placed an order, 0 = no purchase |
| `order_id` | string | Nullable — populated when converted=1 |

---

## Suggested Demo Ticket

```json
{
  "ticket_kind": "DATA_ENGINEERING",
  "title": "Marketing ROI — Revenue and Conversions by Campaign and Channel",
  "description": "From five raw source tables, build a gold-layer star schema: deduplicate customers, aggregate campaign spend, join orders to sessions, and compute attributed revenue, conversion rate, and ROI per campaign per month.",
  "grain": "one row per campaign per channel per month",
  "metrics": [
    "attributed_revenue: sum of raw_orders.amount_usd where campaign_id matches, excluding refunds and cancellations",
    "session_count: count of raw_web_sessions",
    "conversion_rate: sum(converted) / count(session_id)",
    "campaign_roi: attributed_revenue / sum(raw_campaign_spend.spend_usd) per campaign"
  ],
  "constraints": [
    "Exclude cancelled and returned orders (status IN ('cancelled','returned'))",
    "Deduplicate raw_customers by customer_email — keep the row with the latest signup_ts",
    "Only include sessions from 2023-01-01 onwards",
    "Attribute revenue to a campaign only when raw_orders.campaign_id is not null"
  ]
}
```

## Derived Models the Agents Should Produce

| Model | Grain | Source(s) |
|---|---|---|
| `dim_customer` | one row per customer_email | raw_customers (deduped) |
| `dim_campaign` | one row per campaign_id | raw_campaign_spend (aggregated) |
| `fct_orders` | one row per order | raw_orders + dim_customer + dim_campaign |
| `fct_campaign_performance` | one row per campaign per month | fct_orders + raw_campaign_spend |
| `fct_web_sessions` | one row per session | raw_web_sessions + dim_customer + dim_campaign |

## Upload Order

Upload in this order so the agents see join-key context when profiling:
1. `raw_customers.csv`
2. `raw_campaign_spend.csv`
3. `raw_orders.csv`
4. `raw_order_items.csv`
5. `raw_web_sessions.csv`
