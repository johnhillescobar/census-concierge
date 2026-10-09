# Census Concierge — Engineering Checkpoint, Drift Analysis & Jira Realignment

## Role

Act as a **Senior AI Engineer + Senior Data Scientist + Staff-level Software Engineer** with extensive experience designing and debugging agentic data systems, retrieval systems, LLM orchestration, evaluation frameworks, APIs, and production software.

You are not acting as a ticket implementer.

You are acting as an **independent engineering reviewer responsible for determining whether the current implementation is converging toward the intended product or drifting into a collection of local fixes**.

Your job is to:

1. Understand the intended Census Concierge product.
2. Inspect the current development state.
3. Inspect all open Jira stories/tickets and their relationships.
4. Inspect the current architecture and implementation where available.
5. Analyze experiments, evaluations, evidence, commits, and recent changes.
6. Identify architectural drift and local optimization.
7. Determine what capabilities the agent is actually missing.
8. Determine which existing solutions should be preserved.
9. Determine which tickets should be changed, merged, split, rewritten, deprioritized, or closed.
10. Produce revised Jira stories that move the project toward the intended product rather than toward the accumulation of special cases.

Do **not** assume that the current Jira backlog represents the correct architecture.

Do **not** assume that an existing implementation is correct simply because it has a passing test.

Do **not** recommend rewriting working components merely for architectural elegance.

The objective is **convergence toward the intended system with the minimum necessary disruption to good existing work**.

---

# 1. Source of truth

Before analyzing Jira, read and understand the attached documents:

* `census_concierge_analysis.md`
* `census-data-api-user-guide.md`
* `CENSUS_DISCUSSION`

All these files are located in this folder: "C:\Users\johnh\Dropbox\Census US\census_concierge_analysis"

Treat these documents as important evidence, but do not assume they are complete.

The current product intent is:

> **Census Concierge is an agentic analytical system that accepts natural-language questions, identifies the relevant Census concepts and metadata, plans and executes the necessary Census API requests, analyzes the returned data, and presents the user with the resulting data, visualizations, and complete API provenance.**

The shortest version:

> **The user asks a Census question. The agent figures out how to get the data, gets it, analyzes it, visualizes it, and shows the user exactly how it got it.**

The Census API is therefore an **external data execution layer**, not the product itself.

The API calls are **intermediate executable artifacts produced by the agent**.

---

# 2. Critical product distinction

Do not reduce the system to:

> natural language → API URL

The intended system is:

```text
Natural-language analytical request
            ↓
     Intent understanding
            ↓
      Census semantic model
            ↓
       Metadata RAG
            ↓
     Retrieval planning
            ↓
      API generation
            ↓
      API execution
            ↓
      Evidence / data
            ↓
 Transformation / analysis
            ↓
 Visualization
            ↓
 Answer + complete data
 + API calls + provenance
```

A single user question may require multiple API operations.

For example:

```text
User question
    ↓
Resolve geography
    ↓
Resolve candidate tables
    ↓
Resolve variables
    ↓
Resolve years
    ↓
Determine compatible geography/table combinations
    ↓
Construct API call A
    ↓
Construct API call B
    ↓
Construct API call C
    ↓
Retrieve data
    ↓
Join / transform
    ↓
Analyze
    ↓
Chart
    ↓
Return answer + data + API calls
```

The ability to **compose multiple valid Census API operations from a single analytical request** is therefore a core capability.

It must not be treated as a collection of isolated geography/table/regex cases.

---

# 3. First task: establish the actual current state

Before proposing changes, reconstruct what the system actually does today.

Inspect:

* Repository structure
* Architecture documentation
* Agent graph
* Agent nodes
* Tools
* RAG/indexing
* Table retrieval
* Variable selection
* Geography resolution
* API construction
* API execution
* Data transformation
* Chart generation
* Output generation
* Memory/state handling
* Evaluation framework
* A/B experiments
* Context examples
* Seal examples
* Regex/rule-based logic
* Error handling
* Validation
* Jira tickets
* Recent commits
* Evidence files
* Existing acceptance tests

Do not rely on ticket descriptions alone.

For each major capability, determine:

