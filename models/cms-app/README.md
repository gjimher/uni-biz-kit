# CMS App — Company News Demo

A minimal **content manager**: employees publish news and other company content (markdown body plus photos) and browse it by date, category or author. It is the smallest of the demo models — three concepts and the generated backoffice — served under `base_uri: /cms`.

## Domain

`employee` (author profile, linked to a registered user), `category` (grouping/filtering), and `article` (title, summary, [markdown](../../docs/Backend.md#field-types) body and photo [documents](../../docs/Backend.md#concept-properties)). Two roles: `admin` (full access) and `editor` (writes and publishes content). See [Backend.md](../../docs/Backend.md) for the model format and [Security.md](../../docs/Security.md) for the roles.

## How it was built

The model was implemented by an **LLM coding harness** from a **global functional description** and verified by **functional review** of the running application. Like [intranet-app](../intranet-app/README.md), it was produced **correctly on the first attempt**.
