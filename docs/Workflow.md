# UniBizKit Workflow System

UniBizKit provides a simple, model-driven workflow system that can be added to any business concept.

## Overview

A workflow defines a sequence of states that a concept can go through. For each state, it defines which roles have "ownership" of the record. If a user's role is not among the owners of the current state, they lose edit permissions for that record, effectively making it read-only.

## Configuration

Workflows are defined in `workflow.json`.

### Schema

The workflow configuration consists of an array of `workflows`, each containing:

*   **name**: Unique name for the workflow type.
*   **concepts**: List of concept names that use this workflow.
*   **states**: Ordered list of states.
    *   **name**: State identifier.
    *   **owners**: List of roles that can edit the record in this state.

### Example

```json
{
  "workflows": [
    {
      "name": "order_workflow",
      "concepts": ["order"],
      "states": [
        { "name": "initial", "owners": ["user", "admin"] },
        { "name": "ordered", "owners": ["admin"] },
        { "name": "accepted", "owners": ["admin"] },
        { "name": "sent", "owners": ["admin"] },
        { "name": "delivered", "owners": ["admin"] }
      ]
    }
  ]
}
```

## Backend Implementation

When a concept has an associated workflow, the `SchemaProcessor` automatically injects two fields:

1.  **state**: A `TEXT` column storing the current state name. It defaults to the first state defined in the workflow.
2.  **state_info**: An `XML` column storing the transition history.

## Frontend Implementation

Concepts with workflows feature a `WorkflowSelector` component at the top of their Edit forms.

*   **State Transitions**: Users can move the record to the previous or next state in the sequence.
*   **Transition Notes**: When changing state, a text field appears to enter an optional note.
*   **History**: Hovering over the current state shows the details of the last transition (user, date, and note).
*   **Permissions**: If the current user does not have a role that "owns" the current state, the workflow selector and all other form fields are disabled.

## Design Principles

*   **Restrictive Roles**: The workflow system only *removes* edit permissions. It never grants more permissions than those defined in `security.json`.
*   **Linear Flow**: By default, transitions are allowed only to the immediately preceding or succeeding state.
*   **Transparency**: Transition history is stored in an XML format in the database for auditing purposes.
