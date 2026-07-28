# Agile App — Software Project Management Demo

An **agile software project manager**: software projects with their boards, components and releases, issues of every type identified by the familiar `AGL-12` key, sprint planning with story points, and a kanban lifecycle enforced by the backend. It is the largest of the demo models — twelve concepts, two workflows and a custom portal on top of the generated backoffice.

## Domain

`project` (key, delivery type, rollups of issue count and open points) owns `board` (WIP limit and swimlane configuration), `component`, `version` (releases), `sprint` and `issue`. An `issue` carries type, priority, assignee, reporter, epic/parent self-[relations](../../docs/Backend.md#relationships), sprint, fix version, `component`/`label` many-to-many sets, estimates and [attachments](../../docs/Backend.md#concept-properties); its `issue_comment`, `work_log` and `issue_link` children hold the discussion, the logged time and the blocks/duplicates graph. `member` is the [profile concept](../../docs/Security.md#profile-concepts) shared by the `manager` and `member` roles, alongside `admin` and a read-only `viewer`.

Two [workflows](../../docs/Workflow.md) drive it: `issue_workflow` (`backlog → todo → in_progress → in_review → done`) and `sprint_workflow` (`planned → active → completed`), with FEEL [rules](../../docs/Backend.md#business-rules-rulesjsonc) acting as transition validators — a story needs an estimate to be ready, work in progress needs an assignee, closing needs a resolution, and a sprint needs dates to start. `project` is [versioned](../../docs/Backend.md#record-history), so the whole project aggregate keeps an issue history. See [Backend.md](../../docs/Backend.md) for the model format and [Security.md](../../docs/Security.md) for the roles.

## Portal pages

Beyond the generated backoffice, `presentation/pages` adds a private portal: **your work** (`/`), a drag-and-drop **kanban board** (`/priv/board`), **backlog and sprint planning** (`/priv/backlog`) and **reports** (`/priv/reports`). Dropping a card on another column calls the same `workflow-transition` backend function the backoffice selector uses, so board moves are validated by the workflow rules and a rejected move snaps back.

## How it was built

The model was implemented by an **LLM coding harness** from a **global functional description** and verified by **functional review** of the running application.