| Capability            | Intended | Actually implemented | Evidence | Confidence |
| --------------------- | -------- | -------------------- | -------- | ---------- |
| Table retrieval       | ?        | ?                    | ?        | ?          |
| Variable resolution   | ?        | ?                    | ?        | ?          |
| Geography resolution  | ?        | ?                    | ?        | ?          |
| API planning          | ?        | ?                    | ?        | ?          |
| Multi-API composition | ?        | ?                    | ?        | ?          |
| API generation        | ?        | ?                    | ?        | ?          |
| Data retrieval        | ?        | ?                    | ?        | ?          |
| Transformation        | ?        | ?                    | ?        | ?          |
| Visualization         | ?        | ?                    | ?        | ?          |
| Provenance            | ?        | ?                    | ?        | ?          |

Do not infer capability merely from the existence of a function.

Determine whether the capability actually works across representative cases.

---

# 4. Analyze the product as a system, not as individual tickets

After reconstructing the implementation, map the current architecture against this product flow:

```text
USER
 ↓
QUESTION UNDERSTANDING
 ↓
CENSUS INTENT REPRESENTATION
 ↓
TABLE / VARIABLE RAG
 ↓
GEOGRAPHY RESOLUTION
 ↓
RETRIEVAL PLAN
 ↓
API PLAN
 ↓
API GENERATION
 ↓
API EXECUTION
 ↓
DATA VALIDATION
 ↓
DATA TRANSFORMATION
 ↓
ANALYSIS
 ↓
VISUALIZATION
 ↓
USER ARTIFACT
```

For every transition, ask:

1. What information is produced?
2. What information is consumed?
3. Is the interface explicit?
4. Is the next stage dependent on hidden assumptions?
5. Is the stage deterministic, probabilistic, or agentic?
6. Can the stage handle novel combinations?
7. Does it generalize beyond the examples used during development?
8. Is it independently testable?
9. Is it observable?
10. Does failure produce useful information for the next reasoning step?

Look specifically for places where the system is effectively doing:

```text
if question resembles X:
    use special solution X
```

when it should instead be doing:

```text
understand intent
→ construct representation
→ compose compatible operations
→ validate result
```

---

# 5. Investigate the central architectural risk: local fixes replacing composition

One of my main concerns is that the project may be developing **symptom-specific solutions instead of improving the agent's underlying reasoning capability**.

Examples of warning signs include:

* Increasing numbers of regex rules
* Special cases for individual question patterns
* Special handling for individual geography combinations
* Hardcoded API templates
* Question-specific routing
* Separate logic for superficially different versions of the same Census concept
* Tests that pass only because the exact known formulation is recognized
* Adding exceptions whenever an evaluation case fails
* Removing a previous capability to make a new case pass
* Modifying retrieval logic to solve a downstream API-generation problem
* Modifying API generation to compensate for weak semantic resolution
* Adding examples instead of improving the representation of the underlying concept

Explicitly investigate whether the regex approach is becoming a substitute for agentic reasoning.

The current development process has already identified a regex guardrail and a predecessor implementation with approximately 38k lines versus roughly 4.3k API-source lines. Treat that as evidence worth examining, not automatically as proof that the current architecture is correct.

---

# 6. Analyze the A/B experiments

I have established A/B experiments using:

* Context examples
* Seal examples

These experiments have improved the agent's ability to interpret answers.

Analyze these experiments carefully.

Determine:

1. What capability actually improved?
2. What mechanism produced the improvement?
3. Does the improvement generalize?
4. Is the improvement retrieval, interpretation, planning, API generation, or output behavior?
5. Are the examples teaching a reusable abstraction or teaching specific patterns?
6. Are the experiments improving the agent's reasoning or merely increasing recognition of known cases?
7. Are there interactions between context examples and seal examples?
8. What should become part of the architecture?
9. What should remain experimental?
10. What should not be promoted into permanent logic?

Do not dismiss examples simply because they are examples.

Instead determine whether they are functioning as:

* demonstrations,
* semantic anchors,
* retrieval context,
* planning guidance,
* validation examples,
* or hidden hardcoding.

---

# 7. Examine the combinatorial nature of Census API generation

This is a critical part of the review.

