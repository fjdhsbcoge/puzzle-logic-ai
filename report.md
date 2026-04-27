# Puzzle Logic: Concrete Applications in Philosophy of Science, Epistemology, and Scientific Methodology

## Research Summary

This report identifies **8 strong candidates** where the core principles of "Puzzle Logic" (empirical-only knowledge assembly, constraint propagation, structural falsification, convergent self-correction) have been explicitly articulated or operationalized in philosophy of science and scientific methodology. Each framework is evaluated on how it embodies the puzzle-logic principles, whether it has been operationalized into algorithms or procedures, and what performance metrics could verify it.

---

## Candidate 1: Bridgman's Operationalism

**Framework/Philosophy:** Operationalism / Operational Analysis  
**Key Proponent:** Percy Williams Bridgman (1882-1961), Nobel Prize-winning physicist  
**Primary Work:** *The Logic of Modern Physics* (1927)

### How It Embodies Puzzle-Logic Principles

| Puzzle-Logic Principle | Bridgman's Operationalism |
|------------------------|---------------------------|
| Reality as jigsaw puzzle of empirical measurements | **Exact match**: "The concept is synonymous with the corresponding set of operations" (1927, p. 5). Concepts like "length" do not exist abstractly; there is only ruler-length, triangulation-length, radar-length, etc. |
| Pieces connect via logical/mathematical constraints | **Exact match**: Different measurement operations for the same term must give convergent results in overlapping domains, or they are different concepts. Numerical convergence is the constraint that binds pieces together. |
| False claim has no slot | **Exact match**: "If a specific question has meaning, it must be possible to find operations by which an answer may be given to it." (1927, p. 28). A claim without corresponding operations is meaningless — it has no slot. |
| All knowledge from empirical data, no abstract axioms | **Exact match**: Bridgman explicitly sought to eradicate metaphysical concepts (like Newton's "absolute time") by tying every concept to concrete measurement operations. |
| Small-scale first | **Exact match**: Bridgman opened his discussion with the most mundane concept — length — to show that even prosaic cases reveal operational complexity. |
| Constraint propagation | **Exact match**: "If we deal with phenomena outside the domain in which we originally defined our concepts, we may find physical hindrances...so that the original operations have to be replaced by others." Each new measurement constrains what operations are valid. |
| Convergence → clearer picture | **Exact match**: "These new operations are...to be so chosen that they give, within experimental error, the same numerical results in the domain in which the two sets of operations may be both applied." Convergence justifies using the same name. |
| Rejection: contradictory measurements stand out | **Exact match**: If measurement operations fail to converge in their overlap, they are different concepts. Bridgman: "our verbal machinery has no built-in cutoff." |
| Falsifiable by structure | **Exact match**: A concept becomes meaningless when its operations break down. "Length loses its meaning at lengths less than the size of the electron because such lengths cannot be measured." |

### Operationalization
- **Operationalized as measurement practice**: Operational definitions are now standard across the social sciences, psychology, physics, and engineering.
- **Legacy**: The practice of defining abstract concepts as measurable variables is the primary operationalist legacy in science today.
- **Computational**: Not a formal algorithm, but measurement protocols are procedural and replicable.

### Performance Metrics
- **Prediction accuracy**: Convergence of different operational definitions in overlapping domains
- **False-positive rejection**: Detection when concepts are used beyond their operational domains
- **Convergence rate**: Degree of numerical agreement between different measurement operations

### References
- Bridgman, P.W. (1927). *The Logic of Modern Physics*. New York: Macmillan.
- Stanford Encyclopedia of Philosophy entry on Operationalism: https://plato.stanford.edu/entries/operationalism/
- Routledge Encyclopedia of Philosophy: https://www.rep.routledge.com/articles/thematic/operationalism/v-1
- Green, C.D. "Of Immortal Mythological Beasts: Operationism in Psychology": http://www.yorku.ca/christo/papers/operat.htm

---

## Candidate 2: Deborah Mayo's Error Statistics / Severity Framework

**Framework/Philosophy:** Error Statistics / Severe Testing  
**Key Proponent:** Deborah G. Mayo (Virginia Tech)  
**Primary Works:** *Error and the Growth of Experimental Knowledge* (1996); *Statistical Inference as Severe Testing* (2018); papers with Aris Spanos

### How It Embodies Puzzle-Logic Principles

| Puzzle-Logic Principle | Mayo's Error Statistics |
|------------------------|-------------------------|
| Reality as jigsaw puzzle of empirical measurements | **Strong match**: Knowledge is built from "piecemeal results" assembled into incisive arguments. Data enters through sampling distributions and error probabilities. |
| Pieces connect via logical/mathematical constraints | **Exact match**: The severity function SEV(Test T, data x, claim C) mathematically constrains what claims are warranted by what data. Error probabilities bound erroneous interpretations. |
| False claim has no slot | **Exact match**: "A claim is severely tested to the extent that it has been subjected to and passes a test that probably would have found flaws, were they present." A false claim that would have produced a more discordant outcome has no slot — it fails severity. |
| All knowledge from empirical data | **Strong match**: "Experience is determined only by experience." Error statistics uses only relative frequencies of outcomes and sampling distributions derived from data. |
| Small-scale first | **Strong match**: Mayo explicitly builds from simple statistical significance tests to more complex inferences, checking assumptions at each stage. |
| Constraint propagation | **Exact match**: Each test result constrains what discrepancies can be inferred. "Failing to falsify hypotheses, while rarely allowing their acceptance as precisely true, may warrant excluding various discrepancies, errors or rivals." |
| Convergence → clearer picture | **Strong match**: "Inductive inference requires building up incisive arguments and inferences by putting together several different piece-meal results." More severe tests → higher confidence. |
| Rejection: contradictory measurements stand out | **Exact match**: The error-statistical framework is designed to detect when biasing selection effects, violations of model assumptions, or unwarranted interpretations corrupt inferences. |
| Falsifiable by structure | **Exact match**: Mayo formalizes Popper's intuition: "An inquiry is falsified by showing its inability to severely probe the question of interest." Not argument but structural inability to test. |

### Operationalization
- **Fully operationalized**: Error-statistical methods (significance tests, confidence intervals, resampling, randomization) are standard statistical algorithms implemented in software worldwide.
- **Algorithm**: The severity function SEV() is computable. The framework demands:
  1. Specification of test hypothesis H
  2. Test statistic d(X)
  3. Sampling distribution under H
  4. Computation of severity for specific inferences
- **Auditing protocol**: Severity requires explicit auditing for biasing selection effects, model assumption violations, and unwarranted substantive interpretations.

### Performance Metrics
- **Severity values**: SEV(Test T, data x, claim C) ∈ [0,1]
- **False-positive rate**: Controlled via Type I error probabilities
- **Power**: Probability test would detect flaws if present
- **Convergence rate**: How severity increases with more independent severe tests
- **Rejection accuracy**: Rate at which false claims fail severity

### References
- Mayo, D.G. (2018). *Statistical Inference as Severe Testing*. Cambridge University Press.
- Mayo, D.G. & Spanos, A. (2011). "Error Statistics." In *Philosophy of Statistics*, Elsevier.
- Mayo, D.G. (1996). *Error and the Growth of Experimental Knowledge*. University of Chicago Press.
- Haig, B.D. review of SIST: https://sites.stat.columbia.edu/gelman/research/unpublished/mayo_reviews.pdf
- Mayo's severity seminar slides (2024): https://errorstatistics.com/wp-content/uploads/2024/10/final-9-october-mayo-neyman-seminar.pdf
- Dynamic Ecology blog on severity: https://dynamicecology.wordpress.com/2012/11/28/why-and-how-to-do-statistics-its-probably-not-why-and-how-you-think/

---

## Candidate 3: William Wimsatt's Robustness Analysis

**Framework/Philosophy:** Robustness Analysis / Multiple-Access Realism  
**Key Proponent:** William C. Wimsatt (University of Michigan)  
**Primary Work:** "Robustness, Reliability, and Overdetermination" (1981); *Re-Engineering Philosophy for Limited Beings* (2007)

### How It Embodies Puzzle-Logic Principles

| Puzzle-Logic Principle | Wimsatt's Robustness Analysis |
|------------------------|------------------------------|
| Reality as jigsaw puzzle of empirical measurements | **Exact match**: "To analyze a variety of independent derivation, identification, or measurement processes...to look for and analyze things that are invariant over or identical in the conclusions or results of these processes." |
| Pieces connect via logical/mathematical constraints | **Exact match**: The invariance across independent processes is the constraint that binds pieces together. "X is robust = X remains invariant under a multiplicity of (at least partially) independent derivations." |
| False claim has no slot | **Strong match**: If a result is not robust across independent methods, it is likely artifactual — it doesn't fit into the multi-method structure. |
| All knowledge from empirical data | **Strong match**: Robustness analysis uses only independent empirical detection/manipulation processes. No reliance on abstract axioms. |
| Small-scale first | **Strong match**: Wimsatt applies robustness to everyday cases (sensory modalities, experimental procedures) before theoretical entities. |
| Constraint propagation | **Exact match**: "To analyze and explain any relevant failures of invariance." Each new method tested either supports or undermines the robustness claim, propagating constraints across the system. |
| Convergence → clearer picture | **Exact match**: "Robustness is the primary criterion for reality and for error detection." More independent methods converging → higher confidence in reality of target. |
| Rejection: contradictory measurements stand out | **Exact match**: Failures of invariance (when methods disagree) are explicitly analyzed to determine whether the target is non-robust or one method is biased. |
| Falsifiable by structure | **Strong match**: A non-robust result is rejected not by argument but by its inability to remain invariant across independent access methods. |

### Operationalization
- **Operationalized as scientific practice**: Robustness analysis is a standard meta-scientific practice across biology, physics, social psychology, and linguistics.
- **Procedural framework**: The four-step robustness procedure is algorithmic:
  1. Analyze variety of independent derivation/identification/measurement processes
  2. Look for invariant conclusions/results
  3. Determine scope of invariance and conditions of dependence
  4. Analyze and explain failures of invariance
- **Computational**: Used in model selection, multi-sensor fusion, and sensor validation.

### Performance Metrics
- **Robustness index**: Degree of invariance across independent methods
- **Independence measure**: Degree of methodological independence between access processes
- **Artifact detection rate**: Frequency with which non-robust results are identified as artifacts
- **Convergence reliability**: Rate at which robust results survive further testing

### References
- Wimsatt, W.C. (1981/2007). "Robustness, Reliability, and Overdetermination." In *Re-Engineering Philosophy for Limited Beings*, Harvard University Press.
- Wimsatt, W.C. (2007). *Re-Engineering Philosophy for Limited Beings*. Harvard University Press.
- Houkes, W., Seselja, D., & Vaesen, K. "Robustness analysis." https://philsci-archive.pitt.edu/22010/1/12_Houkes_Seselja_Vaesen_Robustness.pdf
- Kuorikoski, J., Lehtinen, A., & Marchionni, C. (2010). "Robustness and Reality." *Synthese*.

---

## Candidate 4: Sneed-Stegmuller Structuralism (The Structuralist Theory of Science)

**Framework/Philosophy:** Structuralist View of Scientific Theories  
**Key Proponents:** Joseph D. Sneed (1971), Wolfgang Stegmuller (1973+), with Patrick Suppes  
**Primary Work:** Sneed, *The Logical Structure of Mathematical Physics* (1971); Stegmuller, *The Structure and Dynamics of Theories* (1976)

### How It Embodies Puzzle-Logic Principles

| Puzzle-Logic Principle | Sneed-Stegmuller Structuralism |
|------------------------|--------------------------------|
| Reality as jigsaw puzzle of empirical measurements | **Strong match**: Theories are not statements but "systems of systems" — mathematical structures linked to the world by measurement procedures. The "empirical claim" is that real systems bear the proposed structure. |
| Pieces connect via logical/mathematical constraints | **Exact match**: The framework's core innovation is **constraints** (C) — second-order conditions that interconnect models of the same theory. "Models of one and the same empirical theory don't appear isolated; they are mutually related by certain second-order conditions." |
| False claim has no slot | **Strong match**: The Ramsey-Sneed sentence formulates the empirical claim using existential quantifiers for theoretical terms. If no theoretical components satisfy the constraints for given non-theoretical data, the claim has no slot. |
| All knowledge from empirical data | **Strong match**: T-non-theoretical concepts provide the "relative basis of data." Theoretical terms appear only as variables in the Ramsey-Sneed sentence. |
| Small-scale first | **Strong match**: Sneed used classical particle mechanics as the showcase, building from concrete measurement of mass and force. |
| Constraint propagation | **Exact match**: "If we measure the mass of the Earth on the basis of observations of the system Earth-Moon, the same number of Kgs has to be valid in any other system in which the Earth appears." Measurement results propagate across all applications. |
| Convergence → clearer picture | **Strong match**: The more applications of a theory are successfully constrained (same mass values, same constants across systems), the stronger the empirical claim. |
| Rejection: contradictory measurements stand out | **Exact match**: Constraints require that values measured in one system must be "exported" to all other systems containing the same entity. Contradictory values break the constraint structure. |
| Falsifiable by structure | **Exact match**: The Ramsey-Sneed sentence is the theory's empirical claim. If no assignment of theoretical functions satisfies the constraints for given partial potential models, the theory fails structurally. |

### Operationalization
- **Formalized framework**: Structuralism provides a formal metatheoretical apparatus (set-theoretic predicates, model theory) that has been applied to reconstruct dozens of scientific theories.
- **Computational**: Constraint propagation algorithms (AC-3, AC-4, etc.) are direct implementations of the structuralist constraint idea, though not originally developed for philosophy of science.
- **Theory reconstruction**: Used to formally analyze theory change, Kuhnian paradigms, and intertheoretic reduction.

### Performance Metrics
- **Constraint satisfaction rate**: Percentage of cross-system constraints satisfied
- **Model fit**: Degree to which empirical substructures embed into theoretical models
- **Convergence across applications**: Consistency of theoretical values across different physical systems
- **Approximation quality**: How well admissible blurs (A) fit real data

### References
- Sneed, J.D. (1971). *The Logical Structure of Mathematical Physics*. Reidel.
- Stegmuller, W. (1976). *The Structure and Dynamics of Theories*. Springer.
- Balzer, W., Moulines, C.U., & Sneed, J.D. (1987). *An Architectonic for Science*. Reidel.
- Stanford Encyclopedia of Philosophy on Structuralism in Physics: https://plato.stanford.edu/entries/physics-structuralism/
- Mapping Ignorance blog on Sneed: https://mappingignorance.org/2023/03/06/sneed-structuralism-and-t-theorecity/
- Structuralist Theory of Science preview: https://api.pageplace.de/preview/DT0400.9783110879421_A20011934/preview-9783110879421_A20011934.pdf

---

## Candidate 5: Hasok Chang's Pragmatic Realism / Operational Coherence

**Framework/Philosophy:** Pragmatic Realism / Activist Realism / Operational Coherence  
**Key Proponent:** Hasok Chang (University of Cambridge)  
**Primary Works:** *Is Water H2O?* (2012); "Pragmatism, Perspectivism, and the Historicity of Science"; *Realism for Realistic People* (2022)

### How It Embodies Puzzle-Logic Principles

| Puzzle-Logic Principle | Chang's Operational Coherence |
|------------------------|------------------------------|
| Reality as jigsaw puzzle of empirical measurements | **Exact match**: "A statement is true to the extent that there are operationally coherent activities that can be performed by relying on its content." Reality is built from concrete epistemic activities (measurements, detections, DNA extraction, match-lighting). |
| Pieces connect via logical/mathematical constraints | **Strong match**: "A putative entity should be considered real if it is employed in a coherent epistemic activity that relies on its existence and its basic properties." The coherence of the activity network is the constraint. |
| False claim has no slot | **Strong match**: If a claim cannot support operationally coherent activities — if the operations don't harmonize toward their aim — the claim is not true (in Chang's pragmatic sense). |
| All knowledge from empirical data | **Exact match**: Chang's "deep empiricism" rejects metaphysical explanations. "We can make concepts as we like, but whether the entities they specify turn out to be real is not up to us." |
| Small-scale first | **Exact match**: Chang's examples are deliberately mundane: match-lighting, DNA extraction, nuclei-location with DAPI staining. |
| Constraint propagation | **Strong match**: An epistemic activity (EA) has "inherent purpose" and "external function" within a "system of practice" (SP). The coherence requirements of the SP constrain individual EAs. |
| Convergence → clearer picture | **Strong match**: "The concrete realization of a coherent activity is successful, ceteris paribus." Success is the indirect criterion for coherence. More coherent activities → more reliable knowledge. |
| Rejection: contradictory measurements stand out | **Strong match**: Incompatible claims within the same SP threaten overall coherence. Chang's framework allows incompatible claims to be true in different SPs, but within one SP, inconsistency signals failure. |
| Falsifiable by structure | **Strong match**: A claim is "pragmatically true" only if it is needed in a coherent activity. If the activity's operations fail to harmonize, the claim loses its slot. |

