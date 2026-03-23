# Design: Documentation Overhaul

**Data:** 2025-03-23
**Status:** Approved
**Component:** OntoCore (primo), poi OntoMCP, CLI, OntoStore

---

## Obiettivo

Pulizia, valorizzazione e standardizzazione della documentazione EN/ZH per riflettere la qualità del lavoro svolto.

**Criteri di successo:**
1. Un developer può iniziare da zero leggendo la doc
2. La doc riflette la qualità e profondità del sistema
3. Pronta per open source/community

---

## Tono e Stile

**Professionale rilassato** — competente ma accessibile, senza formalismi eccessivi.

> "OntoCore compila skill markdown in ontologie OWL 2. Il risultato? Query deterministiche, ogni volta."

**NO:**
- Formalismo aziendale ("Si prega di notare che...")
- Gergo inutile
- Atteggiamento

**SÌ:**
- Chiaro e diretto
- Esempi pratici
- Voci attive

---

## Framework: Diátaxis

4 tipi di documentazione:

| Tipo | Orientamento | Scopo |
|------|--------------|-------|
| **Tutorial** | Apprendimento | Guidare un nuovo utente passo-passo |
| **How-to Guide** | Problema | Risolvere un problema specifico |
| **Reference** | Informazione | Descrizione tecnica, dizionario |
| **Explanation** | Comprensione | Capire il "perché" |

---

## Approccio: Audit → Gap Analysis → Fill

Non si riparte da zero. Si rispetta il lavoro esistente.

### Fase 1: Audit

**Output:** `AUDIT.md`

Catalogare tutti i file esistenti con:
- Nome file
- Dimensione
- Ultima modifica
- Rilevanza per il componente (Alta/Media/Bassa)
- Qualità (Buono/Da migliorare/Obsoleto)

### Fase 2: Mapping

**Output:** `MAPPING.md`

Mappare ogni file su un quadrante Diátaxis:
- Dove si colloca?
- Ci sono sovrapposizioni?
- Quali quadranti sono vuoti?

### Fase 3: Gap Analysis

**Output:** `GAP-ANALYSIS.md` + TODO list

Per ogni file:
- ✅ Mantenere (buono)
- ⚠️ Aggiornare (contenuto ok, tono/struttura da rifare)
- ❌ Riscrivere (contenuto obsoleto)
- 🔲 Creare (argomento non coperto)

### Fase 4: Fill

Lavorare un file alla volta:
- Seguire template Diátaxis
- Tono professionale rilassato
- Revisione dopo ogni file

---

## OntoCore — Matrice Diátaxis

### Tutorial (Apprendimento)
- "La tua prima skill compilata"
- "Setup ambiente di sviluppo"
- "Compilare da zero"

### How-to Guide (Problema)
- "Come strutturare una SKILL.md valida"
- "Come usare i 26 Knowledge Node types"
- "Come scrivere State Transitions corrette"
- "Come configurare la security pipeline"
- "Come risolvere errori SHACL comuni"

### Reference (Informazione)
- API extractor reference
- Schemas Pydantic (ExtractedSkill, KnowledgeNode, etc.)
- CLI commands reference
- SHACL shapes reference
- Security patterns reference

### Explanation (Comprensione)
- "Perché OWL 2 + SHACL?"
- "La Knowledge Architecture (10 dimensioni)"
- "Filosofia neuro-simbolica"
- "Pipeline di compilazione end-to-end"

---

## File Rilevanti per OntoCore

| File | Target Quadrante |
|------|------------------|
| `docs/getting-started.md` | Tutorial |
| `docs/compiler.md` | Reference |
| `docs/architecture.md` | Explanation |
| `docs/knowledge-extraction.md` | Explanation |
| `docs/cli.md` | Reference |
| `docs/overview.md` | Explanation |

---

## Piano di Esecuzione

```
FASE 1: AUDIT (1-2 ore)
├── Leggere tutti i file docs/ rilevanti
├── Valutare qualità e rilevanza
└── Output: AUDIT.md

FASE 2: MAPPING (30 min)
├── Mappare ogni file su Diátaxis
├── Identificare sovrapposizioni e gap
└── Output: MAPPING.md

FASE 3: GAP ANALYSIS (30 min)
├── Confrontare con la matrice ideale
├── Prioritizzare: aggiornare vs riscrivere vs creare
└── Output: GAP-ANALYSIS.md + TODO list

FASE 4: FILL (variabile)
├── Lavorare un file alla volta
├── Tono: professionale rilassato
├── Revisione dopo ogni file
└── Output: docs/ aggiornati

FASE 5: TRADUZIONE ZH (dopo EN completo)
└── Tradurre tutto in docs/zh/
```

---

## Ordine Componenti

1. **OntoCore** — Il compilatore Python, cuore del sistema
2. **OntoMCP** — Il server MCP in Rust
3. **CLI** — I comandi `ontoskills ...`
4. **OntoStore** — Il registry/skill store

---

## Templates Diátaxis

### Tutorial
```markdown
# Titolo: [Obiettivo dell'utente]

## Obiettivo
Cosa imparerai a fare

## Prerequisiti
- Cosa serve prima di iniziare

## Passi
1. Primo passo
2. Secondo passo
...

## Risultato atteso
Cosa hai ottenuto alla fine

## Next steps
Dove andare dopo
```

### How-to Guide
```markdown
# Titolo: [Problema da risolvere]

## Problema
Descrizione del problema

## Soluzione
Approccio generale

## Passi
1. ...
2. ...

## Note
Avvertenze, alternative
```

### Reference
```markdown
# Titolo: [Nome API/Classe/Comando]

## Descrizione breve
Una frase

## Sintassi/Signature
```code```

## Parametri/Proprietà
| Nome | Tipo | Descrizione |
|------|------|-------------|

## Esempi
```code```

## Vedi anche
Link correlati
```

### Explanation
```markdown
# Titolo: [Concetto da spiegare]

## Contesto
Perché stiamo parlando di questo

## Il problema
Cosa cerchiamo di risolvere

## La soluzione
Come funziona

## Trade-offs
Pro e contro

## Vedi anche
Approfondimenti
```
