Choose which portfolio data sources are needed to answer the user's portfolio question.

Available sources:
- projects: GitHub or portfolio projects, descriptions, tech stacks, links, README-level details, and project outcomes
- resume: resume facts, employment history, companies, responsibilities, education, certifications, skills, achievements, and role summaries
- docs: extra long-form documents, case studies, blog posts, notes, or custom portfolio knowledge

Return the smallest useful set of sources. Use multiple sources when the question crosses boundaries.

Examples:
- "What projects has the subject built?" -> projects
- "What is their work experience?" -> resume
- "Who are you?" -> resume
- "Are they a good fit for AI backend work?" -> projects, resume
- "How can I contact them?" -> resume
- "What have they written about system design?" -> docs
