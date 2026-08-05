# Dependencies

The planner validates missing tasks and cycles before review. Workers claim ready tasks using `FOR UPDATE SKIP LOCKED`; evidence and versioned state preserve critical-path and blocking analysis.
