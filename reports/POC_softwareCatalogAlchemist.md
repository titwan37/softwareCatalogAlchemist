
Here is a comprehensive use case and functional architecture for your software. Let's call the project working title **"RepoInspector"** or **"SoftwareCataloguer"**.

This tool directly addresses the classic IT storage headache: an unstructured archive of legacy installer binaries (`.msi`, `.exe`) buried deep inside an organic, messy directory tree. By combining local file parsing, metadata extraction, web intelligence, and LLM reasoning, your software will transform chaotic storage into a clean, categorized, and logically organized repository.

---

## 1. Project Overview & Objectives

* **Problem Statement:** A large, disorganized software repository containing `.msi` and `.exe` files spread across an irrational subfolder tree makes discovery, auditing, and maintenance extremely difficult.
* **Core Objective:** Automatically scan, analyze, categorize, and propose/execute a logical folder restructuring for all executable and installer binaries.
* **Target Output:**
1. A searchable, interactive software catalog (database/web interface).
2. An automated categorization mapping (e.g., Development Tools, Productivity, Drivers, Utilities, Media).
3. A dry-run preview of an optimized, logical directory tree with automated file relocation capabilities.



---

## 2. Key Features & Functional Workflow

### Phase 1: Deep Recursive Discovery & Local Metadata Extraction

* **Recursive Crawler:** Traverse the messy subfolder tree targeting `.msi`, `.exe`, `.msp`, and potentially compressed archives (`.zip`, `.7z`, `.iso`) if installers are bundled.
* **File & Metadata Harvesting:**
* Extract file hashes (SHA-256) for deduplication and version tracking.
* Extract PE headers (Windows Portable Executable metadata): Product Name, Company Name, File Version, Original Filename, and Copyright notices.
* Extract MSI internal summary information streams (ProductCode, Manufacturer, Subject).



### Phase 2: Intelligent Analysis & Classification (LLM + Web Enrichment)

* **Heuristic & Identifier Matching:** Look up known product names or vendor strings against a local whitelist/cache.
* **Targeted Web Query / LLM Inference:** For unknown or ambiguous binaries, send the extracted metadata (Filename, Company, Version, File Description) to an LLM pipeline with a lightweight web-search tool or internal knowledge base to answer:
* *What does this software actually do?*
* *Who is the target audience or primary use case?*


* **Automated Taxonomy Assignment:** Categorize each software into a standardized, hierarchical taxonomy (e.g., `Category > Subcategory > Vendor > Product > Version`).

### Phase 3: Cataloging & Search Interface

* **Local Database Storage:** Store scanned assets, metadata, tags, confidence scores, and current vs. proposed paths in a lightweight, high-performance database (e.g., SQLite with WAL).
* **Dashboard / Explorer:** A clean web or desktop UI to review the discovered inventory, inspect categorization confidence, manually override tags if necessary, and view search analytics.

### Phase 4: Logical Restructuring & Reorganization Engine

* **Target Schema Definition:** Define a clean, standardized template for the new repository structure. For example:

$$\text{Target Root} / \text{[Category]} / \text{[Vendor]} / \text{[Product Name]} / \text{[Version]}$$


* **Simulation & Dry-Run:** Generate a before-and-after tree diff to let you inspect moves, rename actions, and identify duplicate files or older obsolete versions.
* **Execution Mode:** Perform safe file operations (Move or Copy), updating symbolic links or generating a redirection mapping file (`manifest.json` or CSV) to ensure existing scripts or references don't break.

---

## 3. Recommended Technology Stack

Depending on your preferred development ecosystem, here is a robust stack to build this:

* **Backend Core & File Scanner:** **Rust** (leveraging `tokio` for async I_O, `walkdir`, and binary parsing crates) or **Python** (`pathlib`, `pefile`, `sqlite3`). Given your background in high-performance Rust tools (like *BildBlitz* or *RepoScroller*), a Rust core with a FastMCP or FastAPI wrapper would make this blazing fast.
* **Metadata & Parsing:** Native Windows API wrappers or cross-platform PE parsers to extract file properties without executing the binaries (protecting safety and performance).
* **LLM & Intelligence Pipeline:** Local or API-based LLMs integrated via structured JSON output schemas (Pydantic / Instructor) to guarantee clean, parseable categorization tags.
* **Frontend UI:** **Next.js** / **React** with Tailwind CSS and ShadCN UI, or an egui-based desktop GUI if you prefer a native standalone utility.

---

## 4. Proposed Logical Folder Structure Template

When the tool runs its restructuring phase, it could organize your chaotic archive into something clean like this:

