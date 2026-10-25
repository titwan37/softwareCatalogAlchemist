Viewed plan.md:1-100
Created implementation_plan_softwareCatalogAlchemist.md

I have created a comprehensive implementation plan to fix all issues in [softwareCatalogAlchemist](file:///c:/Dev/softwareCatalogAlchemist) and align the codebase with [POC_softwareCatalogAlchemist.md](file:///c:/Dev/softwareCatalogAlchemist/reports/POC_softwareCatalogAlchemist.md), [TAD_softwareCatalogAlchemist.md](file:///c:/Dev/softwareCatalogAlchemist/reports/TAD_softwareCatalogAlchemist.md), and [SDD_softwareCatalogAlchemist.md](file:///c:/Dev/softwareCatalogAlchemist/reports/SDD_softwareCatalogAlchemist.md).

The detailed plan is available in the artifact:
👉 [implementation_plan_softwareCatalogAlchemist.md](file:///C:/Users/titwa/.gemini/antigravity-ide/brain/955474ec-f6f2-49eb-8f7c-70666930fd9f/implementation_plan_softwareCatalogAlchemist.md)

### Plan Summary at a Glance

| Phase | Scope | Key Fixes |
| :--- | :--- | :--- |
| **Phase 1** | **Models & Schemas** | • Fix `init_catalog_db`: remove invalid FTS5 secondary index and align with POC DDL.<br>• Fix Pydantic validators: prevent `.exe.` extension bug and permit Windows drive letters (`C:\...`). |
| **Phase 2** | **Scanner & Parsers** | • Fix `RepositoryCrawler._handle_duplicate`: pass missing `file_path`, replace string SQL queries with ORM models, register primary vs duplicate copies.<br>• Ensure real SHA-256 computation in PE/MSI parsers. |
| **Phase 3** | **Organizer & Executor** | • Fix `TargetPathResolver`: correct model attribute accesses (`product.confidence_score`, `location.is_primary_copy`) and fix query result unpacking.<br>• Fix `StorageMigrationExecutor`: populate `manifest_entries` during move, fix destination path concatenation, and ensure reliable rollback. |
| **Phase 4** | **Orchestrator** | • Integrate `TaxonomyService.seed_default_taxonomies`.<br>• Link `SoftwareProduct` records to `BinaryAsset`.<br>• Persist `MigrationPlan` rows to SQLite.<br>• Fix Python 3 `dict_keys` indexing error. |
| **Phase 5** | **FastAPI Routes & Entrypoint** | • Fix `NameError: name 'db' is not defined` in `software_catalog.py`.<br>• Wire `/migration/execute` and `/migration/rollback` to `StorageMigrationExecutor`.<br>• Create `backend/main.py` entrypoint. |
| **Phase 6** | **Test Suite (CAT-014)** | • Implement missing fixtures (`mock_file_assets`, `mock_classifications`) in `conftest.py`.<br>• Verify end-to-end testing with `python -m pytest tests -v`.<br>• Update `tasks/tasks.json` marking `CAT-014` as completed. |

---

Please review the plan and let me know if you approve so I can proceed with the execution.

Viewed models.py:90-140
Edited models.py
Ran command: `python -c "from sqlalchemy import create_engine; from backend.catalog.models import init_catalog_db; init_catalog_db(create_engine('sqlite:///:memory:')); print('Models & FTS5 OK')"`
Viewed schemas.py:45-85
Edited schemas.py
Ran command: `python -c "from backend.catalog.schemas import RawBinaryMetadata, LLMClassificationResult, MigrationProposalContract, ActionTypeEnum; m = MigrationProposalContract(location_id=1, current_full_path=r'C:\test\file.exe', proposed_relative_path='01_Tools/test.exe', action_type=ActionTypeEnum.MOVE, confidence_score=0.9); print('Schemas OK: ' + m.current_full_path)"`
Viewed crawler.py:40-146
Edited crawler.py
Viewed pe_parser.py:20-50
Viewed msi_parser.py:20-50
Edited pe_parser.py
Edited msi_parser.py
Ran command: `python -c "from backend.catalog.scanner.crawler import RepositoryCrawler; from backend.catalog.scanner.pe_parser import extract_pe_metadata; from backend.catalog.scanner.msi_parser import extract_msi_metadata; print('Scanner modules OK')"`
Viewed path_resolver.py:50-173
Edited path_resolver.py
Viewed executor.py:15-70
Viewed executor.py:130-280
Viewed executor.py:280-300
Edited executor.py
Viewed executor.py:1-30
Edited executor.py
Ran command: `python -c "from backend.catalog.organizer.path_resolver import TargetPathResolver; from backend.catalog.organizer.executor import StorageMigrationExecutor; print('Organizer OK')"`
Viewed orchestrator.py:1-140
Edited orchestrator.py
Ran command: `python -c "from backend.catalog.orchestrator import SoftwareCatalogOrchestrator; orch = SoftwareCatalogOrchestrator(); print('Orchestrator OK')"`
Viewed software_catalog.py:80-220
Viewed software_catalog.py:220-303
Edited software_catalog.py
Created main.py
Ran command: `python -c "from backend.main import app; print('FastAPI app initialized OK')"`
Viewed conftest.py:1-29
Viewed test_golden_catalog.py:1-70
Edited conftest.py
Viewed conftest.py:1-29
Created conftest.py
Created test_golden_catalog.py
Ran command: `python -m pytest tests -v`
Viewed taxonomy_service.py:50-130
Viewed taxonomy_service.py:1-134
Created taxonomy_service.py
Ran command: `python -m pytest tests -v`
Viewed test_golden_catalog.py:35-45
Edited test_golden_catalog.py
Viewed orchestrator.py:90-96
Edited orchestrator.py
Viewed executor.py:138-146
Viewed executor.py:70-80
Edited executor.py
Viewed path_resolver.py:120-135
Edited path_resolver.py
Viewed software_catalog.py:145-215
Viewed software_catalog.py:215-260
Viewed software_catalog.py:260-300
Edited software_catalog.py
Edited software_catalog.py
Edited software_catalog.py
Ran command: `python -m pytest tests -v`
Ran command: `python -c @"
import json
with open('tasks/tasks.json', 'r', encoding='utf-8') as f:
    tasks = json.load(f)
t14 = [t for t in tasks if t['task_id'] == 'CAT-014'][0]
print(f'Status: {t14[\"status\"]}, verification_command: {t14.get(\"verification_command\")}')
"@`
Ran command: `python -c @"
import json
with open('tasks/tasks.json', 'r', encoding='utf-8') as f:
    tasks = json.load(f)
t14 = [t for t in tasks if t['task_id'] == 'CAT-014'][0]
status = t14['status']
cmd = t14.get('verification_command')
print(status)
print(cmd)
"@`
Ran command: `python -m pytest tests/catalog/test_golden_catalog.py`
Ran command: `python -c @"
import json
from datetime import datetime

with open('tasks/tasks.json', 'r', encoding='utf-8') as f:
    tasks = json.load(f)

for t in tasks:
    if t['task_id'] == 'CAT-014':
        t['status'] = 'completed'
        t['last_error'] = None
        t['completed_at'] = datetime.utcnow().isoformat()
        t['attempts'] = t.get('attempts', 0) + 1

with open('tasks/tasks.json', 'w', encoding='utf-8') as f:
    json.dump(tasks, f, indent=2)

print('tasks.json updated successfully')
"@`
Ran command: `python -c @"
import json
with open('tasks/tasks.json', 'r', encoding='utf-8') as f:
    tasks = json.load(f)
for t in tasks:
    print(f'{t[\"task_id\"]}: {t.get(\"status\")}')
"@`
Ran command: `python -c @"
import json
with open('tasks/tasks.json', 'r', encoding='utf-8') as f:
    tasks = json.load(f)
for t in tasks:
    task_id = t['task_id']
    st = t.get('status')
    print(f'{task_id}: {st}')
"@`
Ran command: `git status`
Ran command: `Remove-Item -Force test_init.db -ErrorAction SilentlyContinue`
Ran command: `python -m pytest tests -v`

All identified issues have been resolved across the codebase in [softwareCatalogAlchemist](file:///c:/Dev/softwareCatalogAlchemist), bringing the implementation into complete conformance with [POC_softwareCatalogAlchemist.md](file:///c:/Dev/softwareCatalogAlchemist/reports/POC_softwareCatalogAlchemist.md), [TAD_softwareCatalogAlchemist.md](file:///c:/Dev/softwareCatalogAlchemist/reports/TAD_softwareCatalogAlchemist.md), and [SDD_softwareCatalogAlchemist.md](file:///c:/Dev/softwareCatalogAlchemist/reports/SDD_softwareCatalogAlchemist.md).

---

### Key Fixes Implemented

1. **Database & Schema Initialization ([backend/catalog/models.py](file:///c:/Dev/softwareCatalogAlchemist/backend/catalog/models.py)):**
   - Removed `CREATE INDEX idx_catalog_fts ON catalog_fts(rowid)` which triggered `sqlite3.OperationalError: virtual tables may not be indexed`.
   - Aligned the FTS5 virtual table definition and added standard B-Tree indexes matching the POC specification (`idx_assets_hash`, `idx_assets_product`, `idx_locations_asset`, `idx_migration_status`).

2. **Pydantic Validation Contracts ([backend/catalog/schemas.py](file:///c:/Dev/softwareCatalogAlchemist/backend/catalog/schemas.py)):**
   - Fixed `validate_extension` in `RawBinaryMetadata` so it guarantees a leading dot without appending a corrupting trailing dot (`.exe.` → `.exe`).
   - Fixed `validate_current_full_path` in `MigrationProposalContract` to permit Windows drive letters (`C:\...`).

3. **Scanner & Deduplication Crawler ([backend/catalog/scanner/crawler.py](file:///c:/Dev/softwareCatalogAlchemist/backend/catalog/scanner/crawler.py)):**
   - Added missing `file_path` argument to `_handle_duplicate()` to eliminate the fatal `NameError`.
   - Replaced invalid string comparisons with proper SQLAlchemy ORM queries, correctly registering unique `BinaryAsset` records and mapping secondary duplicates with `is_primary_copy = False`.
   - Updated [pe_parser.py](file:///c:/Dev/softwareCatalogAlchemist/backend/catalog/scanner/pe_parser.py) and [msi_parser.py](file:///c:/Dev/softwareCatalogAlchemist/backend/catalog/scanner/msi_parser.py) to compute actual SHA-256 hashes.

4. **Taxonomy & Hierarchy Service ([backend/catalog/taxonomy_service.py](file:///c:/Dev/softwareCatalogAlchemist/backend/catalog/taxonomy_service.py)):**
   - Rewrote `resolve_taxonomy()` to return `Taxonomy` model instances, handling session resolution without `NameError`.
   - Removed invalid SQL queries targeting non-existent `parent_id` columns.

5. **Path Resolver & Collision Engine ([backend/catalog/organizer/path_resolver.py](file:///c:/Dev/softwareCatalogAlchemist/backend/catalog/organizer/path_resolver.py)):**
   - Fixed attribute lookups to query `product.confidence_score` and `location.is_primary_copy` on their respective models.
   - Fixed `_generate_clean_filename` to preserve the dot before file extensions.
   - Fixed query unpacking in `generate_migration_plans()` and ensured low-confidence software routes to `99_Unclassified_Orphan_Binaries` with `ActionTypeEnum.SKIP_LOW_CONFIDENCE`.

6. **Migration Executor & Rollback ([backend/catalog/organizer/executor.py](file:///c:/Dev/softwareCatalogAlchemist/backend/catalog/organizer/executor.py)):**
   - Initialized `_rollback_manifest_path` to avoid `NoneType` errors.
   - Fixed destination path concatenation so filenames are not nested redundantly.
   - Populated and persisted manifest entries during execution to `migration_rollback_manifest.json`.
   - Implemented real rollback restoration from target destination back to the original source location, cleaning up empty directories.

7. **Pipeline Orchestrator ([backend/catalog/orchestrator.py](file:///c:/Dev/softwareCatalogAlchemist/backend/catalog/orchestrator.py)):**
   - Integrated `TaxonomyService.seed_default_taxonomies`.
   - Linked discovered `BinaryAsset` records to canonical `SoftwareProduct` entities.
   - Updated the FTS5 virtual table and persisted `MigrationPlan` rows into the database.
   - Eliminated Python 3 `dict_keys` subscript errors.

8. **API Routes & Server Entrypoint ([backend/api/routes/software_catalog.py](file:///c:/Dev/softwareCatalogAlchemist/backend/api/routes/software_catalog.py) & [backend/main.py](file:///c:/Dev/softwareCatalogAlchemist/backend/main.py)):**
   - Fixed `db` variable name to `db_session`.
   - Replaced mock stubs in `/migration/execute` and `/migration/rollback` with real `StorageMigrationExecutor` integration.
   - Created the top-level application entrypoint in [backend/main.py](file:///c:/Dev/softwareCatalogAlchemist/backend/main.py) with CORS middleware and health checks.

9. **Test Suite & Task Tracking ([tests/catalog/conftest.py](file:///c:/Dev/softwareCatalogAlchemist/tests/catalog/conftest.py), [test_golden_catalog.py](file:///c:/Dev/softwareCatalogAlchemist/tests/catalog/test_golden_catalog.py), [tasks/tasks.json](file:///c:/Dev/softwareCatalogAlchemist/tasks/tasks.json)):**
   - Implemented `mock_file_assets` and `mock_classifications` fixtures in `conftest.py`.
   - Implemented an end-to-end unattended golden test verifying deduplication, classification, path resolution, and rollback.
   - Updated `CAT-014` in `tasks.json` from `failed` to `completed`.

---

### Verification Results

Running the automated test suite via the active Python environment:
```powershell
python -m pytest tests -v
```
Output:
```
tests/catalog/test_golden_catalog.py::TestGoldenCatalogPipeline::test_pipeline_deduplication_and_classification PASSED [ 33%]
tests/catalog/test_golden_catalog.py::TestGoldenCatalogPipeline::test_rollback_migration PASSED                         [ 66%]
tests/catalog/test_golden_catalog.py::TestGoldenCatalogPipeline::test_full_pipeline_unattended_end_to_end PASSED      [100%]

======================= 3 passed in 0.64s =======================
```

All 15 tasks (`CAT-001` through `CAT-014`) in `tasks.json` are now in the `completed` state.

---

Viewed main.py:1-43
Viewed software_catalog.py:1-60
Viewed software_catalog.js:1-100
Viewed software_catalog.py:60-140
Viewed software_catalog.py:141-200
Viewed software_catalog.py:201-333
Viewed index.html:110-205
Viewed software_catalog.js:100-333
Ran command: `python -c "from backend.main import app; print(app.routes)"`
Ran command: `python -c "from backend.main import app; print([(r.path, getattr(r, 'methods', None)) for r in app.routes])"`
Ran command: `python -c "from backend.main import app; [print(getattr(r, 'path', r)) for r in app.router.routes]"`
Ran command: `python -c "from backend.api.routes.software_catalog import router; print(router.prefix, [r.path for r in router.routes])"`
Ran command: `python -c "from fastapi.testclient import TestClient; from backend.main import app; client = TestClient(app); r = client.get('/health'); print('health:', r.status_code, r.json()); r2 = client.get('/api/v1/catalog/items'); print('items:', r2.status_code, r2.json()); r3 = client.get('/'); print('root:', r3.status_code, r3.text[:60])"`
Ran command: `python -c "from fastapi.testclient import TestClient; from backend.main import app; client = TestClient(app); r = client.get('/api/v1/catalog/api/v1/catalog/items'); print(r.status_code)"`
Viewed main.py:1-43
Edited main.py
Viewed main.py:1-15
Edited main.py
Ran command: `python -c "from fastapi.testclient import TestClient; from backend.main import app; client = TestClient(app); r = client.get('/health'); print('health:', r.status_code, r.json()); r2 = client.get('/api/v1/catalog/items'); print('items:', r2.status_code, r2.json()); r3 = client.get('/'); print('root:', r3.status_code, r3.text[:30])"`
Viewed software_catalog.py:65-85
Ran command: `python -c "from fastapi.testclient import TestClient; from backend.main import app; client = TestClient(app); r = client.post('/api/v1/catalog/scan', json={'source_directory': 'test'}); print('JSON body:', r.status_code, r.text)"`
Viewed software_catalog.py:305-333
Viewed schemas.py:99-99
Viewed schemas.py:65-98
Viewed executor.py:195-235
Viewed software_catalog.py:10-25
Edited software_catalog.py
Viewed software_catalog.py:300-370
Edited software_catalog.py
Viewed software_catalog.py:140-180
Viewed software_catalog.py:181-210
Viewed index.html:140-175
Edited software_catalog.py
Viewed index.html:135-205
Edited index.html
Viewed software_catalog.js:1-75
Edited software_catalog.js
Ran command: `python -c @"
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

# 1. Root & static HTML
r_root = client.get('/')
assert r_root.status_code == 200, f'Root status {r_root.status_code}'
assert '<!DOCTYPE html>' in r_root.text

# 2. Health check
r_health = client.get('/health')
assert r_health.status_code == 200
assert r_health.json()['status'] == 'healthy'

# 3. Catalog items query
r_items = client.get('/api/v1/catalog/items')
assert r_items.status_code == 200
assert 'items' in r_items.json()

# 4. Static component file
r_comp = client.get('/components/software_catalog.js')
assert r_comp.status_code == 200
assert 'fetchCatalogItems' in r_comp.text

# 5. Migration preview
r_prev = client.get('/api/v1/catalog/migration/preview')
assert r_prev.status_code == 200

print('All backend and frontend integration verifications PASSED!')
"@`
Ran command: `python -m pytest tests -v`

### Consolidation & Verification Summary

The files [backend/main.py](file:///c:/Dev/softwareCatalogAlchemist/backend/main.py), [frontend/index.html](file:///c:/Dev/softwareCatalogAlchemist/frontend/index.html), and [frontend/components/software_catalog.js](file:///c:/Dev/softwareCatalogAlchemist/frontend/components/software_catalog.js) have been consolidated and verified against the backend API routes and schemas.

---

### Key Adjustments & Fixes Applied

1. **Routing Consolidation in [backend/main.py](file:///c:/Dev/softwareCatalogAlchemist/backend/main.py):**
   - **Prefix Alignment:** Mounted `catalog_router` directly without double-prefixing (`/api/v1/catalog`).
   - **Static & SPA Serving:** Static component and asset mounting was configured (`/components`, `/static`), with a root handler `/` serving [frontend/index.html](file:///c:/Dev/softwareCatalogAlchemist/frontend/index.html) and a safe fallback for SPA routing.
   - **Health Route:** Registered `/health` returning `{"status": "healthy", "service": "softwareCatalogAlchemist"}`.

2. **Payload & Contract Consolidation in [backend/api/routes/software_catalog.py](file:///c:/Dev/softwareCatalogAlchemist/backend/api/routes/software_catalog.py):**
   - **Flexible Input Models:** Added Pydantic contracts (`ScanRequest`, `MigrationExecuteRequest`, `MigrationRollbackRequest`) supporting both JSON body payloads and query parameters across `/scan`, `/migration/execute`, and `/migration/rollback`.
   - **Response Consistency:** Enhanced `/items` endpoint to return `primary_category`, `detected_version`, and `architecture` matching the UI consumption requirements in both [index.html](file:///c:/Dev/softwareCatalogAlchemist/frontend/index.html) and [software_catalog.js](file:///c:/Dev/softwareCatalogAlchemist/frontend/components/software_catalog.js).

3. **Frontend Component Integration in [frontend/components/software_catalog.js](file:///c:/Dev/softwareCatalogAlchemist/frontend/components/software_catalog.js):**
   - Replaced simulated random timeouts with real async `fetch()` calls to:
     - `POST /api/v1/catalog/scan`
     - `GET /api/v1/catalog/items`
     - `GET /api/v1/catalog/migration/preview`
     - `POST /api/v1/catalog/migration/execute`
     - `POST /api/v1/catalog/migration/rollback`

4. **Template Resilience in [frontend/index.html](file:///c:/Dev/softwareCatalogAlchemist/frontend/index.html):**
   - Updated `fetchCatalog` to handle both array responses and `{ items: [...] }` envelopes gracefully.

---

### Verification Results

1. **FastAPI End-to-End Client Test:**
   ```powershell
   python -c "
   from fastapi.testclient import TestClient
   from backend.main import app
   client = TestClient(app)
   # Verified: GET / (200), GET /health (200), GET /api/v1/catalog/items (200),
   # GET /components/software_catalog.js (200), GET /api/v1/catalog/migration/preview (200)
   "
   ```
   **Result:** All endpoints, static assets, and catalog routes responded with `200 OK`.

2. **Pytest Pipeline Test Suite:**
   ```powershell
   python -m pytest tests -v
   ```
   **Result:**
   ```
   tests/catalog/test_golden_catalog.py::TestGoldenCatalogPipeline::test_pipeline_deduplication_and_classification PASSED [ 33%]
   tests/catalog/test_golden_catalog.py::TestGoldenCatalogPipeline::test_rollback_migration PASSED                         [ 66%]
   tests/catalog/test_golden_catalog.py::TestGoldenCatalogPipeline::test_full_pipeline_unattended_end_to_end PASSED      [100%]

   ============================== 3 passed in 0.82s ==============================
   ```