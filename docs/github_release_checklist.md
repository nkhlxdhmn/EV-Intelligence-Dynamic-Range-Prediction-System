# GitHub Release Checklist

Before publishing this repository publicly, verify each item. Nothing here
should be committed until every box is checked.

## Repository content

- [ ] `README.md` present and professional (14 required sections, see README)
- [ ] `docs/architecture.md` present (Mermaid diagram + strict onboard alternative)
- [ ] `docs/model_card.md` present (includes safety-critical disclaimer)
- [ ] API documentation present (`docs/api_usage.md`)
- [ ] Dashboard present and functional (`frontend/`, served at `/dashboard/`)
- [ ] Tests present and passing (`pytest -q` → 138 passed)
- [ ] Docker present (`Dockerfile`, `docker-compose.yml`)
- [ ] `requirements.inference.txt` (runtime) and `requirements.txt` (dev/test)
- [ ] `pytest.ini` present
- [ ] `.gitignore` present and effective

## Secrets & credentials

- [ ] No `.env` files committed
- [ ] No API keys committed
- [ ] No personal credentials committed
- [ ] No private URLs / connection strings committed
- [ ] No hardcoded secrets (verified by `reports/step13_security_audit.json`)

## Data & artifacts

- [ ] No unnecessary datasets committed
- [ ] No large raw datasets committed — TUM dataset is git-ignored
      (`dataset/electric-vehicle-uds-dataset-main/`)
- [ ] DEVRT dataset kept only if licensing permits; otherwise document
      download instructions
- [ ] Frozen model artifacts committed deliberately
      (`models/ev_energy_extratrees_route_aware.joblib`,
      `models/final_preprocessor.joblib`, `models/final_feature_list.json`)
      or documented as downloadable
- [ ] Experiment models under `models/step8/` git-ignored

## Cleanliness

- [ ] No temporary files (`data/tmp_check/` removed)
- [ ] No debug logs committed (`logs/` git-ignored)
- [ ] No duplicate/obsolete root scripts (removed in STEP 13A)
- [ ] No `__pycache__/`, `.pytest_cache/` committed (git-ignored)
- [ ] No stale generated copies under `src/reports/` (removed)

## Final verification commands

```bash
# security scan (manual, prints only found/not-found)
# see reports/step13_security_audit.json

# tests
pytest -q

# model integrity
sha256sum models/ev_energy_extratrees_route_aware.joblib \
         models/final_preprocessor.joblib \
         models/final_feature_list.json   # matches step13_model_integrity.json

# API smoke test
uvicorn api.main:app --host 0.0.0.0 --port 8000
curl http://localhost:8000/health
curl http://localhost:8000/model/info
```

## Release notes drafting (honesty rules)

- State that TUM external validation was **blocked** (30/102 features
  reproducible) — do not imply cross-dataset validation.
- State metrics are DEVRT-only, not universal EV accuracy.
- State DEMO mode is a simulator; no live CAN/OBD integration exists.
- State the route-aware dependency (route/DEM required for best accuracy).
- Include the safety disclaimer: "estimation tool, not a safety-critical
  vehicle control system."