# CRM App — Customer Relationship Management Demo

A **customer relationship manager** in the shape sales, service and field teams know: leads that
convert into an account, a contact and a deal; an opportunity pipeline whose stage drives
probability and forecast category; products, price books, bundles, discount grids and quotes;
contracts, orders, invoices, payments and subscriptions; support cases with their SLA
commitments, a knowledge base, and work orders dispatched to technicians on site. It is by far
the largest demo model — **65 concepts plus 3 report views**, four workflows, seven roles and a
portal of four pages on top of the generated backoffice. Generated from it: **82 tables, 1,088
columns, 1,268 row-level security policies and 855 triggers**, of which the model declares no
SQL at all.

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

Four [workflows](../../docs/Workflow.md) drive it — `opportunity_workflow` (`prospecting →
qualification → needs_analysis → proposal → negotiation → closed`), `case_workflow` (`new →
working → escalated → closed`), `work_order_workflow` (`new → dispatched → in_progress →
completed`) and `invoice_workflow` (`draft → issued → paid`) — with FEEL
[rules](../../docs/Backend.md#business-rules-rulesjsonc) as transition validators: a deal needs
an amount and product lines to be proposed, an owner and a next step to be negotiated, an
outcome (and a reason when lost) to be closed; a case needs an escalation reason to be escalated
and a resolution code to be closed; a job needs a booked appointment to be dispatched and
recorded hours to be completed; and an invoice can only be marked paid when its balance —
a calculated column fed by the cleared payments — reaches zero. `account` is
[versioned](../../docs/Backend.md#record-history-and-versioning), so the whole customer file
keeps its history.

## CRM features, expressed in the model

* **Lead conversion** — `backend/actions/lead-convert.js`, a [backend action](../../docs/Backend.md#action-functions)
  on the lead: it creates (or reuses) the account, creates the contact and the opportunity with
  the caller's own permissions, moves the lead's activities onto them, and writes the conversion
  audit trail with the privileged client because those fields are read-only for everyone else.
* **Stage-driven forecasting** — `probability`, `forecast_category` and `expected_revenue` are
  [calculated fields](../../docs/Backend.md#calculated-fields) over the workflow state, so the
  standard stage → probability → category mapping is a property of the data. Plain SQL rather
  than a rule on purpose: rules only run for authenticated writes, so seeded, imported or
  integrated records would otherwise have an empty forecast.
* **Price books** — a line item points at a `price_book_entry`, and `copy(price_book_entry,
  unit_price, on_insert)` snapshots the list price at the moment of the sale, so repricing the
  book never rewrites an agreed discount.
* **Account health** — `contact_count`, `open_pipeline`, `won_revenue`, `open_case_count` and
  `outstanding_balance` are `rollup(...)` aggregates kept in step by triggers.
* **Money that adds up** — an invoice's `subtotal` rolls up its lines, `paid_amount` rolls up the
  *cleared* payments (a declined card contributes nothing) and `balance` is what is left; the
  workflow refuses to close an invoice while it is above zero.
* **Address validation** — `validations/account.csv` defines the valid billing
  country / state / city combinations, as in `models/b2c-app`.
* **Reporting** — three [view concepts](../../docs/Backend.md#view-concepts-view), ordinary
  generated lists that are read-only by construction: `pipeline_report` (a row per open deal,
  each opening its record), `sla_report` (commitments on open cases, where "already late" is
  decided in SQL with `CURRENT_TIMESTAMP` because a generated column cannot call `now()`) and
  `revenue_by_product` (an aggregate view: `concept`/`concept_id` are null together, so its rows
  stand for no record).
* **Territories** — `territory` is `part_of` itself, so the generated UI gives the tree selector
  and the recursive labels (`EMEA / Iberia`).
* **Addresses that prefill** — `account_address` (`plural_name: addresses`) feeds the
  [`prefill`](../../docs/Backend.md#field-types) blocks on `work_order` and `sales_order`: pick a
  saved address and its fields are inlined into the record.
* **Model-owned catalogues** — `deployed_data.jsonc` keeps the SLA milestone types and the email
  templates: they are upserted on every deployment, so deleting one in the UI brings it back.
* **Payments** — `system.jsonc` points the generated `payment` function at `invoice.balance`, and
  the console charges it through the development simulator.
* **Quick action** — `presentation/addons/log_a_call.jsx` puts a *Log a call* button on the
  contact, account, lead and opportunity lists, writing a completed activity linked to the row.

## Portal pages

Beyond the generated backoffice, `presentation/pages` adds a private portal: a **sales console**
(`/`) with your pipeline, quota attainment, activities, leads, cases and the outstanding
invoices you can charge by card; a drag-and-drop **pipeline kanban** (`/priv/pipeline`); a
**forecast** (`/priv/forecast`) by category, by rep and by win/loss; and a **service console**
(`/priv/service`) with the SLA queue, the dispatch board and the knowledge base. Dropping a card
calls the same `workflow-transition` backend function the backoffice selector uses, so a move is
validated by the model's rules and a rejected move snaps back — and because closing needs an
outcome, the last column is split into Won and Lost drop zones that collect it (and the loss
reason) before the transition. Dispatching a job from the service console works the same way.

## How it was built

The model was implemented by an **LLM coding harness** from a **global functional description**
and verified by **functional review** of the running application.
