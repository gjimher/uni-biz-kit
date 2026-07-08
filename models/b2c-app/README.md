# B2C App — Storefront Demo

A simple but complete **B2C e-commerce** application: catalog with categories, collections and per-variant pricing/stock, a shopping-cart-to-delivery order workflow, coupons, shipping methods, payments and moderated product reviews.

It pairs the generated **React-Admin backoffice** with a hand-written **customer storefront** ([`presentation/pages/`](presentation/pages)) — both talking to the same [Supabase backend](../../docs/Backend.md), which enforces the same rules for shoppers and admins alike. It is served under `base_uri: /b2c` and is one of the [live demos](../ubk-app/index.md).

## Domain

`category`, `collection`, `product`, `product_variant`, `customer`, `address`, `coupon`, `shipping_method`, `order`, `order_item`, `review`. The `order` in its `initial` workflow state doubles as the shopping cart; on checkout it charges the buyer (payment [edge function](../../docs/Backend.md#edge-functions)), computes discounts and totals, and locks the grand total. See [Workflow.md](../../docs/Workflow.md) for the order lifecycle and [Backend.md](../../docs/Backend.md) for the model format.

## How it was built

The model was implemented by an **LLM coding harness** from a **global functional description** — "a realistic B2C shop with cart, coupons, payments and reviews" — rather than a field-by-field spec, and then verified by **functional review** of the running application. The exhaustive, technically-specified counterpart is [test-app](../test-app/README.md).
