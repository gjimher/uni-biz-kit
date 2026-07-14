# Roadmap

UniBizKit is intentionally developed in phases. See [docs/README.md](README.md) for the long-term vision.

## Short Term

* External user directory synchronization (LDAP/IdC/CDC) feeding the workflow `_user_directory` cache (see [Workflow.md](Workflow.md))
* Presentation-lib helpers so custom UIs can build their own profile-completion, password and auth flows easily
* Data versioning and record history
* Cross-model integration: one model using the user database of another (today the workaround is [Single Sign-On](SingleSignOn.md))
* Example models for medium-sized applications

## Mid Term

* Integration via a message-queue system
* Operational improvements: backups, logging, etc.
* Deployment scripts for open-source monitoring stacks
* Kubernetes deployment
* Example models for large-scale applications

## Long Term

* Support multiple data platforms
* Support multiple UI frameworks
* Stronger security and authorization modeling
