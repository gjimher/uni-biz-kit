# Intranet App — Employee Portal Demo

An **employee intranet**: people directory and org chart, work centers with their public-holiday calendars, vacation and paid-leave approval workflows, clock-in/clock-out time tracking with flexibility hours, sick leaves, internal news, and a simple HR/IT ticketing system.

Each concept is scoped to the role that owns it (HR, IT, employee), so what a user can see and do is decided by the generated [row-level security](../../docs/Security.md). It combines the generated backoffice with custom employee-facing pages ([`presentation/pages/`](presentation/pages)) and is served under `base_uri: /intranet` as one of the [live demos](../ubk-app/index.md).

## Domain

`work_center`, `holiday`, `employee`, `vacation_request`, `leave_request`, `work_log`, `sick_leave`, `ticket`, `category`, `article`. Two [workflows](../../docs/Workflow.md) drive it: `approval_workflow` (`draft → submitted → approved`) for vacation and leave requests, and `ticket_workflow` (`open → in_progress → resolved`) for the helpdesk. Balance [rules](../../docs/Backend.md#business-rules-rulesjsonc) reject requests that exceed the employee's remaining vacation or flex-hour allowance.

## How it was built

The model was implemented by an **LLM coding harness** from a **global functional description** and verified by **functional review** of the running application. Notably, it was produced **correctly on the first attempt**, with no iteration on the generated model.
