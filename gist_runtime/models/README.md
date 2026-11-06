# Model artifacts

The API expects the fast GIST artifacts under `gist_runtime/models/`:

- `t1_locked_layers.joblib`
- `t1_input_contract.json`
- `t1_experts/ebm_ga2m_interpretable.joblib`
- `t1_experts/xgboost_hist_balanced.joblib`
- `t2_locked_layers.joblib`
- `input_contract.json`
- `t2_feature_dictionary.csv`
- `experts/ebm_ga2m_interpretable.joblib`
- `experts/random_forest_balanced.joblib`

They are bundled in the `accord-sl-api-0.1.0.zip` release asset and in the private Hugging Face model repository. Do not commit model binaries to this repository.