### Operationalization
- **Partially operationalized**: Chang provides conceptual framework rather than algorithm, but "operational coherence" is defined in terms of concrete, observable operations.
- **Practice-based**: The framework directly guides how to evaluate scientific activities by their concrete success rather than abstract correspondence.
- **Historical case studies**: Chang applies the framework to detailed cases (temperature measurement, phlogiston chemistry, water composition).

### Performance Metrics
- **Operational coherence score**: Degree of harmonious fitting-together of operations in an activity
- **Success rate of epistemic activities**: Ceteris paribus, coherent activities should be successful
- **Cross-activity consistency**: Whether measured values transfer across different EAs in the same SP
- **Systematic conduciveness**: Whether conditions under which EAs are realized are mutually supportive

### References
- Chang, H. (2012). *Is Water H2O? Evidence, Realism and Pluralism*. Springer.
- Chang, H. (2022). *Realism for Realistic People: A New Pragmatist Philosophy of Science*. Cambridge University Press.
- Chang, H. (2018). "Pragmatism, Perspectivism, and the Historicity of Science." In *Perspectivism in Science*.
- Niiniluoto, I. "Ten queries about Hasok Chang's pragmatic realism": https://edition.fi/tup/catalog/download/language-truth-and-reality/1856/7092?inline=1
- Springer article probing operational coherence: https://link.springer.com/article/10.1007/s13194-021-00425-x
- PhilPapers entry: https://philpapers.org/rec/CHARFR-2
- Middlebury blog on Chang's pragmatism: https://sites.middlebury.edu/voluntarism/2021/04/04/hasok-changs-pragmatism-perspectivism-and-the-historicity-of-science/

