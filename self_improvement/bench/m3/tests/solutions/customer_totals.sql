SELECT c.id, c.name, COALESCE(SUM(o.amount_cents), 0) AS total
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.id AND o.status = 'paid'
GROUP BY c.id, c.name
ORDER BY total DESC, c.id ASC;
