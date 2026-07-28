# CRM App — Customer Relationship Management Demo

A **customer relationship manager** in the shape sales, service and field teams know: leads that
convert into an account, a contact and a deal; an opportunity pipeline whose stage drives
probability and forecast category; products, price books, bundles, discount grids and quotes;
contracts, orders, invoices, payments and subscriptions; support cases with their SLA
commitments, a knowledge base, and work orders dispatched to technicians on site. It is by far
the largest demo model — **68 concepts, four workflows and seven roles** — with a tailored
portal on top of the generated backoffice.

## Domain

`account` is the aggregate root: it owns `contact`, `account_address`, `account_team_member`,
`partner`, `opportunity` (with its line items, contact roles, competitors, team, splits,
campaign influence and `quote` → `quote_line`), `contract`, `sales_order` → `order_line`,
`invoice` → `invoice_line`/`payment`/`credit_memo`, `subscription`, `asset`, `entitlement`,
`service_contract` and `support_case` (comments, emails, SLA milestones, case team) plus the
`work_order` → `work_order_line` → `product_consumed` chain of field service. `lead` stands
outside that tree until it is converted; `territory` is a **tree of itself**; `campaign`,
`price_book`, `product` (with its bundle features and options), `discount_schedule`,
`business_hours`, `skill`, `work_type` and `service_resource` are the catalogues the rest hangs
from. `sales_rep` is the [profile concept](../../docs/Security.md#profile-concepts) shared by
the `sales_manager`, `sales_rep`, `marketing`, `support` and `field_tech` roles, alongside
`admin` and a read-only `executive`.

Four [workflows](../../docs/Workflow.md) turn the operating rules into mandatory business
controls:

* **Opportunity** — `prospecting → qualification → needs_analysis → proposal → negotiation →
  closed`. A proposal needs a value and at least one product line; negotiation needs an owner
  and a documented next step; closing records whether the deal was won or lost and, for a loss,
  why.
* **Support case** — `new → working → escalated → closed`. Escalating requires a reason, while
  closing requires a resolution code so service outcomes remain reportable.
* **Work order** — `new → dispatched → in_progress → completed`. Dispatch requires a booked
  appointment and a scheduled start; completion requires the work performed and the time spent
  on site.
* **Invoice** — `draft → issued → paid`. An invoice cannot be issued without lines and a due
  date, or marked as paid while it still has an outstanding balance.

`account` keeps the history of the complete customer file, including the records that belong to
it, so commercial and service changes remain auditable.

## Business capabilities

* **Lead conversion** — a qualified lead becomes an account, a contact and a first opportunity
  in one action. An existing account with the same company name is reused, previous activities
  remain attached to the resulting customer relationship, and repeating the action cannot
  create duplicates.
* **Stage-driven forecasting** — `probability`, `forecast_category` and `expected_revenue` are
  derived from the opportunity stage, so moving a deal automatically updates the weighted
  pipeline and forecast without maintaining a separate set of figures.
* **Price books** — each sale line keeps the list price that applied when it was added, so
  repricing the catalogue never rewrites an agreed price or discount.
* **Account health** — `contact_count`, `open_pipeline`, `won_revenue`, `open_case_count` and
  `outstanding_balance` stay up to date automatically as the customer relationship changes.
* **Money that adds up** — an invoice's `subtotal` rolls up its lines, `paid_amount` rolls up the
  *cleared* payments (a declined card contributes nothing) and `balance` is what is left; the
  workflow refuses to mark an invoice as paid while it is above zero.
* **Address validation** — billing country, state and city must match an allowed combination.
* **Reporting** — three read-only reports follow every open deal, highlight active SLA
  commitments and breaches, and group invoiced and outstanding revenue by quarter and product.
* **Territories** — sales territories form a hierarchy with paths such as `EMEA / Iberia`, and
  accounts and representatives can be assigned to the appropriate level.
* **Saved addresses** — orders and field jobs can reuse an account address, avoiding repeated
  entry while preserving the delivery or service destination on the transaction.
* **Managed catalogues** — SLA milestone types and email templates form part of the deployed
  business configuration, so every environment starts with the expected reference data.
* **Payments** — the amount charged is always the invoice's current outstanding balance, and
  cleared payments reduce that balance automatically. The demo console includes a payment
  simulator for exercising the full flow.
* **Activity capture** — *Log a call* is available directly from contacts, accounts, leads and
  opportunities, creating a completed activity against the customer record.

## Portal pages

Beyond the generated backoffice, the application adds a private portal: a **sales console**
with your pipeline, quota attainment, activities, leads, cases and the outstanding invoices
you can charge by card; a drag-and-drop **pipeline kanban**; a **forecast** by category, by rep
and by win/loss; and a **service console** with the SLA queue, the dispatch board and the
knowledge base. Moving a card applies the same business controls as changing its stage in the
backoffice, and a rejected move snaps back. Because closing needs an outcome, the last column
is split into Won and Lost drop zones that collect it (and the loss reason) before the move.
Dispatching a job from the service console applies the same controls.

## How it was built

The model was implemented by an **LLM coding harness** from a **global functional description**
and verified by **functional review** of the running application.
