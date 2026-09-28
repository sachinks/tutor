# TUTOR documentation

TUTOR is an AI-assisted learning system for Classes 6–12. Students learn through live batches, recorded courses and an
AI tutor, and everything they do builds one evidence-based **learner record**.

## Map

| Area | Document | Read it when |
|---|---|---|
| Product | [Vision and scope](product/vision-and-scope.md) | You're new, or deciding whether something belongs in v1 |
| Product | [Users and journeys](product/users-and-journeys.md) | Building or reviewing any screen or endpoint |
| Product | [Requirements](product/requirements.md) | Checking what "done" means for a feature (functional and non-functional) |
| Product | [Roadmap](product/roadmap.md) | Planning work; seeing what is built and what is next |
| Architecture | [Overview](architecture/overview.md) | Understanding how the system fits together |
| Architecture | [Data model](architecture/data-model.md) | Touching any table or migration |
| Architecture | [API reference](architecture/api-reference.md) | Building or calling an endpoint |
| Architecture | [AI service](architecture/ai-service.md) | Working on the tutor, RAG, grading or evals |
| Architecture | [Security and privacy](architecture/security-and-privacy.md) | Anything involving children's data, auth, payments or secrets |
| Engineering | [Development guide](engineering/development.md) | Setting up a machine; day-to-day workflow |
| Engineering | [Standards](engineering/standards.md) | Before opening your first pull request |
| Engineering | [Deployment](engineering/deployment.md) | Releasing to staging or production |
| Testing | [Test plan](testing/test-plan.md) · [Tester guide](testing/tester-guide.md) · [Test cases](testing/README.md) | Testing a build; reporting bugs |
| Decisions | [Decision log](decisions/decision-log.md) | Asking "why is it like this?" |

## Conventions for these documents

- **Status labels.** Every feature, table and endpoint is marked **Implemented** or **Planned**. Documents describe the
  system as it is, and say plainly where it is heading.
- **One source of truth.** If code and documentation disagree, fix one of them in the same pull request.
- **Diagrams** are written in Mermaid so they live in git and render on GitHub.
- **Decisions** are recorded once in the decision log and referenced by ID (for example `D10`, `M4`, `C6`).
