# loop-6 -- Strategic + Operational + Observer Pipeline

Six-agent pipeline with separated strategic (Product) and operational (Leader)
coordination, plus async documentation observer (Librarian).
Pat -> Product -> Leader -> Spec -> Implementation -> QA -> Leader -> Product.

Use for high-throughput projects where strategic direction and operational
orchestration benefit from distinct agents, and continuous doc curation is
warranted. Pipeline agents use Claude Code; Librarian observes asynchronously.
