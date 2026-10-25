from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from backend.catalog.models import Taxonomy
import json

from pathlib import Path

def load_taxonomies_from_file() -> list[dict[str, Any]]:
    tax_path = Path(__file__).parent / "taxonomy.json"
    with open(tax_path, "r", encoding="utf-8") as f:
        return json.load(f)

class TaxonomyService:
    def __init__(self, db_session: Optional[Session] = None):
        self._default_taxonomies = load_taxonomies_from_file()
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

        # 1. Exact match on prefix / name
        for tax_data in self._default_taxonomies:
            t_cat = tax_data["category_name"].lower().replace("_", " ")
            t_pref = tax_data["category_prefix"].lower().replace("_", " ")
            if norm_cat == t_cat or norm_cat == t_pref:
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

        # 2. Check substring match in DEFAULT_TAXONOMIES, but if category_name is already a clean category (e.g. "Web")
        # and doesn't match an explicit taxonomy prefix, allow direct clean category
        for tax_data in self._default_taxonomies:
            t_cat = tax_data["category_name"].lower().replace("_", " ")
            t_pref = tax_data["category_prefix"].lower().replace("_", " ")
            t_sub = (tax_data.get("subcategory_name") or "").lower().replace("_", " ")
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

        # Fallback: If category_name provided (e.g. "Web"), use it cleanly as prefix rather than "00"
        if "orphan" in norm_cat or "unclassified" in norm_cat:
            prefix = "99_Unclassified_Orphan_Binaries"
        else:
            prefix = category_name or "00_Uncategorized"

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
