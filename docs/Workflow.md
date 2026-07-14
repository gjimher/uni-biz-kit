# UniBizKit Workflow System

UniBizKit provides a simple, model-driven workflow system that can be added to any business concept.

## Overview

A workflow defines a sequence of states that a concept can go through. For each state, it defines which roles have "ownership" of the record. If a user's role is not among the owners of the current state, they lose edit permissions for that record, effectively making it read-only.

## Configuration

Workflows are defined in `workflow.jsonc`.

### Schema

The workflow configuration consists of an array of `workflow_rules`, each containing:

*   **name**: Unique name for the workflow type.
*   **concepts**: Comma-separated list of concept names that use this workflow.
*   **states**: Ordered list of states.
    *   **name**: State identifier.
    *   **owners**: List of roles that can edit the record in this state.
    *   **assigners**: List of roles that can change the task owner (see [Task Assignment](#task-assignment)) in this state. An empty list disables assignment for the state.
    *   **retain_task_owner** (optional, default `false`): when entering this state, keep the previous task owner instead of clearing it back to the assignable pool.

### Example

```json
{
  "workflow_rules": [
    {
      "name": "order_workflow",
      "concepts": "order",
      "states": [
        { "name": "initial", "owners": ["user", "admin"], "assigners": [] },
        { "name": "ordered", "owners": ["admin"], "assigners": ["admin"] },
        { "name": "accepted", "owners": ["admin"], "assigners": ["admin"] },
        { "name": "sent", "owners": ["admin"], "assigners": ["admin"] },
        { "name": "delivered", "owners": ["admin"], "assigners": ["admin"] }
      ]
    }
  ]
}
```

## Task Assignment

Each workflow record can have a **task owner**: the user responsible for moving the workflow forward while the record is in its current state.

*   The owner is stored in the injected `state_task_owner` field as a plain **email** (no foreign key), so the user database can live outside the model (SSO, LDAP, future model federation).
*   Only users with a role in the current state's `assigners` can change it. This is enforced in the database (security trigger) and reflected in the UI.
*   An assigner who is not an owner of the state can change *only* the task owner; the rest of the record stays read-only for them.
*   On a state transition the task owner is cleared back to the assignable pool, unless the target state sets `retain_task_owner: true`.

### Task pages

Two built-in admin pages can be linked from the [custom menu](Frontend.md) using the `workflow` menu item property:

```json
{
  "label": "Tasks",
  "children": [
    { "label": "Assignable tasks", "workflow": "assignable_tasks" },
    { "label": "My tasks", "workflow": "my_tasks" }
  ]
}
```

*   **assignable_tasks**: unassigned records (`state_task_owner` is null) in states where the user can assign, with an *Assign to me* button per row.
*   **my_tasks**: records whose task is assigned to the logged-in user.

Both are standard list views (server-side filtering by concept, state and record text, sorting and pagination) backed by the generated `_workflow_tasks` SQL view: a UNION of every workflow concept with the concept as a column and the current state's `assigners` baked in as an array. The view uses `security_invoker`, so each user only sees the records their row-level security already allows.

### User directory

Assignment suggestions come from the `_user_directory` table, a **discovery cache** (never a source of truth or a security input): email, auth uuid, last known roles, source and last login. It is filled by the model's seed users and refreshed on every login by the access token hook; an external directory synchronization (LDAP/IdC/CDC, see [Roadmap](Roadmap.md)) can feed the same table later. The assignment autocomplete suggests directory users whose roles own the current state, but accepts any email (free entry), so users unknown to the cache can still be assigned.

### Email notification

When the task owner changes and the change is not a self-assignment, a database trigger calls the `task-assigned-email` [backend function](Backend.md#backend-functions), which emails the new owner (sender and edit link included). SMTP settings and the app URL come from the `SMTP_*` / `APP_BASE_URL` environment variables in production (wired into the generated docker-compose from [`system.jsonc`](Deployment.md#runtime-configuration-systemjsonc)) and fall back to the development SMTP mock.

## Backend Implementation

When a concept has an associated workflow, the `SchemaProcessor` automatically injects three fields:

1.  **state**: A `TEXT` column storing the current state name. It defaults to the first state defined in the workflow.
2.  **state_info**: An `XML` column storing the transition history.
3.  **state_task_owner**: The email of the user assigned to the workflow task (see [Task Assignment](#task-assignment)).

Transitions are applied by the `workflow-transition` [backend function](Backend.md#backend-functions), which verifies state ownership and runs the [business rules](Backend.md#business-rules-rulesjsonc) bound to the transition (`when: ["on_state_changed_to_<state>"]`).

## Frontend Implementation

Concepts with workflows feature a `WorkflowSelector` component at the top of their Edit forms.

*   **State Transitions**: Users can move the record to the previous or next state in the sequence.
*   **Transition Notes**: When changing state, a text field appears to enter an optional note.
*   **History**: Hovering over the current state shows the details of the last transition (user, date, and note).
*   **Permissions**: If the current user does not have a role that "owns" the current state, the workflow selector and all other form fields are disabled.
*   **Task Owner**: Assigners see a free-entry email autocomplete and an *Assign to me* button; other users see the current task owner read-only.

## Design Principles

*   **Restrictive Roles**: The workflow system only *removes* edit permissions. It never grants more permissions than those defined in [`security.jsonc`](Security.md).
*   **Transparency**: Transition history is stored in an XML format in the database for auditing purposes.