---

## Candidate 6: Bootstrap Methods / Cross-Validation (Self-Correcting Statistical Science)

**Framework/Philosophy:** Resampling / Bootstrap / Cross-Validation  
**Key Proponents:** Bradley Efron (1979), Julian Simon (1960s precursor), modern ML/statistics community  
**Primary Work:** Efron, "Bootstrap Methods: Another Look at the Jackknife" (1979); Efron & Tibshirani (1993)

### How It Embodies Puzzle-Logic Principles

| Puzzle-Logic Principle | Bootstrap / Cross-Validation |
|------------------------|------------------------------|
| Reality as jigsaw puzzle of empirical measurements | **Strong match**: The bootstrap generates an empirical distribution Pn from the data itself. "This empirical distribution allows us to estimate the distribution of the variable...even if we do not know the true distribution P." |
| Pieces connect via logical/mathematical constraints | **Strong match**: Each bootstrap sample must be drawn with replacement from the original empirical distribution. The resampling constraint ensures the synthetic data remains tethered to reality. |
| False claim has no slot | **Exact match**: Cross-validation evaluates models on held-out data. A model that overfits the training set but fails to predict validation data has no slot — it is rejected. |
| All knowledge from empirical data | **Exact match**: "The most fundamental idea of the bootstrap method is that we compute measures of our inference uncertainty from that estimated sampling distribution" — derived solely from the sample, with no parametric assumptions. |
| Small-scale first | **Exact match**: Bootstrap starts with a single sample and resamples from it. CV splits data into training/validation sets. Both are fundamentally small-scale, data-driven operations. |
| Constraint propagation | **Exact match**: In cross-validation, parameters estimated from training data are constrained by their performance on validation data. The validation error propagates back to constrain model selection. |
| Convergence → clearer picture | **Exact match**: As sample size increases, the bootstrap distribution converges to the true sampling distribution. CV scores converge to identify the true model with probability approaching 1. |
| Rejection: contradictory measurements stand out | **Exact match**: "A model can be misspecified...the false model is said to be locally misspecified if...the sample moment of the misspecified model converges to zero slower than that of the true model." CV detects this. |
| Falsifiable by structure | **Exact match**: "The algorithm identifies a correctly specified model from misspecified models with the probability approaching to 1 as the number of data increases." Falsification by structural inability to predict held-out data. |

