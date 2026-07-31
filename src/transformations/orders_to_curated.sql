select
    cast(order_id as varchar) as order_id,
    cast(customer_id as varchar) as customer_id,
    cast(order_total as decimal(18, 2)) as order_total,
    current_timestamp as loaded_at
from raw_orders
where order_status = 'COMPLETE';
