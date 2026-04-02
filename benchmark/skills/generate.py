"""Generate synthetic SKILL.md files for benchmarking."""

import os
import sys
import random

SKILL_TEMPLATES = [
    {
        "name": "pdf-generator",
        "description": "Generate PDF documents from templates",
        "intents": ["create_pdf", "export_pdf", "generate_document"],
        "states": {"requires": ["template_loaded"], "yields": ["pdf_created"]},
        "steps": [
            "Load the template from the specified path",
            "Populate template variables with provided data",
            "Render the PDF using the template engine",
            "Write the output to the specified file path",
            "Verify the PDF was created successfully",
        ],
        "knowledge": [
            {"type": "Standard", "content": "Always use UTF-8 encoding for PDF generation"},
            {"type": "AntiPattern", "content": "Never generate PDFs in memory for large documents — use streaming"},
            {"type": "Heuristic", "content": "If template has > 100 variables, batch the population"},
        ],
    },
    {
        "name": "excel-exporter",
        "description": "Export data to Excel spreadsheets",
        "intents": ["export_excel", "create_spreadsheet", "write_xlsx"],
        "states": {"requires": ["data_prepared"], "yields": ["excel_created"]},
        "steps": [
            "Initialize the workbook with proper sheets",
            "Write headers with formatting",
            "Populate data rows",
            "Apply conditional formatting",
            "Save the workbook to disk",
        ],
        "knowledge": [
            {"type": "Standard", "content": "Use openpyxl for .xlsx format compatibility"},
            {"type": "AntiPattern", "content": "Do not load entire dataset into memory before writing"},
            {"type": "PreFlightCheck", "content": "Verify data types match column expectations"},
        ],
    },
    {
        "name": "api-authenticator",
        "description": "Handle API authentication with various methods",
        "intents": ["authenticate_api", "refresh_token", "validate_credentials"],
        "states": {"requires": ["credentials_available"], "yields": ["authenticated"]},
        "steps": [
            "Load credentials from secure storage",
            "Determine authentication method (OAuth, API key, JWT)",
            "Perform authentication handshake",
            "Store the session token",
            "Set up automatic token refresh",
        ],
        "knowledge": [
            {"type": "Security", "content": "Never log credentials or tokens"},
            {"type": "Heuristic", "content": "Prefer OAuth 2.0 for third-party APIs"},
            {"type": "AntiPattern", "content": "Do not store tokens in plain text files"},
        ],
    },
    {
        "name": "database-migrator",
        "description": "Run database migrations with rollback support",
        "intents": ["run_migration", "rollback_migration", "check_migration_status"],
        "states": {"requires": ["db_connected"], "yields": ["migration_complete"]},
        "steps": [
            "Check current migration version",
            "Validate migration files",
            "Create a backup snapshot",
            "Apply migrations in order",
            "Verify schema integrity",
        ],
        "knowledge": [
            {"type": "Standard", "content": "Always run migrations inside a transaction"},
            {"type": "AntiPattern", "content": "Never skip migration version numbers"},
            {"type": "PreFlightCheck", "content": "Verify backup exists before applying destructive migrations"},
        ],
    },
    {
        "name": "email-sender",
        "description": "Send emails with templates and attachments",
        "intents": ["send_email", "send_template_email", "send_with_attachment"],
        "states": {"requires": ["smtp_configured"], "yields": ["email_sent"]},
        "steps": [
            "Load the email template",
            "Render template with variables",
            "Attach files if specified",
            "Connect to SMTP server",
            "Send the email and confirm delivery",
        ],
        "knowledge": [
            {"type": "Standard", "content": "Use TLS for SMTP connections"},
            {"type": "AntiPattern", "content": "Do not send bulk emails synchronously"},
            {"type": "Heuristic", "content": "Queue emails > 100 recipients for batch processing"},
        ],
    },
    {
        "name": "file-compressor",
        "description": "Compress and decompress files in various formats",
        "intents": ["compress_file", "decompress_archive", "create_zip"],
        "states": {"requires": [], "yields": ["file_compressed"]},
        "steps": [
            "Determine compression format from extension",
            "Read source files",
            "Apply compression algorithm",
            "Write compressed output",
            "Verify archive integrity",
        ],
        "knowledge": [
            {"type": "Standard", "content": "Use gzip for single files, zip for multiple files"},
            {"type": "Heuristic", "content": "For files > 1GB, use streaming compression"},
        ],
    },
    {
        "name": "image-resizer",
        "description": "Resize and optimize images for web delivery",
        "intents": ["resize_image", "optimize_image", "create_thumbnail"],
        "states": {"requires": ["image_loaded"], "yields": ["image_processed"]},
        "steps": [
            "Load the image file",
            "Determine target dimensions and format",
            "Apply resize with proper aspect ratio",
            "Optimize for web (quality, compression)",
            "Save to output path",
        ],
        "knowledge": [
            {"type": "Standard", "content": "Use Lanczos resampling for downscaling"},
            {"type": "AntiPattern", "content": "Do not upscale images beyond 2x original size"},
            {"type": "Heuristic", "content": "WebP is preferred for web delivery over JPEG/PNG"},
        ],
    },
    {
        "name": "json-transformer",
        "description": "Transform JSON data between schemas",
        "intents": ["transform_json", "map_json_schema", "convert_data_format"],
        "states": {"requires": ["schema_defined"], "yields": ["data_transformed"]},
        "steps": [
            "Parse the input JSON",
            "Load the transformation schema",
            "Map source fields to target fields",
            "Apply data type conversions",
            "Validate output against target schema",
        ],
        "knowledge": [
            {"type": "Standard", "content": "Validate input before transformation"},
            {"type": "AntiPattern", "content": "Do not mutate the input data directly"},
        ],
    },
    {
        "name": "log-analyzer",
        "description": "Parse and analyze application logs",
        "intents": ["analyze_logs", "parse_log_file", "extract_errors"],
        "states": {"requires": [], "yields": ["log_analysis_complete"]},
        "steps": [
            "Detect log format (syslog, JSON, plain text)",
            "Parse log entries",
            "Extract error patterns and stack traces",
            "Generate statistics (error rate, frequency)",
            "Produce analysis report",
        ],
        "knowledge": [
            {"type": "Heuristic", "content": "For log files > 100MB, use streaming parser"},
            {"type": "AntiPattern", "content": "Do not load entire log file into memory"},
            {"type": "PreFlightCheck", "content": "Verify file encoding before parsing"},
        ],
    },
    {
        "name": "ssh-connector",
        "description": "Establish SSH connections and run remote commands",
        "intents": ["ssh_connect", "run_remote_command", "transfer_file_scp"],
        "states": {"requires": ["ssh_key_available"], "yields": ["ssh_connected"]},
        "steps": [
            "Load SSH key or credentials",
            "Establish connection to remote host",
            "Verify host fingerprint",
            "Execute remote command",
            "Capture and return output",
        ],
        "knowledge": [
            {"type": "Security", "content": "Always verify host fingerprints"},
            {"type": "AntiPattern", "content": "Never use password authentication in production"},
            {"type": "Standard", "content": "Use connection pooling for multiple commands"},
        ],
    },
]