### Operationalization
- **Fully operationalized as algorithms**: Bootstrap and cross-validation are standard computational procedures in statistics and machine learning.
- **Algorithm (Bootstrap)**:
  1. Draw random samples with replacement from observed data
  2. Compute statistic of interest for each bootstrap sample
  3. Use distribution of bootstrap statistics to estimate sampling distribution
- **Algorithm (Cross-Validation)**:
  1. Split data into training and validation sets
  2. Estimate model parameters on training set
  3. Evaluate on validation set
  4. Select model with lowest validation error
- **Implemented**: In every major statistical software package (R, Python, MATLAB, SAS).

### Performance Metrics
- **Bootstrap convergence**: How closely bootstrap distribution approximates true sampling distribution
- **CV consistency**: Probability of selecting true model approaches 1 as n → ∞
- **False model rejection rate**: How often misspecified models are correctly rejected
- **Overfitting detection**: Difference between training and validation error
- **Mean squared error / standard error**: Bootstrap estimates of uncertainty

### References
- Efron, B. (1979). "Bootstrap Methods: Another Look at the Jackknife." *Annals of Statistics*, 7(1), 1-26.
- Efron, B. & Tibshirani, R. (1993). *An Introduction to the Bootstrap*. Chapman & Hall.
- Komiyama, J. & Shimao, H. (2017). "Cross Validation Based Model Selection via Generalized Method of Moments." https://www.aeaweb.org/conference/2018/preliminary/paper/EsDSaQeB
- Medium article on Bootstrap with Python: https://medium.com/@jumbongjunior/resampling-method-bootstrap-efron-explained-and-application-using-python-a54e6e1406f8
- Elder Research on Efron and Simon: https://www.elderresearch.com/blog/efron-simon-and-the-bootstrap/
- Yang, X. "Cross-Validation for Selecting a Model Selection Procedure": http://users.stat.umn.edu/~yangx374/papers/ACV_v30.pdf

