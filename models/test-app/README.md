# Test App — Reference Model

A B2C e-commerce example that exercises all major UniBizKit features. It serves as both a learning reference and the integration test input (`pytest` reads from this directory).

This is the project's **development model**: it deliberately packs in every capability so the generators and the [test suite](../../docs/Development.md) have something to run against. Its model was built by an **LLM coding harness under code review**, from tasks specified in **precise technical detail** — as opposed to the demo models ([b2c-app](../b2c-app/README.md), [intranet-app](../intranet-app/README.md), [cms-app](../cms-app/README.md)), which were built from higher-level functional descriptions.

## How the complex parts are solved

The `order` concept is where most of the interesting mechanics come together. All of it is enforced **server-side** — the untrusted [frontend](../../docs/Frontend.md) only proposes changes; [edge functions](../../docs/Backend.md#edge-functions) and RLS decide what sticks.

| Requirement | How it is modelled | Where |
|-------------|--------------------|-------|
| Bind an order to the buyer, un-spoofably | `order.customer` uses `calculated: "copy_logged_on_insert(customer)"` — set to the logged-in user's profile at insert and then locked, so the client cannot assign an order to someone else | [Backend.md](../../docs/Backend.md#calculated-fields) |
| Keep the order total in sync with its lines | `order.total_amount` uses `calculated: "rollup(sum,order_item,total_price)"`, recomputed by a DB trigger whenever an `order_item.total_price` changes | [Backend.md](../../docs/Backend.md#calculated-fields) |
| Reuse a saved address without duplicating data entry | `shipping_address`/`billing_address` are `prefill` fields over `customer.addresses`: the buyer picks one saved address and its fields (street, city, province, country) are copied inline into the order | [Backend.md](../../docs/Backend.md#field-types) |
| Compute shipping with a rule that sees the whole order | `shipping_costs` uses `calculated: "by_rules"`; the `order-shipping-costs` FEEL rule reads `db.order.total_amount` (free shipping ≥ 60, else flat 6) and writes the field back — a business rule with access to the complete order, not just the field | [Backend.md](../../docs/Backend.md#business-rules-rulesjsonc) |
| Prevent order tampering after checkout | On the transition to `ordered`, `order-save-ordered-total-amount` snapshots the live total into `ordered_total_amount`; every later transition (`accepted`/`sent`/`delivered`) runs `order-check-ordered-total-amount`, a `check` rule that aborts if the total no longer matches the snapshot. Because rules compile to edge functions, the check cannot be skipped from the client | [Workflow.md](../../docs/Workflow.md), [Backend.md](../../docs/Backend.md#edge-functions) |

The shipping rule recalculates **asynchronously** (`when_async`) while the cart is open so the buyer is never blocked, then **synchronously** (`when`) one last time as the order is placed — see the trigger notes in `rules.jsonc`.
