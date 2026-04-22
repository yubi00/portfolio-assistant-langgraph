Choose which portfolio data sources are needed to answer the user's portfolio question.

Available sources:
- profile: basic identity, contact details, preferred summary, location, social links, and high-level positioning
- projects: GitHub or portfolio projects, descriptions, tech stacks, links, README-level details, and project outcomes
- resume: resume facts, education, certifications, skills, achievements, and role summaries
- work_history: employment history, companies, responsibilities, domain experience, and career timeline
- docs: extra long-form documents, case studies, blog posts, notes, or custom portfolio knowledge

Return the smallest useful set of sources. Use multiple sources when the question crosses boundaries.

Examples:
- "What projects has the subject built?" -> projects
- "What is their work experience?" -> work_history, resume
- "Are they a good fit for AI backend work?" -> projects, resume, work_history
- "How can I contact them?" -> profile
- "What have they written about system design?" -> docs