---

## Candidate 7: John Platt's Strong Inference

**Framework/Philosophy:** Strong Inference / Systematic Hypothesis Elimination  
**Key Proponent:** John R. Platt (biophysicist, University of Chicago)  
**Primary Work:** "Strong Inference" (1964), published in *Science*

### How It Embodies Puzzle-Logic Principles

| Puzzle-Logic Principle | Platt's Strong Inference |
|------------------------|--------------------------|
| Reality as jigsaw puzzle of empirical measurements | **Strong match**: "The difference comes in their systematic application." Science progresses by systematically testing multiple hypotheses against experimental data. |
| Pieces connect via logical/mathematical constraints | **Strong match**: Each crucial experiment is designed so that "alternative possible outcomes, each of which will, as nearly as possible, exclude one or more of the hypotheses." The logical structure of exclusion is the constraint. |
| False claim has no slot | **Exact match**: "Each hypothesis must be testable in this process, with the objective of the test being to effectively kill the hypothesis with a definitive experiment." A hypothesis that produces a discordant outcome is excluded — it has no slot. |
| All knowledge from empirical data | **Strong match**: The method requires "carrying out the experiment so as to get a clean result." No hypothesis survives without empirical support. |
| Small-scale first | **Strong match**: Platt gives examples of rapid progress in molecular biology and physics through systematic application of simple steps. |
| Constraint propagation | **Strong match**: The recycling step ("making subhypotheses or sequential hypotheses to refine the possibilities that remain") propagates constraints from eliminated hypotheses to the remaining ones. |
| Convergence → clearer picture | **Strong match**: "It is like climbing a tree." Each eliminated hypothesis narrows the branch of possibilities. Eventually only one hypothesis remains standing. |
| Rejection: contradictory measurements stand out | **Exact match**: "All it takes is a single data point. If by logical reasoning and accompanying experimentation the proposed hypothesis doesn't lead to the specific consequence, then the hypothesis is assumed to be false and must be removed from consideration." |
| Falsifiable by structure | **Exact match**: A hypothesis is rejected not by argument but by its inability to produce the predicted consequence in the crucial experiment. |