```text
📦 Clean_Software_Repository/
├── 📂 01_Development_Tools/
│   ├── 📂 Compilers_and_SDKs/
│   │   ├── 📂 Microsoft/
│   │   │   └── Visual_Studio_Code/
│   │   │       └── 1.85.1/
│   │   │           └── VSCodeSetup-x64-1.85.1.exe
│   └── 📂 Database_Clients/
├── 📂 02_Productivity_and_Office/
├── 📂 03_System_Utilities/
│   ├── 📂 Disk_and_Partition/
│   ├── 📂 Compression/
│   │   └── 📂 7-Zip/
│   │       └── 23.01/
│   │           └── 7z2301-x64.msi
├── 📂 04_Drivers_and_Hardware/
└── 📂 99_Unclassified_Orphan_Binaries/

```

---

Would you like to dive deeper into designing the scanning pipeline architecture, or shall we outline the data schema for the software catalog database?

The architectural blueprint below separates high-speed, local binary ingestion from asynchronous AI enrichment, backed by a normalized SQLite data schema designed for deduplication, taxonomy mapping, and safe file relocation.

---

## 1. Scanning & Enrichment Pipeline Architecture

Because disk I/O and static binary parsing happen in milliseconds while web queries and LLM inference take seconds, the pipeline must decouple **local extraction** from **semantic enrichment** using an asynchronous producer-consumer model (e.g., `tokio` channels or Crossbeam queues).

```text
[ Messy Storage ] 
       │
       ▼ (Stage 1: Parallel Directory Walk)
[ File Paths Stream ] 
       │
       ▼ (Stage 2: Fast Hash & Deduplication Check)
[ Unique Binary Queue ] ──(Duplicate)──► [ Link to Existing Asset ID ]
       │
       ▼ (Stage 3: Static PE / MSI / Authenticode Parser)
[ Normalized Metadata ]
       │
       ├──(High Confidence Cache Hit)──────────┐
       ▼                                       ▼
[ Stage 4: Web Search + LLM Agent ]     [ SQLite WAL DB ]
       │                                       ▲
       └────────(Structured Taxonomy)──────────┘
                                               │
                                               ▼ (Stage 5: Path Resolver)
                                        [ Migration Plan / Dry-Run ]

```

### Stage 1: Asynchronous File Crawler (Producer)

* **Mechanism:** Uses a non-blocking directory walker (`ignore` or `walkdir` in Rust) to traverse the chaotic folder tree.
* **Contextual Breadcrumbs:** Before moving on, the crawler captures the **parent folder names** (e.g., `.../Old_Server_Backup/Compta_Tools/setup.exe`). When an installer is named generically (`setup.exe` or `install.msi`), those parent folder names are often the only clue to what the software actually is.

### Stage 2: Cryptographic Hashing & Deduplication

* **Mechanism:** Computes a fast cryptographic hash (**BLAKE3** or **SHA-256**) using memory-mapped files (`memmap2`) to avoid loading multi-gigabyte ISOs or installers into RAM.
* **Deduplication Gate:** Checks the hash against the database. If the exact binary was already found in three other subfolders, it skips parsing and LLM querying, logging the file solely as a duplicate location reference.

### Stage 3: Static Binary Inspection (Zero-Execution)

To maintain strict security and speed, binaries are inspected statically without ever running them:

* **For `.exe` (Portable Executable):** Parses the `.rsrc` (Resource) section using a PE parser (`pelite` or `goblin` in Rust, `pefile` in Python) to extract the `VS_VERSIONINFO` structure:
* `CompanyName`, `ProductName`, `FileDescription`, `FileVersion`, `OriginalFilename`, `InternalName`.
* Extracts the **Authenticode Digital Signature** (Publisher certificate subject) — often more reliable than the `CompanyName` string, which developers frequently leave blank.
* Checks the PE header machine type (`0x8664` for x64, `0x014c` for x86, `0xAA64` for ARM64).


* **For `.msi` (Windows Installer):** Reads the OLE Compound Document format (`cfb` crate or `msilib`) to query the internal `Property` table directly via SQL-like semantics for `Manufacturer`, `ProductName`, `ProductVersion`, `ProductCode` (GUID), and `UpgradeCode`.

### Stage 4: Tiered Intelligence & LLM Classification

To avoid burning API tokens or time on hundreds of recognizable installers, enrichment operates in three tiers:

