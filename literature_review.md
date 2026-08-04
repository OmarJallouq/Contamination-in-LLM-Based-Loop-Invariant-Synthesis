# Literature Review — LLM vs. Classical Loop Invariant Synthesis

**Thesis working title:** *Guessing Loop Invariants: Do Language Models Beat Templates, or Just Reach Different Programs?*

**One-line framing:** Guessing a loop invariant is undecidable; checking one is automatic. This asymmetry lets an unreliable LLM be paired with a sound verifier. But if the verifier provides all the guarantees, does the LLM actually beat a classical candidate generator — and does it solve *different* programs (complementarity)? We measure this on Dafny, with an objective verifier oracle, against a properly-implemented classical baseline that most prior work omits.

Papers are grouped by their role in the argument. Each entry: **citation** — summary — **relevance to us**.

---

## 1. Classical invariant inference (what our baseline is built on)

**Flanagan & Leino (2001), "Houdini, an Annotation Assistant for ESC/Java," FME 2001.**
Pioneered template-based inference: generate a pool of candidate annotations, then use the verifier to filter to the largest mutually-inductive subset (a fixpoint).
**Relevance:** This *is* our filtering algorithm. Both our baseline and our hybrid arm use a Houdini-style filter. We implement the isolation variant and discuss the fixpoint/mutual-support tradeoff.

**Ernst et al. (2007), "The Daikon system for dynamic detection of likely invariants," Science of Computer Programming.**
The canonical template-based invariant detector. Instantiates a fixed grammar of templates (variable bounds, comparisons, simple relations) over program variables and retains those consistent with observed executions.
**Relevance:** Our baseline's linear template family (Family A) is the Daikon grammar. Critically, the literature notes Daikon templates are "hardly sufficient for full functional correctness" — which predicts and legitimizes our low classical baseline (14.4%), showing it reproduces a documented limitation rather than being an implementation artifact.

**Furia & Meyer (2009), "Inferring Loop Invariants using Postconditions."**
Rather than guessing blindly like Daikon, this leverages the *postcondition*: it weakens/mutates the postcondition (e.g. replacing the terminal bound with the loop counter) to derive candidate invariants, restricting the search to high-quality candidates.
**Relevance:** This is exactly our function-aware + postcondition-weakening baseline (Families B and C). It is the citable justification for the strongest part of our classical baseline — the part that lets it solve quantified invariants like `forall k :: 0<=k<i ==> ...`.

**Cousot & Cousot (1977), "Abstract interpretation."** / **Gulwani et al. (2008), template-based parametric solvers.**
Heavier static-analysis methods: over-approximate reachable states via numeric domains (intervals, octagons, polyhedra), or assume an invariant shape and solve for parameters.
**Relevance:** Cited as *richer classical baselines we deliberately do not implement* — they are full static-analysis engines, out of scope for a BSc, and drift from "the simple classical method." Naming them scopes our baseline honestly.

---

## 2. LLM-based invariant synthesis (the direct prior work)

**Kamath et al. (2023/2024), "Finding Inductive Loop Invariants using Large Language Models" (LOOPY), arXiv:2311.07948, FMCAD 2024.** ← CLOSEST PRIOR WORK
LLM generates candidate invariants for C programs; a Houdini adaptation filters them; the LLM repairs incorrect ones. Three techniques: domain-specific prompting, Houdini filtering, LLM repair.
**Relevance:** This is the paper we are closest to and must differentiate from. Key differences: (1) they use **C + Frama-C**; we use **Dafny** (cleaner integrated oracle, different contamination profile, out of the C monoculture). (2) They report LLM+Houdini success but their baseline is a full model checker, not a *template generator* — we add the controlled classical-template baseline. (3) Their own finding that Houdini "helps weaker models catch up with GPT-4" motivates our capability-scaling study. (4) They also observed a *verifier ceiling* (10 cases correct-but-unverifiable), analogous to our ceiling analysis.

**Wu et al. (2024a), "LaM4Inv" / "LLM Meets Bounded Model Checking," ASE 2024.**
Iteratively queries the LLM and uses bounded model checking (BMC) to filter and reassemble candidate predicates across rounds.
**Relevance:** A different filter (BMC vs. Houdini) and a reassembly strategy. Contrast point for our hybrid design; also C-based.

**Wu et al. (2024b), "LEMUR: Integrating LLMs in Automated Program Verification," ICLR 2024.**
Neuro-symbolic framework with backtracking to repair invalid invariants; a sequential decision process using the base solver to check correctness.
**Relevance:** Represents the "complex iterative/backtracking" school. Our design is deliberately simpler (fixed repair budget) — a scope contrast worth stating.

**Chakraborty et al. (2023), "Ranking LLM-Generated Loop Invariants for Program Verification," EMNLP Findings.**
Uses contrastive ranking to order LLM-generated invariants so the correct one is tried sooner.
**Relevance:** An efficiency angle on the same generate-and-filter paradigm; relevant if we analyze candidate-pool efficiency (how many LLM candidates survive filtering).

**Pei et al. (2023), "Can Large Language Models Reason about Program Invariants?" (ICML).**
Early demonstration that LLMs can hypothesize invariants; explored fine-tuning on Daikon outputs.
**Relevance:** Establishes the basic capability we build on; the fine-tuning direction is one we explicitly do *not* take (we characterize off-the-shelf models).