### Operationalization
- **Operationalized as scientific method**: Strong inference is explicitly presented as a systematic method that can be "formally and explicitly and regularly" applied.
- **Procedural framework**: The four-step method is algorithmic:
  1. Devise alternative hypotheses
  2. Devise a crucial experiment (or several) with alternative outcomes that exclude hypotheses
  3. Carry out the experiment to get a clean result
  4. Recycle: make subhypotheses and repeat
- **Taught in practice**: Strong inference is explicitly taught in some scientific training programs as a deliberate methodology.

### Performance Metrics
- **Hypothesis elimination rate**: How many hypotheses are excluded per experiment
- **Convergence speed**: How quickly the method narrows to a single hypothesis
- **False-negative rate**: Rate at which true hypotheses are incorrectly excluded
- **Experimental efficiency**: Number of experiments required to reach conclusion
- **Reproducibility**: Rate at which strong inference results are replicated

### References
- Platt, J.R. (1964). "Strong Inference." *Science*, 146(3642), 347-353.
- Robert Hanlon blog: https://robertthanlon.com/2022/09/08/science-and-the-power-of-multiple-hypotheses/
- LessWrong summary: https://www.lesswrong.com/posts/F7pihuF8qRbJ6WTue/link-strong-inference
- Hendren Writing: https://www.hendrenwriting.com/showcase-entries/strong-inference