1. **Tier 1 — Local Fingerprint Cache:** Matches extracted `Manufacturer` + `ProductName` against already classified software in your local SQLite database.
2. **Tier 2 — Package Manager Lookup (Fast & Free):** Queries public software manifests (such as the **Windows Package Manager / Winget** community repository or Chocolatey API) using the `ProductName` or `ProductCode`. If a match is found, you immediately get verified publisher, tags, and license data.
3. **Tier 3 — Search-Grounded LLM Agent:** Triggered when metadata is sparse (e.g., `setup_v2.exe` with no PE version info) or unrecognized.
* **Input Payload:** Filename, Parent Directory Path, PE strings, Cert Signer, File Size.
* **Web Grounding:** Executes a lightweight query (e.g., DuckDuckGo/Tavily/Brave Search API) for `"<OriginalFilename>" "<CompanyName>" software`.
* **Structured Output Enforcement:** The LLM is constrained via JSON Schema to return a deterministic classification object:



```json
{
  "canonical_vendor": "VideoLAN",
  "canonical_product": "VLC Media Player",
  "detected_version": "3.0.20",
  "architecture": "x64",
  "primary_category": "05_Media_and_Design",
  "subcategory": "Video_Players",
  "license_model": "Open Source (GPLv2)",
  "summary": "Cross-platform multimedia player and framework that plays most multimedia files.",
  "confidence_score": 0.98,
  "reasoning": "Matched PE OriginalFilename 'vlc-3.0.20-win64.exe' and signer 'VideoLAN'."
}

```

### Stage 5: Target Path Resolver & Conflict Engine

* **Path Generation:** Applies your naming template (e.g., `{Category}/{Subcategory}/{Vendor}/{Product}/{Version}/{CleanFilename}`).
* **Sanitization:** Strips illegal file system characters (`:`, `/`, `\`, `*`, `?`, `"`) and normalizes whitespace.
* **Collision & Redundancy Detection:** Flags cases where multiple identical hashes exist across the old tree (proposing `DELETE_DUPLICATE` for redundant copies and `MOVE` for the primary copy).

---

## 2. Software Catalog Database Schema (SQLite WAL)

Using SQLite in **WAL (Write-Ahead Logging)** mode with **FTS5 (Full-Text Search)** provides single-file portability, concurrent read/write performance during scanning, and instant search across your catalog.

### Entity-Relationship Overview

```text
┌──────────────────────┐       ┌──────────────────────┐       ┌──────────────────────┐
│      taxonomies      │       │   software_products  │       │    binary_assets     │
├──────────────────────┤       ├──────────────────────┤       ├──────────────────────┤
│ id (PK)              │◄──────┤ taxonomy_id (FK)     │◄──────┤ product_id (FK)      │
│ category_code        │       │ id (PK)              │       │ id (PK)              │
│ category_name        │       │ canonical_vendor     │       │ sha256_hash (UNIQUE) │
│ subcategory_name     │       │ canonical_name       │       │ file_type (EXE/MSI)  │
│ folder_slug          │       │ description          │       │ detected_version     │
└──────────────────────┘       │ license_type         │       │ architecture         │
                               │ llm_confidence       │       │ raw_pe_metadata (JSON│
                               └──────────────────────┘       └──────────┬───────────┘
                                                                         │
                               ┌──────────────────────┐                  │
                               │   migration_plans    │                  │
                               ├──────────────────────┤                  ▼
                               │ id (PK)              │       ┌──────────────────────┐
                               │ location_id (FK)     │◄──────┤    file_locations    │
                               │ proposed_path        │       ├──────────────────────┤
                               │ action_type          │       │ id (PK)              │
                               │ execution_status     │       │ asset_id (FK)        │
                               └──────────────────────┘       │ current_full_path    │
                                                              │ parent_context_hint  │
                                                              └──────────────────────┘

```

### SQL DDL Schema Definition

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- 1. Standardized Category Tree
CREATE TABLE taxonomies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_prefix TEXT NOT NULL,          -- e.g., "01", "02"
    category_name TEXT NOT NULL,            -- e.g., "Development_Tools"
    subcategory_name TEXT NOT NULL,         -- e.g., "IDEs_and_Editors"
    description TEXT,
    UNIQUE(category_name, subcategory_name)
);

