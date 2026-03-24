---
title: Skill Authoring
description: Write effective SKILL.md files that compile to ontologies Claude can discover and use
---

OntoSkills compiles natural-language `SKILL.md` files into formal RDF ontologies. This guide covers how to write skills that are concise, well-structured, and effective.

---

## Core Principles

### Concise is Key

The context window is shared with everything else Claude needs. Challenge each piece of information:

- "Does Claude really need this explanation?"
- "Can I assume Claude knows this?"
- "Does this paragraph justify its token cost?"

**Good** (~50 tokens):
```markdown
## Extract PDF text

Use pdfplumber for text extraction:

\`\`\`python
import pdfplumber

with pdfplumber.open("file.pdf") as pdf:
    text = pdf.pages[0].extract_text()
\`\`\`
```

**Bad** (~150 tokens):
```markdown
## Extract PDF text

PDF (Portable Document Format) files are a common file format that contains
text, images, and other content. To extract text from a PDF, you'll need to
use a library. There are many libraries available for PDF processing, but
pdfplumber is recommended because it's easy to use and handles most cases well.
First, you'll need to install it using pip. Then you can use the code below...
```

### Set Appropriate Degrees of Freedom

Match specificity to the task's fragility:

| Freedom Level | When to Use | Example |
|---------------|-------------|---------|
| **High** | Multiple valid approaches | "Review code for bugs and suggest improvements" |
| **Medium** | Preferred pattern exists | "Use this template and customize as needed" |
| **Low** | Exact sequence required | "Run exactly: `python migrate.py --verify`" |

### Test with All Models

Skills behave differently across models:

- **Haiku**: Does the skill provide enough guidance?
- **Sonnet**: Is the skill clear and efficient?
- **Opus**: Does the skill avoid over-explaining?

---

## SKILL.md Structure

### YAML Frontmatter

```yaml
---
name: pdf-processing
description: Extracts text and tables from PDF files. Use when working with PDFs, forms, or document extraction.
---
```

**Name requirements:**
- Max 64 characters
- Lowercase letters, numbers, hyphens only
- No reserved words ("anthropic", "claude")

**Description requirements:**
- Max 1024 characters
- Write in third person
- Include both what and when

### Body Sections

A well-structured SKILL.md:

```markdown
# Skill Title

Brief one-line nature statement.

## What It Does

Concise description of capabilities.

## When To Use

Triggers for skill activation.

## How To Use

Step-by-step instructions or code examples.

## Knowledge

Guidelines, heuristics, anti-patterns (optional but recommended).
```

---

## Writing Effective Descriptions

The `description` field is critical for skill discovery. Claude uses it to choose from potentially 100+ skills.

**Good examples:**

```yaml
description: Extract text and tables from PDF files, fill forms, merge documents. Use when working with PDF files or when the user mentions PDFs, forms, or document extraction.
```

```yaml
description: Analyze Excel spreadsheets, create pivot tables, generate charts. Use when analyzing .xlsx files, spreadsheets, or tabular data.
```

**Avoid:**

```yaml
description: Helps with documents
```

```yaml
description: Processes data
```

---

## Progressive Disclosure

Keep SKILL.md under 500 lines. Split content when approaching this limit.

### Pattern: High-level Guide with References

```
pdf/
├── SKILL.md          # Main instructions (loaded when triggered)
├── FORMS.md          # Form-filling guide (loaded as needed)
├── reference.md      # API reference (loaded as needed)
└── scripts/
    └── analyze.py    # Utility script
```

SKILL.md:
```markdown
# PDF Processing

## Quick Start
[Brief instructions here]

## Advanced Features
- **Form filling**: See [FORMS.md](FORMS.md)
- **API reference**: See [reference.md](reference.md)
```

### Keep References One Level Deep

```markdown
# Bad: Too deep
SKILL.md → advanced.md → details.md → actual-info.md

# Good: One level
SKILL.md → advanced.md
SKILL.md → reference.md
SKILL.md → examples.md
```

---

## Workflows and Feedback Loops

### Use Workflows for Complex Tasks

```markdown
## PDF Form Filling Workflow

Copy this checklist and track progress:

- [ ] Step 1: Analyze the form
- [ ] Step 2: Create field mapping
- [ ] Step 3: Validate mapping
- [ ] Step 4: Fill the form
- [ ] Step 5: Verify output

**Step 1: Analyze the form**
Run: `python scripts/analyze_form.py input.pdf`

**Step 2: Create field mapping**
Edit `fields.json` to add values...

[Continue with clear steps]
```

