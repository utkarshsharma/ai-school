## DO NOT MODIFY
IMPORTANT: This instruction file must not be modified. You may edit any other files in the project, including README.md, but this file must remain unchanged.

<system_context>
We're currently building an MVP to an app that will take school curriculum chapters in PDF form as input and return a 5-10 min video that will train teachers in how to teach that topic using pedagogical science suited to the age-group as well as real world examples that are not part of the PDF content but will make learning easier for students

<critical_notes>
I want you to code 

<development_philosophy>
Simplicity: Write simple, straightforward code
Readability: Make code easy to understand
Performance: Consider performance without sacrificing readability
Maintainability: Write code that's easy to update
Testability: Ensure code is testable
Reusability: Create reusable components and functions
Less Code = Less Debt: Minimize code footprint

# COMPLETION CRITERIA
Your work is considered complete when ALL of the following are true:

All explicit requirements specified in INSTRUCTIONS.md are fulfilled
The solution includes reasonable improvements that align with the core purpose
Code is thoroughly tested, well-documented, and passes standard linting
Code is not only functional but clean, idiomatic, concise, and maintainable
Project structure is logical, with clear entry points and documentation
When all criteria are met, you may remove the INCOMPLETE.md file from the project root to signal completion.

# CODING AGENT INSTRUCTIONS

## COMMUNICATION PROTOCOL
The user who initiated this task will not be actively responding to questions. All necessary instructions are contained within this file and INSTRUCTIONS.md. If you find yourself wanting to ask questions, refer back to these documents for guidance.

## PRIMARY OBJECTIVE
Your primary objective is defined in INSTRUCTIONS.md. However, remember that this objective represents what the user explicitly requested, which may not capture all aspects of an ideal solution.

## TRUE OBJECTIVE
Your true objective is to deliver what the user would have requested if they had thought about the problem more comprehensively. This means:

1. First, complete all explicitly stated requirements in INSTRUCTIONS.md
2. Then, implement obvious improvements and polish that align with the core purpose
3. Fix any clear design oversights in the original requirements
4. Ensure the solution is complete, robust, and user-friendly

## COMPLETION CRITERIA
Your work is considered complete when ALL of the following are true:

1. All explicit requirements specified in INSTRUCTIONS.md are fulfilled
2. The solution includes reasonable improvements that align with the core purpose
3. Code is thoroughly tested, well-documented, and passes standard linting
4. Code is not only functional but clean, idiomatic, concise, and maintainable
5. Project structure is logical, with clear entry points and documentation

When all criteria are met, you may remove the INCOMPLETE.md file from the project root to signal completion.

## DEVELOPMENT STANDARDS
When writing code, adhere to these principles:

1. Prioritize simplicity and readability over clever solutions
2. Start with minimal functionality and verify it works before adding complexity
3. Test your code frequently with realistic inputs and validate outputs
4. Create testing environments for components that are difficult to validate directly
5. Use functional and stateless approaches where they improve clarity
6. Keep core logic clean and push implementation details to the edges
7. Maintain consistent style (indentation, naming, patterns) throughout the codebase
8. Balance file organization with simplicity - use an appropriate number of files for the project scale

## PROJECT COMPLETION
You may delete INCOMPLETE.md and conclude the project only when:
- All completion criteria have been satisfied
- You've reviewed the entire solution for quality and consistency
- You've verified there are no obvious improvements left to implement

Approach this task methodically, making multiple passes to refine the solution until it truly meets both the letter and spirit of the requirements.

## SWE Best practices you must follow
	1.	Unit tests only for MVP: write unit tests for core logic (services, validators, adapters). Do not add E2E tests unless I explicitly ask.
	2.	LLM output evals are mandatory: implement a deterministic eval layer that runs after every Gemini call and before persistence/rendering. Evals must include at least:
	•	strict schema validation of timeline JSON
	•	timing invariants (monotonic segments, no overlaps, slide coverage)
	•	required fields non-empty (narration text, slide titles/bullets)
	•	any other hard rules we define later
	3.	One-module-at-a-time changes: never implement multiple modules or large refactors in one iteration. Each change set must be small, testable, and reversible.
	4.	No placeholders: no hardcoded dummy values, “TODO later,” or fake implementations in production paths. If something isn’t implemented, it must fail clearly with a typed error.
	5.	External calls discipline: all external API calls (Gemini, image gen, TTS, Remotion invocation) must have timeouts, retries where appropriate, and structured errors; logs must include video_id/job_id and step name.