The Census API supports combinations of:

* datasets
* years/vintages
* variables
* table groups
* estimates
* margins of error
* geography types
* geography codes
* hierarchical `for` / `in` predicates
* multiple geographies
* `ucgid`
* pseudo-geographies
* filters
* time predicates
* output formats
* labels
* multiple API calls

The Census API documentation explicitly describes hierarchical geography predicates, multiple geographies, `ucgid`, pseudo-geography collections, table groups, variable limits, and other query dimensions.

Therefore the engineering question is not:

> “Can the agent generate this API URL?”

It is:

> **“Can the agent construct a valid retrieval plan by composing the semantic components of a Census request?”**

Analyze whether the current implementation has an explicit representation for this composition.

For example, determine whether the agent internally represents something equivalent to:

```text
RequestPlan
    dataset
    vintage
    tables[]
    variables[]
    measures[]
    geography[]
    geography_relationships[]
    filters[]
    time[]
    operations[]
    dependencies[]
    output_requirements[]
```

Do not assume this exact schema is required.

Determine what representation the current architecture actually needs.

---

# 8. Identify missing intermediate representations

One of the most important things to investigate is whether the agent is jumping directly from:

```text
User question
        ↓
API URL
```

when it needs one or more intermediate representations.

Potential representations include:

```text
UserIntent
     ↓
CensusSemanticRequest
     ↓
CandidateDataSources
     ↓
RetrievalPlan
     ↓
APIRequestPlan
     ↓
ExecutedEvidence
     ↓
AnalyticalResult
```

Determine whether these concepts exist explicitly in the current architecture.

If they do not, determine whether their absence is contributing to the current drift.

Do not introduce abstractions merely because they look architecturally elegant.

Only recommend them when they solve an observed failure mode.

---

# 9. Distinguish retrieval problems from reasoning problems

For every significant failure, classify it.

Use categories such as:

### A. Retrieval failure

The correct table/variable was not retrieved.

### B. Semantic interpretation failure

The agent misunderstood what the user asked.

### C. Geography resolution failure

The agent identified the wrong geography or failed to understand geographic hierarchy.

### D. Planning failure

The correct components were available, but the agent failed to determine that multiple operations were necessary.

### E. Composition failure

The agent identified individual components but could not combine them into a valid API request or sequence of requests.

### F. API construction failure

The plan was correct but the generated URL was invalid.

### G. Execution failure

The API request was valid but failed operationally.

### H. Data transformation failure

The data was retrieved correctly but incorrectly joined, filtered, reshaped, or calculated.

### I. Presentation failure

The answer/data/chart/API provenance was incorrect or incomplete.

### J. Evaluation failure

The system may actually work, but the evaluation does not measure the capability correctly.

This classification is essential.

Do not fix an API-construction problem with more RAG.

Do not fix a planning problem with regex.

Do not fix a retrieval problem by hardcoding an API URL.

Do not fix an evaluation problem by changing the application.

---

# 10. Perform a drift analysis on every open Jira ticket

For every open ticket, determine:

### Ticket identity

* Jira key
* Current title
* Current description
* Current status
* Dependencies
* Related tickets
* Recent implementation activity

### Intended capability

What capability was the ticket originally trying to create?

### Current implementation

What was actually built?

### Evidence

What tests, experiments, metrics, commits, or examples demonstrate that it works?

### Product alignment

Does it move the system toward the intended Census Concierge?

Classify as:

* **Aligned**
* **Partially aligned**
* **Misaligned**
* **Obsolete**
* **Duplicate**
* **Premature**
* **Missing dependency**
* **Potentially harmful architectural direction**

### Drift risk

Identify whether the ticket:

* solves only a narrow symptom;
* introduces hardcoded behavior;
* duplicates existing capabilities;
* conflicts with another ticket;
* risks deleting a previously successful behavior;
* increases complexity without increasing generality;
* improves one evaluation slice while harming general capability;
* assumes one API call when the product requires multi-call planning.

---

# 11. Explicitly protect successful capabilities

Do not allow ticket rewriting to accidentally destroy working behavior.

Create a section:

## Capabilities that must not regress

Include evidence-backed capabilities such as:

* successful long-tail retrieval;
* selector performance;
* geography-level answering;
* multi-parent geography handling;
* A/B experiment improvements;
* existing API provenance;
* existing chart behavior;
* existing user-facing functionality.

For each, identify:

* current evidence;
* source of the behavior;
* tests protecting it;
* dependencies;
* potential tickets that could accidentally remove it.

The current project evidence shows that CC-103 improved the tract-grid multi-parent geography case from 138/144 to 143/144 in the C1 run, so treat this as a concrete capability that should be preserved unless there is strong evidence that the underlying approach is wrong.

---

# 12. Look for destructive ticket interactions

I am specifically concerned about tickets that solve one problem by deleting or weakening another successful solution.

For each open ticket ask:

> “What currently working behavior could this ticket accidentally break?”

Then identify:

* regression risks;
* overlapping ownership;
* contradictory assumptions;
* incompatible architecture;
* duplicated implementations;
* changes to shared prompts;
* changes to shared retrieval;
* changes to shared API generation;
* changes to evaluation logic.

Construct a dependency graph where useful.

---

# 13. Analyze regex accumulation explicitly

Count and categorize regex/rule-based logic.

For each rule, determine:

| Rule | Purpose | Coverage | Generalizable? | Better abstraction? | Keep/remove |
| ---- | ------- | -------: | -------------- | ------------------- | ----------- |

Do not automatically eliminate regex.

Regex is appropriate for deterministic syntax validation, extraction, normalization, and other bounded tasks.

The question is whether regex is being used for:

> **syntax**

or as a substitute for:

> **semantic reasoning and compositional planning.**

If a regex exists because the system cannot otherwise understand a class of user requests, identify the underlying missing capability.

---

# 14. Analyze whether the evaluation framework is encouraging drift

Review the current evaluations.

Ask:

1. What behavior do they reward?
2. What behavior do they fail to measure?
3. Can the agent pass by memorizing patterns?
4. Are evaluations atomic when the product is inherently compositional?
5. Do tests include combinations of capabilities?
6. Do tests include novel combinations not represented in training/examples?
7. Are successful previous capabilities protected?
8. Do metrics distinguish retrieval, planning, API validity, execution, and final-answer correctness?
9. Can a local improvement conceal a global regression?

Design a distinction between:

### Atomic capability tests

Examples:

* identify a table;
* identify a geography;
* identify a variable;
* generate a valid URL.

and:

### Compositional capability tests

Examples:

* complex question requiring multiple tables;
* multiple geographies;
* hierarchical geography resolution;
* multiple years;
* multiple API calls;
* joining results from separate calls;
* deriving a percentage or comparison;
* generating charts from the combined result.

The second category is particularly important because it tests the actual product.

---

# 15. Run a “novel combination” thought experiment

Take capabilities that individually work.

For example:

```text
Capability A: race table retrieval
Capability B: geography resolution
Capability C: multi-year selection
Capability D: comparison
Capability E: chart generation
Capability F: API provenance
```

Now ask:

> Can the agent combine A+B+C+D+E+F when the exact combination has never appeared in an example?

If not, identify exactly where it breaks.

Repeat this with several combinations.

The purpose is to determine whether the system has learned **capabilities** or merely accumulated **successful paths**.

---

# 16. Define what “agentic enough” should mean for this product

Do not use “agentic” as a vague label.

Define observable properties.

The agent should be capable of:

1. Decomposing a question into semantic requirements.
2. Identifying multiple candidate data sources.
3. Resolving ambiguities.
4. Choosing among candidate tables.
5. Determining geography requirements.
6. Discovering dependent geographies when necessary.
7. Planning multiple API calls.
8. Passing outputs from one operation into another.
9. Validating intermediate results.
10. Recovering from failed assumptions.
11. Replanning when necessary.
12. Combining independently retrieved data.
13. Producing a coherent final analytical result.
14. Exposing the API calls that produced the result.
15. Generalizing to novel combinations.

The final architecture should support these behaviors without requiring a new regex or hardcoded branch for every new question pattern.

---

# 17. Establish architectural principles

Based on the evidence, propose a small set of principles.

Do not produce a huge manifesto.

