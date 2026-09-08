# Compile-time architecture breadth — supervised sparse B-v0

Date: 2026-09-08

## Result

The first deliberately minimal supervised sparse challenger does **not** beat the same-feature centroid control on the frozen A593 teacher corpus.

Fixed construction split: train phrase slots 0–6, test slot 7, 593 concepts / 593 held-out phrases. Both variants use the same char-word-boundary TF-IDF feature family; the challenger changes the objective from centroid similarity to a one-vs-rest linear hinge classifier.

- same-feature centroid, quantized top-300: **165/593 Top1 (27.82%)**, **355/593 Hit@5 (59.87%)**, MRR **0.4246**;
- supervised unpruned: **159/593 Top1 (26.81%)**, **267/593 Hit@5 (45.03%)**, MRR **0.3496**;
- supervised signed-int8 top-300: **147/593 Top1 (24.79%)**, **249/593 Hit@5 (41.99%)**, MRR **0.3263**.

The pruned supervised candidate is therefore **-18 Top1, -106 Hit@5 and -0.0983 MRR** versus its same-feature centroid control.

## Interpretation

This is a construction diagnostic, not a fresh transfer test, and it does not prove that every possible supervised sparse classifier is bad. It does answer the intended breadth question for the simplest obvious formulation: merely replacing centroid/BM25-like scoring with a linear discriminative objective does **not** reveal a higher ceiling here.

Per the breadth gate, do not start a hyperparameter/model sweep to rescue B-v0. That would recreate the local-optimisation pattern the breadth phase was introduced to stop. Freeze this formulation as a miss and move to the materially different task/activity representation C.

The compiled-size estimate is comfortably small enough that bytes are not the reason for rejection; quality is. The current estimate is structurally optimistic for gzip because ids/weights were represented by zero-filled bytes, so it must not be quoted as an actual shipping artifact size.

Evidence: `research/evaluation/v31/compile-time-semantic-a593-supervised-sparse-breadth.json`.
