-- Named analytics queries. Each starts with "-- name: <query_name>".

-- name: monthly_revenue
-- Revenue per month with month-over-month growth (LAG window function).
WITH monthly AS (
    SELECT substr(o.order_date, 1, 7)                      AS month,
           COUNT(DISTINCT o.order_id)                      AS orders,
           SUM(i.quantity * i.unit_price_cents) / 100.0    AS revenue
    FROM fact_order o
    JOIN fact_order_item i USING (order_id)
    GROUP BY month
)
SELECT month,
       orders,
       ROUND(revenue, 2) AS revenue,
       ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY month))
             / LAG(revenue) OVER (ORDER BY month), 1) AS mom_growth_pct
FROM monthly
ORDER BY month;

-- name: top_products_by_category
-- Top 2 products per category by revenue (RANK window function).
WITH product_revenue AS (
    SELECT p.category,
           p.name,
           SUM(i.quantity)                               AS units,
           SUM(i.quantity * i.unit_price_cents) / 100.0  AS revenue
    FROM fact_order_item i
    JOIN dim_product p USING (sku)
    GROUP BY p.category, p.name
)
SELECT category, name, units, ROUND(revenue, 2) AS revenue, rnk
FROM (
    SELECT *, RANK() OVER (PARTITION BY category ORDER BY revenue DESC) AS rnk
    FROM product_revenue
)
WHERE rnk <= 2
ORDER BY category, rnk;

-- name: channel_mix
-- Share of revenue by channel (window SUM over the whole result).
SELECT o.channel,
       COUNT(DISTINCT o.order_id) AS orders,
       ROUND(SUM(i.quantity * i.unit_price_cents) / 100.0, 2) AS revenue,
       ROUND(100.0 * SUM(i.quantity * i.unit_price_cents)
             / SUM(SUM(i.quantity * i.unit_price_cents)) OVER (), 1) AS revenue_share_pct
FROM fact_order o
JOIN fact_order_item i USING (order_id)
GROUP BY o.channel
ORDER BY revenue DESC;

-- name: cohort_retention
-- Of customers whose first order was in a given quarter, what share ordered again
-- 1, 2 and 3 quarters later? NULL means that quarter hasn't happened yet in the data.
WITH orders_q AS (
    SELECT customer_id,
           CAST(substr(order_date, 1, 4) AS INTEGER) * 4
             + (CAST(substr(order_date, 6, 2) AS INTEGER) - 1) / 3 AS q
    FROM fact_order
),
first_q AS (
    SELECT customer_id, MIN(q) AS cohort_q FROM orders_q GROUP BY customer_id
),
activity AS (
    SELECT DISTINCT f.customer_id, f.cohort_q, o.q - f.cohort_q AS q_offset
    FROM first_q f JOIN orders_q o USING (customer_id)
),
last_q AS (SELECT MAX(q) AS max_q FROM orders_q)
SELECT (cohort_q / 4) || '-Q' || (cohort_q % 4 + 1) AS cohort,
       SUM(q_offset = 0) AS customers,
       CASE WHEN cohort_q + 1 <= max_q
            THEN ROUND(100.0 * SUM(q_offset = 1) / SUM(q_offset = 0), 1) END AS q1_retention_pct,
       CASE WHEN cohort_q + 2 <= max_q
            THEN ROUND(100.0 * SUM(q_offset = 2) / SUM(q_offset = 0), 1) END AS q2_retention_pct,
       CASE WHEN cohort_q + 3 <= max_q
            THEN ROUND(100.0 * SUM(q_offset = 3) / SUM(q_offset = 0), 1) END AS q3_retention_pct
FROM activity, last_q
GROUP BY cohort_q
ORDER BY cohort_q;