---

## Candidate 8: Judea Pearl's Do-Calculus / Causal Inference Framework

**Framework/Philosophy:** Causal Inference / Do-Calculus / Structural Causal Models  
**Key Proponent:** Judea Pearl (UCLA)  
**Primary Works:** *Causality* (2000); *The Book of Why* (2018); papers with Galles, Robins, Huang, Valtorta

### How It Embodies Puzzle-Logic Principles

| Puzzle-Logic Principle | Pearl's Do-Calculus |
|------------------------|---------------------|
| Reality as jigsaw puzzle of empirical measurements | **Strong match**: Causal queries are expressed as do-expressions (e.g., P(y|do(x),z)). The framework determines whether causal effects can be computed from purely observational data. |
| Pieces connect via logical/mathematical constraints | **Exact match**: The do-calculus consists of three inference rules that permit mapping between interventional and observational distributions based on d-separation conditions in the causal graph. These are formal constraints. |
| False claim has no slot | **Exact match**: If a causal effect is not identifiable, "there exists no sequence of applications of the rules of the do-calculus that transforms the causal effect formula into one that only includes observational quantities." The claim has no slot in the data. |
| All knowledge from empirical data | **Strong match**: The framework explicitly transforms expressions involving interventions (do-operators) into expressions involving only observations — "ordinary conditional probabilities, which is assessable by empirical observation." |
| Small-scale first | **Strong match**: Pearl's framework starts with simple causal graphs (back-door, front-door criteria) before complex derivations. |
| Constraint propagation | **Exact match**: Rule 1 extends d-separation; Rule 2 permits exchange of do(z) with observation z; Rule 3 allows insertion/deletion of actions. Each rule application propagates constraints through the graph. |
| Convergence → clearer picture | **Strong match**: The completeness theorem proves that if a causal effect is identifiable, a sequence of rule applications will transform it into an observational formula. The algorithm is guaranteed to converge. |
| Rejection: contradictory measurements stand out | **Strong match**: If the causal graph structure is incompatible with the data (e.g., observed conditional independences violate d-separation), the model is falsified. |
| Falsifiable by structure | **Exact match**: Huang & Valtorta (2006) proved completeness: "If a causal effect is identifiable, there exists a sequence of applications of the rules of the do-calculus that transforms the causal effect formula into a formula that only includes observational quantities." If not identifiable, the structural constraints explicitly block inference. |

### Operationalization
- **Fully operationalized as algorithms**: The do-calculus has been implemented in multiple software packages (causaleffect, dagitty, pcalg in R).
- **Algorithm**: The identifiability algorithm by Huang & Valtorta:
  1. Represent causal assumptions as directed acyclic graph (DAG)
  2. Express causal query as do-expression
  3. Apply do-calculus rules 1-3 systematically
  4. If query reduces to observational formula → identifiable; if algorithm reports failure → not identifiable
- **Formal completeness**: Proven sound and complete (Huang & Valtorta 2006).

