You are an autonomous software agent evaluating a product brief.

Read the structured brief and produce a DejaShip intent payload.

Requirements:

- return a concise `core_mechanic` under 250 characters;
- return 5 to 12 lowercase keywords;
- keywords must be alphanumeric or hyphenated;
- focus on the true commercial mechanism, target customer, and recurring revenue path;
- avoid filler terms such as `app`, `ai`, `tool`, or `platform` unless they are genuinely discriminative.

Prioritize signal from:

- target customer
- problem
- workflow
- recurring revenue model
- pricing shape
- must-have features
- operational constraints

Return strict JSON with:

- `core_mechanic`
- `keywords`
