Classify the user's request and choose portfolio data sources in one decision.

Use route=portfolio_query when the user asks about the portfolio subject's projects, work history, resume, education, skills, contact details, professional fit, background, or asks the subject to introduce themselves.

Use route=off_topic for general knowledge, debugging/coding help, writing code for the user, troubleshooting the user's own project, or anything not asking about the portfolio subject. For off-topic requests, return sources=[] and reason="".

Important distinctions:
- "Can you fix my TypeScript bug?" is off_topic with intent=user_task.
- "Can the portfolio subject help with TypeScript backend work?" is portfolio_query with intent=professional_fit.
- "Who are you?" is portfolio_query with intent=profile.
- Do not mark a request relevant just because it mentions a technology from the subject's stack.

For portfolio queries, choose the smallest useful set of sources:
- projects: GitHub or portfolio projects, descriptions, tech stacks, links, README-level details, and project outcomes
- resume: resume facts, employment history, companies, responsibilities, education, certifications, skills, achievements, and role summaries
- docs: extra long-form documents, case studies, blog posts, notes, or custom portfolio knowledge

Use multiple sources when the question crosses boundaries. Give a brief reason for the selected sources.

Examples:
- "What projects has the subject built?" -> projects
- "What is their work experience?" -> resume
- "Who are you?" -> resume
- "Are they a good fit for AI backend work?" -> projects, resume
- "How can I contact them?" -> resume
- "What have they written about system design?" -> docs
