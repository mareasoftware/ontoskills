# run.py Refactoring Design

## Goal
Eliminare ~70% boilerplate duplicato tra i 3 runner (`_run_skillsbench_acp`, `_run_skillsbench_task_first`, `_run_skillsbench_taskwise`) e migliorare la CLI con `--dry-run`, `--skip-tasks`, e `--max-tasks` default a tutti i task.

## Architecture

### Unico runner configurabile

```python
def _run_skillsbench(output_dir, *, cases, ...):
```

Accetta una lista di `(mode, hints)` e gestisce tutto: loading task, creazione stati, binding runner, esecuzione, salvataggio risultati.

Le 3 funzioni attuali diventano wrapper:
```python
def _run_skillsbench_acp(...):
    return _run_skillsbench(output_dir, cases=[("acp", not args.no_skill_hints)], ...)

def _run_skillsbench_taskwise(...):
    return _run_skillsbench(output_dir, cases=[...3 casi...], ...)

def _run_skillsbench_task_first(...):
    return _run_skillsbench(output_dir, cases=[...5 casi...], ...)
```

### CASE_RUNNERS dict

Runner factories rimosse, sostituite da un dict module-level:
```python
_CASE_RUNNERS = {
    "baseline": lambda w, nudge: _acp_runner(w, skills_dir=None, skill_nudge=nudge),
    "acp": lambda w, nudge: _acp_runner(w, skills_dir=..., skill_nudge=nudge),
    "acp-mcp": lambda w, nudge: _mcp_runner(w, skill_nudge=nudge),
}
```

### Helpers estratti

- `_prepare_states(output_dir, cases, force_restart)` → crea/carica gli stati
- `_save_case_results(states, cases, labels, output_dir)` → salva results/score/chart per ogni caso
- `_build_runners(wrapper, cases)` → produce lista trial_runners dal dict

### CLI changes

- `--max-tasks` default: `None` → tutti i task con skill compilate
- `--skip-tasks`: comma-separated, passato a `load_tasks(skip_tasks=...)`
- `--dry-run`: stampa riepilogo (task, casi, workers, stima durata) senza eseguire

### Data flow

```
CLI args → _run_skillsbench(cases, ...)
  → wrapper.load_tasks(max_tasks, skip_tasks, ...)
  → if dry_run: print summary; return
  → states = _prepare_states(...)
  → runners = _build_runners(wrapper, cases)
  → asyncio.run(wrapper._run_pooled(...))  # se 1 caso
     or asyncio.run(wrapper._run_pooled_task_first(...))  # se multi-caso
  → _save_case_results(...)
```

## Files
- `benchmark/run.py`: riscritto, ~350 righe (da 694)
- `benchmark/tests/test_run.py`: test per `--dry-run`, `--skip-tasks`, runner dict

## Verdict
Funzionale, nessun cambiamento di comportamento. Il codice risultante sarà più facile da estendere con nuovi casi/modi.
