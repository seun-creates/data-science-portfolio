# 03 · Customer Churn Prediction

Predicts which subscription customers will cancel and turns the model's scores into a retention-campaign decision with a measurable dollar value.

## Approach
1. **Leak-free protocol:** 20% test set held out until the very end. Model comparison and threshold choice use 5-fold stratified cross-validation on training data only.
2. **One pipeline:** imputation, scaling and one-hot encoding live inside the scikit-learn `Pipeline`, so they are fitted on training folds only.
3. **Honest comparison:** a majority-class baseline, logistic regression and gradient boosting, compared on ROC-AUC and average precision (better for imbalanced classes).
4. **Business threshold:** instead of the default 0.5, the threshold maximizes expected campaign value: `saved churners × 30% × $600 − contacts × $40`.

## Results (seed 42, 1,400 test customers, 18.6% churn)
| Model | CV ROC-AUC | CV avg. precision |
| --- | --- | --- |
| **Baseline (majority)** | 0.500 | 0.186 |
| **Logistic regression (selected)** | **0.817 ± 0.015** | **0.511** |
| **Gradient boosting** | 0.802 ± 0.011 | 0.482 |

Test set at threshold 0.20: [ROC-AUC **0.822**] [Recall **77%**] [Precision **40%**]
Expected campaign value [**+$15,900**] vs. [**−$9,020**] for contacting everyone.

The simpler model won. Gradient boosting didn't earn its extra complexity here, so the interpretable logistic regression is the one that ships.

![Graphs](../../docs/churn)

## Model card
| | |
| --- | --- |
| Intended use | Rank customers for a retention offer; a human decides on the campaign |
| Training data | 5,600 synthetic customers (seeded); no personal data |
| Top drivers | Contract type, tenure, support tickets, monthly charges |
| Limitations | Synthetic data; real churn drifts, so retrain and re-check calibration monthly |
| Fairness check | `senior_citizen` is a feature; in real use, compare error rates by group |

## Run it

```bash
make churn        # trains, evaluates, writes artifacts/churn/
pytest projects/03-churn-model -q
```

## Skills shown
scikit-learn pipelines · cross-validation · imbalanced-class metrics · model selection ·
threshold optimization · calibration · permutation importance · model cards · artifact integrity
