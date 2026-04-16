use anyhow::Result;
use oxigraph::io::RdfFormat;
use oxigraph::model::Term;
use oxigraph::store::Store;
use std::env;
use std::fs::{self, File};
use std::io::BufReader;
use std::time::Instant;
use walkdir::WalkDir;

/// Benchmark results for a single query
#[derive(serde::Serialize)]
struct BenchResult {
    query_name: String,
    skill_count: usize,
    avg_us: u64,
    min_us: u64,
    max_us: u64,
    p50_us: u64,
    p99_us: u64,
    iterations: usize,
}

/// Overall benchmark report
#[derive(serde::Serialize)]
struct BenchReport {
    total_skills: usize,
    total_triples: usize,
    load_time_ms: u64,
    results: Vec<BenchResult>,
}

/// Extract the numeric value from a SPARQL COUNT binding.
/// Oxigraph terms for typed literals stringify as `"42"^^<...>`,
/// so we must extract the Literal's lexical form, not use to_string().
fn extract_count(bindings: &oxigraph::sparql::QuerySolution, index: usize) -> usize {
    bindings
        .get(index)
        .and_then(|term| match term {
            Term::Literal(lit) => lit.value().parse().ok(),
            _ => None,
        })
        .unwrap_or(0)
}

fn main() -> Result<()> {
    let args: Vec<String> = env::args().collect();
    let ttl_dir = args.get(1).map(|s| s.as_str()).unwrap_or("skills");
    let iterations: usize = args
        .get(2)
        .and_then(|s| s.parse().ok())
        .unwrap_or(1000);
    let output_path = args.get(3).map(|s| s.as_str()).unwrap_or("results/ontomcp-bench.json");

    println!("=== OntoMCP SPARQL Benchmark ===\n");

    // Load TTL files into oxigraph
    let store = Store::new()?;
    let start = Instant::now();

    let mut loaded_files = 0usize;

    for entry in WalkDir::new(ttl_dir).into_iter().filter_map(|e| e.ok()) {
        let path = entry.path();
        if path.extension().map(|e| e == "ttl").unwrap_or(false) {
            let reader = BufReader::new(File::open(path)?);
            match store.load_from_reader(RdfFormat::Turtle, reader) {
                Ok(_) => {
                    loaded_files += 1;
                }
                Err(e) => eprintln!("Warning: failed to load {}: {}", path.display(), e),
            }
        }
    }

    let load_time = start.elapsed();

    let oc = "https://ontoskills.sh/ontology#";

    // Count skills via SPARQL (authoritative, not substring matching)
    let total_skills: usize = {
        let query = format!("SELECT (COUNT(?s) AS ?count) WHERE {{ ?s a <{oc}Skill> }}");
        let results: Vec<_> = store.query(&query)?.into_bindings().collect();
        results.first().map(|r| extract_count(r, 0)).unwrap_or(0)
    };

    // Count triples
    let total_triples: usize = {
        let count_query = "SELECT (COUNT(*) AS ?count) WHERE { ?s ?p ?o }";
        let results: Vec<_> = store.query(count_query)?.into_bindings().collect();
        results.first().map(|r| extract_count(r, 0)).unwrap_or(0)
    };

    println!(
        "Loaded {} files ({} skills, {} triples) in {:.1}ms\n",
        loaded_files,
        total_skills,
        total_triples,
        load_time.as_secs_f64() * 1000.0,
    );

    // Define benchmark queries using the oc: namespace from core.ttl
    // Property names match the actual ontology: oc:hasDescription (not oc:description),
    // oc:directiveContent, oc:resolvesIntent, etc.
    let queries: Vec<(&str, String)> = vec![
        (
            "search (by intent)",
            format!(
                r#"SELECT ?skill ?desc WHERE {{
                    ?skill a <{oc}Skill> .
                    ?skill <{oc}resolvesIntent> "create_pdf" .
                    OPTIONAL {{ ?skill <{oc}hasDescription> ?desc }}
                }}"#
            ),
        ),
        (
            "search (by type)",
            format!(
                r#"SELECT ?skill WHERE {{
                    ?skill a <{oc}Skill> .
                    ?skill a <{oc}ExecutableSkill> .
                }}"#
            ),
        ),
        (
            "get_skill_context",
            format!(
                r#"SELECT ?skill ?p ?o WHERE {{
                    ?skill a <{oc}Skill> .
                    ?skill <{oc}resolvesIntent> "create_pdf" .
                    ?skill ?p ?o .
                }}"#
            ),
        ),
        (
            "query_epistemic_rules",
            format!(
                r#"SELECT ?node ?type ?content WHERE {{
                    ?node a ?type .
                    ?node a <{oc}KnowledgeNode> .
                    ?node <{oc}directiveContent> ?content .
                }}"#
            ),
        ),
        (
            "evaluate_execution_plan",
            format!(
                r#"SELECT ?skill WHERE {{
                    ?skill a <{oc}Skill> .
                    ?skill <{oc}resolvesIntent> "create_pdf" .
                    ?skill <{oc}requiresState> ?req .
                }}"#
            ),
        ),
        (
            "search (all — scan)",
            format!(
                r#"SELECT ?skill ?intent ?desc WHERE {{
                    ?skill a <{oc}Skill> .
                    OPTIONAL {{ ?skill <{oc}resolvesIntent> ?intent }}
                    OPTIONAL {{ ?skill <{oc}hasDescription> ?desc }}
                }}"#
            ),
        ),
    ];

    let mut results = Vec::new();

    for (name, query) in &queries {
        // Validate query once before timing (fail fast on errors)
        if let Err(e) = store.query(query.as_str()) {
            eprintln!("ERROR: query '{}' failed: {}", name, e);
            results.push(BenchResult {
                query_name: name.to_string(),
                skill_count: total_skills,
                avg_us: 0,
                min_us: 0,
                max_us: 0,
                p50_us: 0,
                p99_us: 0,
                iterations: 0,
            });
            continue;
        }

        // Guard against iterations == 0 to avoid panic on empty times vec
        if iterations == 0 {
            println!("{:<35} skipped (0 iterations)", name);
            results.push(BenchResult {
                query_name: name.to_string(),
                skill_count: total_skills,
                avg_us: 0,
                min_us: 0,
                max_us: 0,
                p50_us: 0,
                p99_us: 0,
                iterations: 0,
            });
            continue;
        }

        let mut times = Vec::with_capacity(iterations);

        for _ in 0..iterations {
            let start = Instant::now();
            // Materialize results to measure full execution, not just lazy setup
            let results = store.query(query.as_str()).unwrap();
            let count = match results {
                oxigraph::sparql::QueryResults::Solutions(solutions) => solutions.count(),
                oxigraph::sparql::QueryResults::Graph(graph) => graph.count(),
                _ => 0,
            };
            std::hint::black_box(count);
            times.push(start.elapsed().as_micros() as u64);
        }

        times.sort_unstable();

        let avg = times.iter().sum::<u64>() / times.len() as u64;
        let min = times[0];
        let max = times[times.len() - 1];
        let p50 = times[times.len() * 50 / 100];
        let p99 = times[times.len() * 99 / 100];

        println!(
            "{:<35} avg={:>6}μs  p50={:>6}μs  p99={:>6}μs  min={:>5}μs  max={:>6}μs",
            name, avg, p50, p99, min, max
        );

        results.push(BenchResult {
            query_name: name.to_string(),
            skill_count: total_skills,
            avg_us: avg,
            min_us: min,
            max_us: max,
            p50_us: p50,
            p99_us: p99,
            iterations,
        });
    }

    let report = BenchReport {
        total_skills,
        total_triples,
        load_time_ms: load_time.as_millis() as u64,
        results,
    };

    // Write JSON results
    if let Some(parent) = std::path::Path::new(output_path).parent() {
        fs::create_dir_all(parent)?;
    }
    let json = serde_json::to_string_pretty(&report)?;
    fs::write(output_path, &json)?;
    println!("\nResults written to {}", output_path);

    Ok(())
}
