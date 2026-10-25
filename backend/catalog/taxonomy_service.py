from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from backend.catalog.models import Taxonomy


DEFAULT_TAXONOMIES = [
    {
        "category_prefix": "01_Development_Tools",
        "category_name": "Development Tools",
        "subcategory_name": "IDEs_and_Editors",
        "description": "IDEs, compilers, and build automation utilities."
    },
    {
        "category_prefix": "02_Productivity_and_Office",
        "category_name": "Productivity and Office",
        "subcategory_name": "Word_Processing",
        "description": "Word processors, spreadsheets, and project management software."
    },
    {
        "category_prefix": "03_System_Utilities",
        "category_name": "System Utilities",
        "subcategory_name": "Compression",
        "description": "Disk management, system monitoring, and maintenance tools."
    },
    {
        "category_prefix": "04_Drivers_and_Hardware",
        "category_name": "Drivers and Hardware",
        "subcategory_name": "Drivers",
        "description": "Device drivers and hardware configuration utilities."
    },
    {
        "category_prefix": "05_Media_and_Design",
        "category_name": "Media and Design",
        "subcategory_name": "Photo_Editing",
        "description": "Photo editing, video production, and graphic design suites."
    },
    {
        "category_prefix": "06_Security_and_Network",
        "category_name": "Security and Network",
        "subcategory_name": "Network",
        "description": "Firewalls, antivirus, and network monitoring tools."
    },
    {
        "category_prefix": "07_Scientific_and_CAD",
        "category_name": "Scientific and CAD",
        "subcategory_name": "CAD",
        "description": "Simulation software, scientific calculators, and computer-aided design."
    },
    {
        "category_prefix": "99_Unclassified_Orphan_Binaries",
        "category_name": "Unclassified Orphan Binaries",
        "subcategory_name": None,
        "description": "Software with insufficient metadata for categorization."
    }
]


class TaxonomyService:
    def __init__(self, db_session: Optional[Session] = None):
        self._default_taxonomies = DEFAULT_TAXONOMIES
        self.db_session = db_session

    def seed_default_taxonomies(self, db_session: Session) -> int:
        """Seed the database with default taxonomy categories."""
        count = 0
        for tax_data in self._default_taxonomies:
            existing = db_session.query(Taxonomy).filter(
                Taxonomy.category_prefix == tax_data["category_prefix"]
            ).first()

            if not existing:
                new_taxonomy = Taxonomy(**tax_data)
                db_session.add(new_taxonomy)
                count += 1
        db_session.commit()
        return count

    def resolve_taxonomy(
        self,
        category_name: str,
        subcategory_name: Optional[str] = None,
        db_session: Optional[Session] = None
    ) -> Taxonomy:
        """Resolve a taxonomy entry by name, returning a Taxonomy model instance."""
        session = db_session or self.db_session
        norm_cat = (category_name or "").lower().replace("_", " ")

        if session:
            try:
                all_tax = session.query(Taxonomy).all()
                # 1. Exact match
                for t in all_tax:
                    t_cat = (t.category_name or "").lower().replace("_", " ")
                    t_pref = (t.category_prefix or "").lower().replace("_", " ")
                    if norm_cat in t_cat or t_cat in norm_cat or norm_cat in t_pref or t_pref in norm_cat:
                        if subcategory_name and t.subcategory_name:
                            if subcategory_name.lower() in t.subcategory_name.lower():
                                return t
                        elif not subcategory_name:
                            return t
                
                # 2. Relaxed match
                for t in all_tax:
                    t_cat = (t.category_name or "").lower().replace("_", " ")
                    t_pref = (t.category_prefix or "").lower().replace("_", " ")
                    if norm_cat in t_cat or t_cat in norm_cat or norm_cat in t_pref or t_pref in norm_cat:
                        return t
            except Exception:
                pass

        # Check in DEFAULT_TAXONOMIES
        for tax_data in self._default_taxonomies:
            t_cat = tax_data["category_name"].lower().replace("_", " ")
            t_pref = tax_data["category_prefix"].lower().replace("_", " ")
            if norm_cat in t_cat or t_cat in norm_cat or norm_cat in t_pref or t_pref in norm_cat:
                tax = Taxonomy(
                    category_prefix=tax_data["category_prefix"],
                    category_name=tax_data["category_name"],
                    subcategory_name=subcategory_name or tax_data.get("subcategory_name"),
                    description=tax_data.get("description")
                )
                if session:
                    session.add(tax)
                    session.commit()
                return tax

        # Fallback
        prefix = "99" if ("orphan" in norm_cat or "unclassified" in norm_cat) else "00"
        fallback_tax = Taxonomy(
            category_prefix=prefix,
            category_name=category_name or "Uncategorized",
            subcategory_name=subcategory_name,
            description=f"Auto-resolved category for {category_name}"
        )
        if session:
            session.add(fallback_tax)
            session.commit()
        return fallback_tax

    def get_taxonomy_tree(self, db_session: Optional[Session] = None) -> List[Dict[str, Any]]:
        """Retrieve the full taxonomy tree structure."""
        session = db_session or self.db_session
        if session:
            try:
                taxonomies = session.query(Taxonomy).all()
                if taxonomies:
                    return [
                        {
                            "id": t.id,
                            "category_prefix": t.category_prefix,
                            "category_name": t.category_name,
                            "subcategory_name": t.subcategory_name,
                            "description": t.description
                        }
                        for t in taxonomies
                    ]
            except Exception:
                pass

        return [dict(t) for t in self._default_taxonomies]


_taxonomy_service = TaxonomyService()