### Performance Metrics
- **Identifiability rate**: Percentage of causal queries that can be identified from given graph structure
- **Bias reduction**: Degree to which do-calculus removes confounding bias vs. naive conditioning
- **Graph recovery accuracy**: Rate at which causal structure learning algorithms recover true graph
- **Transportability success**: Rate at which causal effects transfer across populations
- **Computational efficiency**: Time complexity of identifiability algorithm (polynomial in number of variables)

### References
- Pearl, J. (2000). *Causality: Models, Reasoning, and Inference*. Cambridge University Press.
- Pearl, J. (2012). "The Do-Calculus Revisited." Keynote lecture. https://ftp.cs.ucla.edu/pub/stat_ser/r402.pdf
- Huang, Y. & Valtorta, M. (2006). "Pearl's Calculus of Intervention Is Complete." *Proceedings of UAI*. https://arxiv.org/pdf/1206.6831
- Bareinboim, E. & Pearl, J. "On Pearl's Hierarchy and the Foundations of Causal Inference." https://causalai.net/r60.pdf
- ActiveLoop AI glossary: https://www.activeloop.ai/resources/glossary/pearls-causal-calculus/
- Behavioral Data Science taster: https://www.behavioral-ds.science/theme1_content/causal_inference_taster/

---

## Summary Table

| # | Framework | Proponent | Puzzle-Logic Match | Operationalized? | Key Metric |
|---|-----------|-----------|-------------------|-------------------|------------|
| 1 | Bridgman's Operationalism | P.W. Bridgman | **Exact** | Yes (measurement protocols) | Operational convergence |
| 2 | Error Statistics / Severity | Deborah Mayo | **Exact** | Yes (statistical algorithms) | Severity SEV(T,x,C) |
| 3 | Robustness Analysis | William Wimsatt | **Exact** | Yes (scientific practice) | Invariance across methods |
| 4 | Structuralism (Sneed-Stegmuller) | Sneed, Stegmuller | **Exact** | Yes (formal metatheory) | Constraint satisfaction |
| 5 | Operational Coherence | Hasok Chang | **Strong** | Partially (practice-based) | Coherence/success rate |
| 6 | Bootstrap / Cross-Validation | Efron, et al. | **Exact** | Yes (computational algorithms) | CV consistency |
| 7 | Strong Inference | John Platt | **Strong** | Yes (procedural method) | Hypothesis elimination rate |
| 8 | Do-Calculus | Judea Pearl | **Exact** | Yes (complete algorithm) | Identifiability rate |

---

## Cross-Cutting Themes

### 1. **Constraint Propagation as a Unifying Mechanism**
All eight frameworks feature some form of constraint propagation:
- Bridgman: operational definitions constrain conceptual extension
- Mayo: error probabilities constrain inferential claims
- Wimsatt: invariance constraints across independent methods
- Sneed-Stegmuller: second-order constraints (C) link theory applications
- Chang: SP coherence constrains individual EAs
- Bootstrap/CV: validation error constrains model selection
- Platt: experimental outcomes constrain hypothesis space
- Pearl: do-calculus rules propagate d-separation constraints

### 2. **Structural Falsification vs. Argumentative Falsification**
A key puzzle-logic principle is "falsifiable by structure, not by argument." This is most explicit in:
- **Mayo**: "An inquiry is falsified by showing its inability to severely probe the question of interest"
- **Pearl**: Non-identifiability means the causal query structurally cannot be answered from the data
- **Sneed-Stegmuller**: If no theoretical assignment satisfies constraints, the empirical claim fails structurally
- **CV**: Misspecified models fail by their inability to predict held-out data

### 3. **Convergence as Epistemic Criterion**
All frameworks use convergence as a sign of validity:
- Bridgman: numerical convergence of different operations
- Mayo: piecemeal assembly of severe tests
- Wimsatt: invariance across independent methods
- Sneed-Stegmuller: consistent values across applications
- Chang: systematic success across EAs
- Bootstrap/CV: convergence to true distribution
- Platt: convergence to single surviving hypothesis
- Pearl: convergence to identifiable causal effect

### 4. **Computational Implementability**
Five of the eight frameworks have been fully operationalized as algorithms (Mayo, Bootstrap/CV, Pearl, Sneed's formalism, Platt's procedure). Two are operationalized as standard scientific practice (Bridgman, Wimsatt). One provides a practice-based conceptual framework (Chang).

---

## Files Generated

- `/mnt/agents/output/report.md` — This comprehensive report
