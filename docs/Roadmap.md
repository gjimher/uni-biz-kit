# Roadmap

UniBizKit is intentionally developed in phases. See [docs/README.md](README.md) for the long-term vision.

## Short Term

* Database migration deployment scripts, with schema-compatibility checks against the deployed database
* Workflow-based task assignment (see [Workflow.md](Workflow.md))
* Backend integration functions and schema adaptation (importing and mapping external schemas)
* `on delete` copy-data relationships: snapshot the related record's data instead of cascading or restricting
* Mandatory profile fields collected when a new user signs up
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