-- 2. Enriched Software Product Catalog (The "What is it?" table)
CREATE TABLE software_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_vendor TEXT NOT NULL,         -- Normalized vendor (e.g., "Microsoft")
    canonical_name TEXT NOT NULL,           -- Normalized name (e.g., "Visual Studio Code")
    taxonomy_id INTEGER REFERENCES taxonomies(id),
    summary_description TEXT,               -- LLM-generated usage summary
    official_website TEXT,
    license_model TEXT,                     -- "Commercial", "FOSS", "Freeware", "Trial"
    enrichment_source TEXT NOT NULL,        -- 'LOCAL_RULE', 'WINGET', 'LLM_WEB'
    confidence_score REAL DEFAULT 0.0,      -- 0.0 to 1.0 (flags < 0.7 for human review)
    is_human_verified INTEGER DEFAULT 0,    -- Boolean: locked by user in UI
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(canonical_vendor, canonical_name)
);

-- 3. Unique Binary Assets (Deduplicated by Hash)
CREATE TABLE binary_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER REFERENCES software_products(id),
    sha256_hash TEXT NOT NULL UNIQUE,       -- Primary deduplication key
    file_size_bytes INTEGER NOT NULL,
    file_extension TEXT NOT NULL,           -- 'exe', 'msi', 'msp'
    detected_version TEXT,                  -- Normalized semver or build string
    architecture TEXT DEFAULT 'Unknown',    -- 'x86', 'x64', 'ARM64', 'Universal'
    pe_company_name TEXT,                   -- Raw extracted PE/MSI Manufacturer
    pe_product_name TEXT,                   -- Raw extracted PE/MSI ProductName
    pe_file_description TEXT,               -- Raw extracted PE FileDescription
    pe_original_filename TEXT,              -- Raw extracted OriginalFilename
    msi_product_code TEXT,                  -- MSI GUID if applicable
    digital_signature_subject TEXT,         -- Authenticode cert subject
    raw_metadata_json TEXT,                 -- Full dump of all headers for debugging
    first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 4. Physical File Instances (Tracks where files currently sit in the messy tree)
CREATE TABLE file_locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL REFERENCES binary_assets(id) ON DELETE CASCADE,
    current_full_path TEXT NOT NULL UNIQUE,
    current_filename TEXT NOT NULL,
    parent_folder_chain TEXT,               -- e.g., "Old_NAS/IT_Tools/Network" (used for LLM context)
    file_modified_at DATETIME,
    is_primary_copy INTEGER DEFAULT 0       -- 1 = Keep & Move; 0 = Redundant copy
);

-- 5. Reorganization & Dry-Run State Machine
CREATE TABLE migration_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL UNIQUE REFERENCES file_locations(id) ON DELETE CASCADE,
    proposed_relative_path TEXT NOT NULL,   -- e.g., "01_Development_Tools/IDEs/Microsoft/VSCode/1.85.1/VSCodeSetup.exe"
    action_type TEXT NOT NULL,              -- 'MOVE', 'COPY', 'DELETE_DUPLICATE', 'SKIP_LOW_CONFIDENCE'
    status TEXT DEFAULT 'PENDING',          -- 'PENDING', 'APPROVED', 'EXECUTED', 'FAILED', 'ROLLED_BACK'
    error_message TEXT,
    executed_at DATETIME
);

-- 6. Full-Text Search Index for Instant UI Cataloging
CREATE VIRTUAL TABLE catalog_fts USING fts5(
    canonical_vendor,
    canonical_name,
    summary_description,
    pe_original_filename,
    content='software_products',
    content_rowid='id'
);

-- Indexes for fast pipeline lookups
CREATE INDEX idx_assets_hash ON binary_assets(sha256_hash);
CREATE INDEX idx_assets_product ON binary_assets(product_id);
CREATE INDEX idx_locations_asset ON file_locations(asset_id);
CREATE INDEX idx_migration_status ON migration_plans(status);

```

### Why This Schema Works Well for Your Use Case

1. **Strict Separation of Binary vs. Physical Location (`binary_assets` vs. `file_locations`):** In messy repositories, the exact same installer is often copied across 5 different project folders. By separating the hash-based `binary_assets` from `file_locations`, you only run the PE parser and LLM **once** per unique binary, and the `migration_plans` table can automatically propose moving one copy (`is_primary_copy = 1`) and archiving or deleting the other four duplicates.
2. **Human-in-the-Loop Confidence Gate (`confidence_score` & `is_human_verified`):** If an EXE is named `update.exe` inside a folder called `Temp` with zero PE metadata, the LLM will return a low `confidence_score` (e.g., `0.25`). The migration engine can automatically route any asset with a score below `0.70` into `99_Manual_Review_Required/` while preserving its original subfolder context.
3. **Auditability & Rollback (`migration_plans`):** Because `current_full_path` and `proposed_relative_path` are stored side-by-side with an execution status, you can execute a dry-run, export a script, or even add a "Rollback" command that reverses every `EXECUTED` move back to its original path if needed.