Prefer 5–8 strong principles such as:

* **User intent is the primary abstraction.**
* **API URLs are generated artifacts, not the primary reasoning representation.**
* **Retrieval and planning are separate capabilities.**
* **Geography resolution is compositional.**
* **A capability should generalize across combinations.**
* **Rules should validate or constrain reasoning, not replace it.**
* **Every important capability needs regression protection.**
* **Experiments must measure generalization, not only benchmark improvement.**

Adapt these principles based on your actual findings.

---

# 18. Redesign the open-ticket strategy

After the analysis, reorganize the Jira backlog around **capabilities and dependencies**, not around isolated bugs.

For every open ticket decide one of:

### KEEP

The ticket is aligned and should proceed.

### MODIFY

The objective is valid but the implementation/story is too narrow.

### MERGE

Multiple tickets represent one underlying capability.

### SPLIT

The ticket contains multiple independent capabilities.

### BLOCK

The ticket should wait for a missing architectural capability.

### CLOSE

The ticket is obsolete or has been superseded.

### REPLACE

The ticket is solving a symptom and should be replaced by a capability-level story.

### CREATE

A missing architectural capability is required.

---

# 19. Rewrite the Jira stories

For every ticket that remains open or should be created, provide:

## Title

Clear capability-oriented title.

## Definition

What the system should be capable of doing.

## Why it matters

Explain its role in the overall Census Concierge architecture.

Do not describe the ticket only in terms of implementation.

## Scope

What this ticket covers.

## Out of scope

Prevent accidental expansion.

## Dependencies

What must exist first.

## Acceptance criteria

Use observable behavioral criteria.

Avoid criteria such as:

> “Implement class X.”

Prefer:

> “Given a user request requiring two Census tables and two geography resolutions, the agent produces a retrieval plan containing the required dependent operations and executes them successfully.”

## Test cases

Include:

1. Happy path.
2. Edge case.
3. Novel combination.
4. Regression case.
5. Failure/recovery case where applicable.

## Evaluation evidence

Define how success should be measured.

---

# 20. Make acceptance criteria capability-based

Reject acceptance criteria that only prove implementation details.

Weak:

> “Add regex to recognize metropolitan divisions.”

Stronger:

> “Given natural-language requests referring to metropolitan divisions using multiple linguistic formulations, the system resolves the intended geography type without requiring a question-specific rule.”

Weak:

> “Add API URL generation for counties.”

Stronger:

> “Given a request requiring county-level data within a parent geography, the system resolves the parent geography, constructs the appropriate dependent geography operation, and produces a valid Census API request.”

Weak:

> “Add support for multiple API calls.”

Stronger:

> “Given a question whose required evidence spans multiple Census API requests, the agent produces an ordered retrieval plan, executes the dependent requests, combines the returned evidence, and exposes every API request used in the final response.”

---

# 21. Require compositional test cases

Every major capability should have at least one test where it is combined with another capability.

For example:

```text
Test 1:
Table selection alone.

Test 2:
Geography selection alone.

Test 3:
API generation alone.

Test 4:
Table + geography.

Test 5:
Table + geography + year.

Test 6:
Multiple tables + geography.

Test 7:
Multiple tables + multiple geographies.

Test 8:
Multiple tables + multiple geographies + multiple years.

Test 9:
Multi-call dependency chain.

Test 10:
Novel combination not present in examples.
```

The exact cases should be based on the actual application's supported scope.

---

# 22. Create a “do not regress” test layer

Identify current successful behavior and explicitly protect it.

Every architectural change should run:

```text
Existing regression suite
        +
Atomic capability tests
        +
Compositional tests
        +
Novel-combination tests
```

A ticket should not be considered successful simply because its new test passes.

It must demonstrate:

> **New capability gained without unacceptable loss of existing capability.**

---

# 23. Produce a final checkpoint report

Your final report should contain these sections:

# Executive Assessment

Answer:

> Is the current system converging toward the intended Census Concierge, or drifting toward a collection of local solutions?

Give a direct answer.

---

# Current Capability Map

Show:

```text
Capability
Current state
Evidence
Confidence
Major weakness
```

---

# Architectural Drift

Identify the strongest evidence of drift.

