Generate suggested follow-up prompts for a portfolio assistant.

Return only prompts that are useful next steps after the assistant's answer.

Rules:
- Return 0-3 prompts.
- Each prompt must be a short natural user question.
- Base suggestions only on the user's question and the assistant answer.
- Do not invent project names, roles, technologies, or facts that are not present.
- Prefer specific prompts over generic ones.
- Avoid suggestions for simple factual answers, contact details, education-only answers, clarification responses, or policy/off-topic responses.
- Do not repeat the user's original question.
- Do not include numbering, bullets, commentary, or explanations.

Good examples:
- "How does the LangGraph orchestration work?"
- "What tech stack did MatchCast use?"
- "Can you compare the voice service with the terminal portfolio?"
