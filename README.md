# ⚙️🧠 Skill Ontology ETL

**The semantic compiler for the Agentic Web.** `skill-ontology-etl` is an LLM-powered ETL (Extract, Transform, Load) pipeline designed to bridge the gap between human-readable documentation and machine-executable logic. It compiles unstructured agent skills (Markdown) into a strict, deterministic **RDF/Turtle knowledge graph** for zero-hallucination agent routing.

## 🎯 The Problem: Context Rot & Hallucinations

Current AI agent frameworks (like OpenClaw or ZeroClaw) often rely on "Skills" written in Markdown. While easy for humans to write, they suffer from:

* **Context Rot:** Large skill files saturate the LLM's context window.
* **Ambiguity:** Small or local LLMs struggle to parse complex prerequisites in raw text.
* **Non-Determinism:** The agent might "hallucinate" how to use a tool because the instructions are buried in prose.

## 💡 The Solution: Semantic Compilation

This tool acts as an **Offline Compiler**. It "digests" your raw skills and produces a structured **Ontology** based on W3C standards (RDF/SPARQL).

Instead of reading a 200-line Markdown file, your agent simply queries a **Knowledge Graph** to find exactly what it needs:

1. **Intent Identification:** What is the user actually asking for?
2. **Prerequisite Check:** Do I have the hardware/API keys required?
3. **Deterministic Execution:** What is the exact shell command or Python script to run?

## 🛠 Features

* **LLM-Powered Extraction:** Uses Structured Outputs (Pydantic) to ensure 100% schema compliance.
* **Ontological Rigor:** Organizes knowledge by *Substance* and *Relations* (e.g., `depends-on`, `implements`, `extends`).
* **Agentic Payload:** Specifically extracts the "trigger" code for autonomous execution.
* **Security Guardrails:** Built-in detection for prompt injection or malicious commands within skill files.
* **SPARQL Ready:** Generates `.ttl` (Turtle) files compatible with engines like **Oxigraph** or **Rudof**.

## 🏗 Architecture

1. **Extract:** Scans the `./skills/` folder for `.md` files.
2. **Transform:** LLM analyzes the text and maps it to the `Knowledge Architecture` framework.
3. **Load:** Serializes the semantic data into a unified `ontology/skills.ttl` graph.

## 🚀 Getting Started

### Prerequisites

* Python 3.11+
* An LLM API Key (OpenAI, Anthropic, or local provider)

### Installation

```bash
git clone https://github.com/your-username/skill-ontology-etl.git
cd skill-ontology-etl
pip install -r requirements.txt

```

### Configuration

Set your API key in your environment:

```bash
export LLM_API_KEY="your-api-key-here"

```

### Usage

Place your Markdown skill files in the `/skills` directory and run:

```bash
python compiler.py

```

The compiled ontology will be generated at `./ontology/skills.ttl`.

## 📄 Example Ontology Output

The compiler transforms prose into machine-readable triples:

```turtle
@prefix ag: <http://agentic.web/ontology#> .

ag:flipper_subghz_tx a ag:AgenticSkill ;
    ag:nature "Hardware Interaction Tool" ;
    ag:resolvesIntent "open_gate", "transmit_subghz" ;
    ag:requiresHardware "flipper_zero_usb" ;
    ag:hasPayload "flipper-cli serial tx {freq} {file}" .

```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