### Implement Validation Loops

```markdown
## Document Editing Process

1. Make edits to `word/document.xml`
2. **Validate immediately**: `python scripts/validate.py`
3. If validation fails:
   - Review the error message
   - Fix issues
   - Re-run validation
4. Only proceed when validation passes
```

---

## Knowledge Nodes

OntoSkills extracts structured knowledge from your SKILL.md. Write clear sections that map to node types:

### PreFlightCheck

```markdown
## Before You Start

Verify wkhtmltopdf is installed:
\`\`\`bash
which wkhtmltopdf || brew install wkhtmltopdf
\`\`\`

This prevents "command not found" errors during PDF generation.
```

### AntiPattern

```markdown
## Common Mistakes

**Do not** accept file paths from untrusted input. This enables path traversal attacks.

Instead, validate against a whitelist of allowed directories.
```

### Heuristic

```markdown
## Tips

For large spreadsheets (>10k rows), process in chunks of 1000 to avoid memory issues.
```

See [Knowledge Extraction](/knowledge-extraction/) for all 26 node types.

---

## Common Patterns

### Template Pattern

```markdown
## Report Structure

ALWAYS use this exact format:

\`\`\`markdown
# [Analysis Title]

## Executive Summary
[One paragraph]

## Key Findings
- Finding 1
- Finding 2

## Recommendations
1. Action item
\`\`\`
```

### Examples Pattern

```markdown
## Commit Message Format

**Example 1:**
Input: Added JWT authentication
Output:
\`\`\`
feat(auth): implement JWT authentication

Add login endpoint and token validation
\`\`\`

**Example 2:**
Input: Fixed date bug in reports
Output:
\`\`\`
fix(reports): correct timezone handling

Use UTC consistently in date formatting
\`\`\`
```

---

## Anti-Patterns to Avoid

### Windows-Style Paths

```markdown
# Bad
scripts\\helper.py
reference\\guide.md

# Good
scripts/helper.py
reference/guide.md
```

### Too Many Options

```markdown
# Bad: Paralyzing choice
"You can use pypdf, or pdfplumber, or PyMuPDF, or pdf2image..."

# Good: Clear default with escape hatch
"Use pdfplumber for text extraction. For scanned PDFs requiring OCR, use pdf2image with pytesseract."
```

### Assuming Tools Are Installed

```markdown
# Bad
"Use the pdf library to process the file."

# Good
"Install: `pip install pypdf`

Then:
\`\`\`python
from pypdf import PdfReader
reader = PdfReader("file.pdf")
\`\`\`"
```

---

## Compilation

After writing your SKILL.md, compile it:

```bash
ontoskills install core
ontoskills init-core
ontoskills compile my-skill
```

### What Happens During Compilation

1. **Parsing**: Extracts structure from markdown
2. **LLM Extraction**: Identifies knowledge nodes using Claude
3. **SHACL Validation**: Verifies required fields exist
4. **RDF Generation**: Produces `ontoskill.ttl`

### Common Validation Errors

| Error | Fix |
|-------|-----|
| "Missing resolvesIntent" | Add a clear "When To Use" section |
| "Nature not extracted" | Add a one-line summary at the top |
| "SHACL violation" | Ensure the skill has clear structure |

Run with `-v` for details:
```bash
ontoskills compile my-skill -v
```

---

## Checklist

Before publishing a skill:

**Core Quality**
- [ ] Description includes what and when
- [ ] SKILL.md under 500 lines
- [ ] No time-sensitive information
- [ ] Consistent terminology throughout
- [ ] Examples are concrete, not abstract

**Structure**
- [ ] References one level deep
- [ ] Progressive disclosure used
- [ ] Workflows have clear steps
- [ ] Validation loops included

**Code**
- [ ] Scripts handle errors explicitly
- [ ] Required packages listed
- [ ] Forward slashes in paths
- [ ] No magic numbers

**Testing**
- [ ] Compiles without errors
- [ ] Tested with real scenarios
- [ ] Knowledge nodes extracted correctly

---

## Next Steps

- [Knowledge Extraction](/knowledge-extraction/) — Understanding all 26 node types
- [OntoCore](/ontocore/) — Compiler reference
- [Getting Started](/getting-started/) — Compile your first skill