def generate_skill_md(template: dict, index: int) -> str:
    """Generate a SKILL.md string from a template."""
    name = template["name"]
    desc = template["description"]
    intents_yaml = "\n".join(f"  - {i}" for i in template["intents"])
    req = template["states"]["requires"]
    yld = template["states"]["yields"]

    steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(template["steps"]))
    knowledge_text = "\n".join(
        f"- **{k['type']}**: {k['content']}" for k in template["knowledge"]
    )

    req_yaml = "\n".join(f"  - {r}" for r in req) if req else "  []"
    yld_yaml = "\n".join(f"  - {y}" for y in yld) if yld else "  []"

    return f"""---
name: {name}
version: "1.{index}.0"
description: {desc}
intents:
{intents_yaml}
requiresState:
{req_yaml}
yieldsState:
{yld_yaml}
---

# {name}

{desc}

## Instructions

{steps_text}

## Knowledge

{knowledge_text}

## Examples

```
# Basic usage
{name} --input data.json --output result.out

# With options
{name} --input data.json --output result.out --verbose --dry-run
```

## Error Handling

- If input file is not found, report clear error message
- If processing fails mid-way, clean up partial output
- If output path is not writable, suggest alternative locations

## Dependencies

- Requires Python 3.10+
- Standard library only for core functionality
"""


def generate_variants(base_templates: list[dict], count: int) -> list[dict]:
    """Generate variant skills by modifying base templates."""
    variants = []
    suffixes = [
        "advanced", "lite", "pro", "enterprise", "cloud", "local",
        "streaming", "batch", "async", "sync", "parallel", "cached",
        "secure", "fast", "minimal", "extended", "modular", "hybrid",
    ]
    prefixes = [
        "aws", "azure", "gcp", "docker", "k8s", "redis",
        "postgres", "mongodb", "elasticsearch", "kafka",
    ]

    random.seed(42)
    for i in range(count):
        base = base_templates[i % len(base_templates)]
        suffix = suffixes[(i // len(base_templates)) % len(suffixes)]
        prefix = prefixes[(i // (len(base_templates) * len(suffixes))) % len(prefixes)]

        name = f"{prefix}-{base['name']}-{suffix}"
        variant = {
            "name": name,
            "description": f"{base['description']} ({suffix} variant for {prefix})",
            "intents": [
                f"{base['intents'][0]}_{suffix}",
                f"{base['intents'][-1]}_{prefix}",
            ],
            "states": {
                "requires": base["states"]["requires"],
                "yields": [f"{base['states']['yields'][0]}_{suffix}"],
            },
            "steps": base["steps"],
            "knowledge": base["knowledge"],
        }
        variants.append(variant)
    return variants


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "."

    os.makedirs(output_dir, exist_ok=True)

    # First, write the base skills
    all_skills = list(SKILL_TEMPLATES)

    # Then generate variants to reach the target count
    if count > len(SKILL_TEMPLATES):
        variants = generate_variants(SKILL_TEMPLATES, count - len(SKILL_TEMPLATES))
        all_skills.extend(variants)

    all_skills = all_skills[:count]

    for i, skill in enumerate(all_skills):
        content = generate_skill_md(skill, i)
        filepath = os.path.join(output_dir, f"{skill['name']}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    print(f"Generated {len(all_skills)} skill files in {output_dir}")


if __name__ == "__main__":
    main()
