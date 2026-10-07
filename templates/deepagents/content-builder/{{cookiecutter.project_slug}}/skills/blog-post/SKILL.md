---
name: blog-post
description: Writes and structures long-form blog posts, creates tutorial outlines, and optimizes content for SEO with optional cover images. Use when the user asks to write a blog post, article, how-to guide, tutorial, technical writeup, thought leadership piece, or long-form content.
---

# Blog Post Writing Skill

## Mode and sources

Read the runtime system prompt for content mode and enabled capabilities.
The default is **pure text**. Read at least three local notes from sources/
with read_source (planning.md, files.md, memory.md, approval.md). Use the
provided sources rather than fabricating web citations. Do not invoke
researcher, web_search or image tools in text mode.

In full mode, delegate research with task(subagent_type="researcher") only
when search is enabled. Specify both the topic and a /research/<slug>.md
output path, then read the findings. Without search, use local material or
material supplied by the user.

## Output and completion

Save text to `blogs/<slug>/post.md`. For a course report/blog, use
save_report(slug, content), then read_report(slug); built-in write_file and
read_file can be used for other content paths. Include a title, context,
findings, practical application and a Sources section with the local
filenames or enabled research URLs used. Use write_todos for the steps and
mark completed only after checking the saved text. Plan actual work steps;
do not add a task just to update the plan. Make the final write_todos update
in a later response than read_report, and mark all successful steps completed
before answering. If a tool fails, fix it before completing that step. Label
the report as synthetic course material and keep claims grounded in the notes.

A text deliverable is complete without an image. Generate a companion image
only if images are enabled AND the user asks for one. Never retry an absent
image or search tool. Mention optional visuals only if requested.

## Blog Post Structure

Every blog post should follow this structure:

### 1. Hook (Opening)
- Start with a compelling question, statistic, or statement
- Make the reader want to continue
- Keep it to 2-3 sentences

### 2. Context (The Problem)
- Explain why this topic matters
- Describe the problem or opportunity
- Connect to the reader's experience

### 3. Main Content (The Solution)
- Break into 3-5 main sections with H2 headers
- Each section covers one key point
- Include code examples, diagrams, or screenshots where helpful
- Use bullet points for lists

### 4. Practical Application
- Show how to apply the concepts
- Include step-by-step instructions if applicable
- Provide code snippets or templates

### 5. Conclusion & CTA
- Summarize key takeaways (3 bullets max)
- End with a clear call-to-action
- Link to related resources

## Cover Image Generation

When images are enabled and the user requested a cover, use `generate_cover`:

```
generate_cover(prompt="A detailed description of the image...", slug="your-blog-slug")
```

The tool saves the image to `blogs/<slug>/hero.png`.

### Writing Effective Image Prompts

Structure your prompt with these elements:

1. **Subject**: What is the main focus? Be specific and concrete.
2. **Style**: Art direction (minimalist, isometric, flat design, 3D render, watercolor, etc.)
3. **Composition**: How elements are arranged (centered, rule of thirds, symmetrical)
4. **Color palette**: Specific colors or mood (warm earth tones, cool blues and purples, high contrast)
5. **Lighting/Atmosphere**: Soft diffused light, dramatic shadows, golden hour, neon glow
6. **Technical details**: Aspect ratio considerations, negative space for text overlay

### Example Prompts

**For a technical blog post:**
```
Isometric 3D illustration of interconnected glowing cubes representing AI agents, each cube has subtle circuit patterns. Cubes connected by luminous data streams. Deep navy background (#0a192f) with electric blue (#64ffda) and soft purple (#c792ea) accents. Clean minimal style, lots of negative space at top for title. Professional tech aesthetic.
```

**For a tutorial/how-to:**
```
Clean flat illustration of hands typing on a keyboard with abstract code symbols floating upward, transforming into lightbulbs and gears. Warm gradient background from soft coral to light peach. Friendly, approachable style. Centered composition with space for text overlay.
```

## SEO Considerations

- Include the main keyword in the title and first paragraph
- Use the keyword naturally 3-5 times throughout
- Keep the title under 60 characters
- Write a meta description (150-160 characters)

## Quality Checklist

Before finishing:
- [ ] Post saved to `blogs/<slug>/post.md`
- [ ] If requested and enabled, hero image generated at `blogs/<slug>/hero.png`
- [ ] Hook grabs attention in first 2 sentences
- [ ] Each section has a clear purpose
- [ ] Conclusion summarizes key points
- [ ] CTA tells reader what to do next