**Chakraborty/Ebner et al. (2024), "SpecGen: Automated Generation of Formal Program Specifications via LLMs," arXiv:2401.08807.**
Generates verifiable specifications (Java/JML), including loop invariants; verified 279/385 programs, reported to outperform Houdini and Daikon.
**Relevance:** Shows LLMs beating classical tools on *spec generation* — but on Java/JML and without our controlled template baseline. A comparison point and a reminder to scope our claim to invariant synthesis specifically.

---

## 3. Neuro-symbolic / generate-and-verify framing

**"A Neurosymbolic Approach to Loop Invariant Generation via Weakest Precondition Reasoning," arXiv:2512.15816 (2025).**
Recent neuro-symbolic method using weakest-precondition reasoning; evaluates against SpecGen, Daikon, Houdini.
**Relevance:** Current example of the neuro-symbolic framing (the pitch to a neuro-symbolic supervisor). Situates our unsound-generator + sound-filter architecture in the live literature.

**"Guiding LLM-based Loop Invariant Synthesis via Feedback on Local Reasoning Errors," arXiv:2605.17914 (2026).**
Uses fine-grained verifier feedback (which condition failed, which variable assignments) to guide LLM invariant generation.
**Relevance:** Directly relevant to our repair-loop / feedback design. Their feedback-guidance idea is a candidate ablation for us (does richer verifier feedback improve LLM success?).

**Learning-augmented algorithms framing (Lykouris & Vassilvitskii 2018; and A. Polak's work on algorithms with untrusted predictions).**
General paradigm: an untrusted predictor wired into an algorithm that keeps worst-case guarantees regardless of prediction quality (consistency vs. robustness).
**Relevance:** The theoretical framing for the supervisor. Our pipeline is an instance: the LLM is the untrusted predictor, the Houdini filter guarantees *unconditional* soundness. Bad predictions cost completeness, never correctness.

---

## 4. Benchmarks & evaluation (corpus and metrics)

**Loughridge et al. (2024), "DafnyBench: A Benchmark for Formal Software Verification," (sun-wendy/DafnyBench).** ← OUR CORPUS
782–785 Dafny programs with `ground_truth` (invariants intact) and `hints_removed` (stripped) versions.
**Relevance:** Our data source. We censused it (517 loop+invariant programs, 303 single-loop), established a 62% ceiling, and scoped to 188 programs. Its authors explicitly flag GitHub-scrape *contamination* and name program mutation as unaddressed future work — which is exactly our planned contamination study.

**Wei et al. (2025), "InvBench" (ICLR, openreview 6UJiwWUt2o).** ← THE COMPARISON WE MUST NOT DUPLICATE
Evaluates 7 LLMs and LLM-based verifiers against the classical solver UAutomizer on C. Finds LLM-based verifiers do *not yet* offer a significant advantage over the classical tool.
**Relevance:** Two-edged. (1) It already did "LLM vs. classical" *on C* — so our contribution must be the Dafny setting + structural/complementarity analysis, not a bare comparison. (2) Its "no significant advantage in aggregate" finding, combined with Loopy's "some benchmarks only the LLM solves," implies *complementarity nobody has mapped* — which is our central question.

**Pinto et al. (2026), "Not All Invariants Are Equal: Curating Training Data to Accelerate Program Verification with SLMs" (ICML 2026).**
Data-curation pipeline (WONDA) to fine-tune small models for invariant synthesis; a fine-tuned 4B model matches a 120B baseline. Critiques standard "speedup" metrics and notes solver-generated invariants are "technically correct but structurally obfuscated."
**Relevance:** (1) Different axis (fine-tuning) — we deliberately do *not* fine-tune, avoiding a compute race we'd lose. (2) Their "technically correct but ineffective/obfuscated" observation is a quality dimension beyond verifies/doesn't-verify, usable in our failure taxonomy. (3) Recent, top-venue — good to cite for currency.

**"LLM For Loop Invariant Generation and Fixing: How Far Are We?" arXiv:2511.06552 (2025).**
Recent survey-style evaluation of LLM invariant generation and repair; examines whether verifier feedback improves fixing.
**Relevance:** Confirms the field is actively asking our exact question; a source for framing and for the repair-feedback design.

---

## How each cluster maps to our contribution

- **Cluster 1** justifies our baseline as two canonical, cited methods (Daikon + Furia-Meyer), making its ~14% solve rate a *reproduction of a known limitation*, not a weak strawman.
- **Cluster 2** is what we differentiate from: prior LLM work is C-centric, rarely runs a controlled *template* baseline, and reports aggregates rather than *which* programs each method solves.
- **Cluster 3** gives the framing (neuro-symbolic / learning-augmented) and candidate ablations (feedback richness).
- **Cluster 4** supplies the corpus (DafnyBench), the comparison we must differentiate from (InvBench), and evaluation critiques we build on (WONDA).

**The gap we fill:** a controlled, Dafny-based comparison of a properly-implemented classical baseline vs. off-the-shelf LLMs vs. a hybrid, focused not on aggregate win-rate but on **complementarity** (do neural and symbolic methods solve *different* programs?) and a **structural difficulty model** (which program features predict which method wins), with **contamination** treated as a first-class variable via program mutation.

---

## Open questions to raise with supervisor

1. **Baseline strength:** Is Daikon + Furia-Meyer (14.4%) the right classical baseline, or should we add richer families (risking "we built a solver")?
2. **Language choice:** Confirm Dafny over C — differentiates from InvBench, but sacrifices direct comparability with the C literature.
3. **Model spread:** Run across Haiku/Sonnet/Opus for a capability-scaling curve? (Loopy suggests Houdini helps weaker models catch up.)
4. **Centre of gravity:** Is *complementarity* the right headline, or the *structural difficulty model*?
