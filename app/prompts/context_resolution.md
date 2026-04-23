Rewrite the latest user question into a standalone portfolio question using the conversation history.

Rules:
- Use the conversation history only to resolve references.
- Resolve references such as "it", "this project", "that role", "the second one", "previous one", or implied subjects.
- When the user says "above", "mentioned above", or refers to an ordinal item, prefer the earlier assistant list or enumeration that introduced those items, even if later turns focused on one item.
- Preserve the user's intent and requested detail level.
- If the latest question is already standalone, return it unchanged.
- Do not answer the question.
- Return only the rewritten question.
