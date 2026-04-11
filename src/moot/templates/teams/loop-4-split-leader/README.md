# loop-4-split-leader -- Separated Product/Lead

Pipeline with separated human-facing (Product) and team-facing (Lead) coordination.
Product <--> Lead --> Spec --> Implementation --> QA --> Lead.

Use when human interaction load is high enough to warrant a dedicated product interface,
or when coordinating multiple parallel pipelines.
