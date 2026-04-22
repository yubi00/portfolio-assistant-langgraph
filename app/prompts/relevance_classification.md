Classify a portfolio assistant request into exactly one graph route.

Use route=portfolio_query only when the user is asking about the portfolio subject's projects, work history, resume, education, skills, contact details, professional fit, or background.

Use route=assistant_identity when the user asks who you are, what you can do, or how to use the assistant.

Use route=off_topic for general knowledge, debugging/coding help, writing code for the user, troubleshooting the user's own project, or anything not asking about the portfolio subject.

Important distinctions:
- "Can you fix my TypeScript bug?" is off_topic with intent=user_task.
- "Can the portfolio subject help with TypeScript backend work?" is portfolio_query with intent=professional_fit.
- Do not mark a request relevant just because it mentions a technology from the subject's stack.

