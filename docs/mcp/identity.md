# Identity MCP

## Purpose
Manages the agent's persona (Identity), language settings, and behavioral constraints. It ensures the agent stays "in character" and follows user-defined rules.

## Data Structure
The identity is stored in `data/identity.json` and includes:
- **Name/Role**: The core persona.
- **Psychological Profile**: Traits, affinities, aversions, and principles.
- **Communication Style**: Tone, verbosity, and vocabulary rules.
- **Constraints**: Hard rules (e.g., "Always say God bless you").

## Functions
- `get_identity()`: Returns the full persona object.
- `identity_prompt()`: Generates a text block for the system prompt.
- `verifier_identity_prompt()`: Returns a subset of the identity (traits + constraints) for the Verifier role to check for violations.

## Tools
### `get_identity`
- **Description**: Retrieves current identity and language.
- **Returns**: JSON object with identity details.

## Example Configuration
```json
{
  "name": "Father Barnabas",
  "role": "Wise Bishop",
  "constraints": ["Always conclude with: 'God bless us.'"]
}
```
