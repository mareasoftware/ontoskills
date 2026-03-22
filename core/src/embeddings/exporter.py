"""Export embeddings for semantic intent discovery."""

import json
from pathlib import Path
from typing import Any

from rdflib import Graph, Namespace
from rich.console import Console

console = Console()


OC = Namespace("https://ontoskills.sh/ontology#")
DCTERMS = Namespace("http://purl.org/dc/terms/")
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


def extract_intents_from_ontology(ontology_path: Path) -> list[dict[str, Any]]:
    """Extract all intents and source their associated skills from ontology.

    Uses dcterms:identifier for skill IDs (production format) rather than
    URI fragments, ensuring compatibility with compiled ontologies.

    Args:
        ontology_path: Path to Turtle ontology file.

    Returns:
        List of dicts with 'intent' and 'skills' keys.
    """
    g = Graph()
    g.parse(ontology_path, format="turtle")

    # Use dcterms:identifier for skill IDs (production format)
    # Falls back to URI fragment if identifier is missing
    query = """
    PREFIX oc: <https://ontoskills.sh/ontology#>
    PREFIX dcterms: <http://purl.org/dc/terms/>

    SELECT ?skill ?intent ?skillId
    WHERE {
        ?skill oc:resolvesIntent ?intent .
        OPTIONAL { ?skill dcterms:identifier ?skillId }
    }
    """

    intent_to_skills: dict[str, list[str]] = {}
    for row in g.query(query):
        # Use dcterms:identifier if available, otherwise fall back to URI fragment
        if row.skillId:
            skill_id = str(row.skillId)
        else:
            skill_id = str(row.skill).split("#")[-1].split("/")[-1]
        intent = str(row.intent)

        if intent not in intent_to_skills:
            intent_to_skills[intent] = []
        if skill_id not in intent_to_skills[intent]:
            intent_to_skills[intent].append(skill_id)

    return [
        {"intent": intent, "skills": skills}
        for intent, skills in intent_to_skills.items()
    ]


def export_embeddings(
    ontology_root: Path,
    output_dir: Path,
) -> None:
    """Export ONNX model, tokenizer, and pre-computed intent embeddings.

    Args:
        ontology_root: Root directory containing ontology TTL files.
        output_dir: Directory to write embedding artifacts.

    Raises:
        ImportError: If optimum is not available (required for ONNX export).
    """
    from sentence_transformers import SentenceTransformer
    from transformers import AutoTokenizer
    from optimum.exporters.onnx import main_export

    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load model and export to ONNX (required - no fallback)
    console.print(f"[blue]Loading model:[/] {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)

    console.print("[yellow]Exporting ONNX model...")
    main_export(
        MODEL_NAME,
        output=output_dir,
        task="feature-extraction",
    )
    console.print(f"[green]Exported ONNX model to[/] {output_dir}")

    # 2. Export tokenizer
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    tokenizer.save_pretrained(str(output_dir))
    console.print(f"[green]Exported tokenizer to[/] {output_dir}")

    # 3. Extract and embed intents
    # Always scan all .ttl files to capture skills (index.ttl only has owl:imports)
    all_intents = []
    for ttl_file in ontology_root.rglob("*.ttl"):
        all_intents.extend(extract_intents_from_ontology(ttl_file))

    # Deduplicate intents
    intent_map: dict[str, list[str]] = {}
    for item in all_intents:
        intent = item["intent"]
        if intent not in intent_map:
            intent_map[intent] = []
        intent_map[intent].extend(item["skills"])

    unique_intents = [
        {"intent": intent, "skills": sorted(set(skills))}
        for intent, skills in sorted(intent_map.items())
    ]

    if not unique_intents:
        console.print("[yellow]No intents found in ontology")
        intents_data = {
            "model": MODEL_NAME,
            "dimension": EMBEDDING_DIM,
            "intents": [],
        }
        intents_path = output_dir / "intents.json"
        with open(intents_path, "w") as f:
            json.dump(intents_data, f)
        console.print(f"[green]Exported empty intent embeddings to[/] {intents_path}")
        return

    # Compute embeddings (normalize for cosine similarity)
    intent_strings = [item["intent"] for item in unique_intents]
    console.print(f"[blue]Computing embeddings for[/] {len(intent_strings)} [blue]intents...")

    embeddings = model.encode(intent_strings, convert_to_numpy=True, normalize_embeddings=True)

    # Build output
    intents_data = {
        "model": MODEL_NAME,
        "dimension": EMBEDDING_DIM,
        "intents": [
            {
                "intent": item["intent"],
                "embedding": emb.tolist(),
                "skills": item["skills"],
            }
            for item, emb in zip(unique_intents, embeddings)
        ],
    }

    intents_path = output_dir / "intents.json"
    with open(intents_path, "w") as f:
        json.dump(intents_data, f)

    console.print(f"[green]Exported[/] {len(unique_intents)} [green]intent embeddings to[/] {intents_path}")