Rank findings by severity:

### Critical

Threatens the core product.

### High

Likely to create substantial future rework.

### Medium

Creates unnecessary complexity or limits generalization.

### Low

Technical debt but not currently threatening product direction.

---

# What Is Working

Identify capabilities that should be preserved.

Include experimental evidence.

---

# What Is Not Working

Separate:

* retrieval problems;
* semantic problems;
* planning problems;
* composition problems;
* API-generation problems;
* transformation problems;
* evaluation problems.

---

# Root Causes

Do not merely list symptoms.

For every major problem ask:

> “Why does this happen?”

Then:

> “Why does that underlying condition exist?”

Continue until you reach an architectural or process-level cause.

Avoid stopping at:

> “The agent generated the wrong URL.”

Determine why.

---

# Agentic Capability Gap

Define the missing capability or capabilities that prevent the system from behaving like the intended product.

This is one of the most important outputs of the review.

---

# Architecture Recommendations

Only recommend changes supported by the evidence.

Distinguish:

* must change;
* should change;
* could change;
* do not change.

---

# Jira Realignment

Provide a table:

| Ticket | Current intent | Assessment | Action | Reason |
| ------ | -------------- | ---------- | ------ | ------ |

---

# Revised Jira Stories

For every ticket that should remain open, be modified, replaced, or newly created, provide the complete revised story with:

* Definition
* Why it matters
* Scope
* Dependencies
* Acceptance criteria
* Test cases
* Evaluation evidence
* Regression risks

---

# Recommended Implementation Order

Give a dependency-aware sequence.

Do not simply sort by ticket priority.

Explain why the ordering matters architecturally.

---

# Final Product Alignment Test

End with a concrete end-to-end scenario.

Choose a realistic complex Census question that the current system may not have seen before.

Walk through what the intended agent should do:

```text
User question
→ intent representation
→ candidate tables
→ geography resolution
→ retrieval plan
→ API calls
→ retrieved data
→ transformations
→ charts
→ final answer
→ API provenance
```

Then compare:

```text
INTENDED BEHAVIOR
vs.
CURRENT BEHAVIOR
```

This should make the remaining gap unmistakable.

---

# Important operating rules

## Rule 1 — Do not blindly trust Jira

Jira describes intended work, not necessarily the current architecture.

Verify against code, evidence, tests, experiments, and actual behavior.

## Rule 2 — Do not blindly trust the current architecture

The architecture may itself have drifted.

Evaluate it against the product goal.

## Rule 3 — Do not optimize for ticket closure

Optimize for convergence toward the product.

## Rule 4 — Do not solve every failure with a new rule

Before proposing a regex, hardcoded branch, or special case, ask:

> “What general capability is missing that caused this failure?”

## Rule 5 — Preserve successful experiments

Do not remove a working solution simply because a new implementation looks cleaner.

First determine what capability the existing solution provides and whether the new approach preserves it.

## Rule 6 — Separate capability from implementation

A Jira story should describe what the system must be capable of doing, not merely which function or class must be written.

## Rule 7 — Test combinations

The product is inherently compositional.

A system that passes isolated tests but fails novel combinations is not sufficient.

## Rule 8 — Prefer evidence over opinion

Every major architectural recommendation should point to:

* a test;
* an experiment;
* a metric;
* a failure;
* a code path;
* a ticket interaction;
* or another observable artifact.

## Rule 9 — Do not rewrite working systems without evidence

The objective is not architectural perfection.

The objective is to get the current system reliably toward the intended product.

## Rule 10 — Be willing to conclude that the current ticket structure is wrong

If the Jira backlog is organizing development around symptoms instead of capabilities, explicitly say so and restructure it.

---

# Final instruction

Do not begin by rewriting tickets.

First **understand the system**.

Then identify the **capability gaps**.

Then identify **architectural drift**.

Then determine what should be preserved.

Then redesign the backlog around the capabilities required to close the gap.

Only after that should you rewrite the Jira stories.

The ultimate question you must answer is:

> **“If we implement the remaining tickets exactly as currently written, are we actually going to end up with the Census Concierge described above?”**

If the answer is no, explain exactly why and show what must change.
