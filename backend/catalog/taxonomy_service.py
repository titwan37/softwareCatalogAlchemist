from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.catalog.models import Taxonomy


DEFAULT_TAXONOMIES = [
    {
        "category_prefix": "01_Development_Tools",
        "category_name": "Development Tools",
        "subcategory_name": None,
        "description": "IDEs, compilers, and build automation utilities."
    },
    {
        "category_prefix": "02_Productivity_and_Office",
        "category_name": "Productivity and Office",
        "subcategory_name": None,
        "description": "Word processors, spreadsheets, and project management software."
    },
    {
        "category_prefix": "03_System_Utilities",
        "category_name": "System Utilities",
        "subcategory_name": None,
        "description": "Disk management, system monitoring, and maintenance tools."
    },
    {
        "category_prefix": "04_Drivers_and_Hardware",
        "category_name": "Drivers and Hardware",
        "subcategory_name": None,
        "description": "Device drivers and hardware configuration utilities."
    },
    {
        "category_prefix": "05_Media_and_Design",
        "category_name": "Media and Design",
        "subcategory_name": None,
        "description": "Photo editing, video production, and graphic design suites."
    },
    {
        "category_prefix": "06_Security_and_Network",
        "category_name": "Security and Network",
        "subcategory_name": None,
        "description": "Firewalls, antivirus, and network monitoring tools."
    },
    {
        "category_prefix": "07_Scientific_and_CAD",
        "category_name": "Scientific and CAD",
        "subcategory_name": None,
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
    def __init__(self):
        self._default_taxonomies = DEFAULT_TAXONOMIES

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

    def resolve_taxonomy(self, category_name: str, subcategory_name: Optional[str] = None) -> Dict[str, Any]:
        """Resolve a taxonomy entry by name."""
        query = text("""
            SELECT 
                t.category_prefix,
                t.category_name,
                COALESCE(s.subcategory_name, NULL) as subcategory_name,
                COALESCE(t.description, '') as description
            FROM taxonomies t
            LEFT JOIN taxonomies s ON t.id = s.parent_id
            WHERE t.category_name = :category_name
        """)

        result = db_session.execute(query, {"category_name": category_name}).fetchone()
        if not result:
            raise ValueError(f"Category '{category_name}' not found in taxonomy.")

        return {
            "category_prefix": result.category_prefix,
            "category_name": result.category_name,
            "subcategory_name": result.subcategory_name,
            "description": result.description
        }

    def get_taxonomy_tree(self) -> List[Dict[str, Any]]:
        """Retrieve the full taxonomy tree structure."""
        query = text("""
            SELECT 
                t.id,
                t.category_prefix,
                t.category_name,
                COALESCE(s.subcategory_name, NULL) as subcategory_name,
                t.description
            FROM taxonomies t
            LEFT JOIN taxonomies s ON t.id = s.parent_id
            ORDER BY t.category_prefix, t.category_name
        """)

        results = db_session.execute(query).fetchall()
        tree = []
        for row in results:
            entry = {
                "id": row.id,
                "category_prefix": row.category_prefix,
                "category_name": row.category_name,
                "subcategory_name": row.subcategory_name,
                "description": row.description
            }
            tree.append(entry)

        return tree


# Global instance for easy access
_taxonomy_service = TaxonomyService()
