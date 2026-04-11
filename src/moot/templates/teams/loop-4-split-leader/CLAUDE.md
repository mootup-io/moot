# {project_name}

TODO: Describe your project. What does it do? What problem does it solve?

## Status

TODO: What works, what doesn't. Update as the project evolves.

## Tech stack

TODO: Language, frameworks, databases, build tools.

## Running

TODO: How to run the project, run tests, build, deploy.

## Code conventions

TODO: Formatting, linting, type checking, naming conventions.

## Agent Workflow

{role_count} agents collaborate on this project: {role_list}. They communicate via the Convo shared context server.

### Roles

{role_descriptions}

### Product / Lead Separation

Product handles prioritization, requirements, and stakeholder communication. Lead runs the pipeline: dispatch to Spec, merge branches, monitor progress, process QA handoffs, run retros. Product dispatches features to Lead; Lead reports completion back to Product.

### Resource Ownership

{resource_ownership}

### Git Workflow

{git_description}

### Startup

On connecting to a space (including restarts and resumes), every agent must:
1. Call orientation() to get identity, focus space, and context
2. Subscribe to the channel for push notifications
3. Post a status_update confirming identity and readiness

### Work Pipeline

{workflow_description}

```
{pipeline_diagram}
```

{handoff_protocol}

Before handing off, the agent must commit to their branch and request a merge from Lead via a `[GIT-REQUEST]` thread.

**Status updates on handoff:** Every agent must call `update_status` when receiving or completing a handoff.

### Channel Threading Protocol

{threading_protocol}

### Clarification Flow

When an agent is blocked and needs input, use `[QUESTION]` threads in the channel. Mention the target agent.

### Tracking Decisions

Use `propose_decision` for choices that involve tradeoffs, creativity, or judgment -- decisions where a different person might choose differently. Do NOT track mechanical or purely deductive decisions.

### Retrospective

After the verifier approves and the leader confirms a feature is complete, every agent posts a retro message in the `[FEATURE]` thread.
