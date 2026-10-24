import os
import re
import json
from typing import Optional, List, Dict, Any
from urllib.parse import quote
import requests
from dotenv import load_dotenv

from backend.catalog.schemas import RawBinaryMetadata, LLMClassificationResult, ArchitectureEnum
from backend.catalog.taxonomy_service import TaxonomyService
from backend.catalog.models import Taxonomy


load_dotenv()

class LLMSoftwareClassifier:
    def __init__(self):
        self.taxonomy_service = TaxonomyService()
        self.search_url = os.getenv("DUCKDUCKGO_SEARCH_URL", "https://api.duckduckgo.com/")
        self.llm_endpoint = os.getenv("LLM_ENDPOINT", "")
        self.llm_api_key = os.getenv("LLM_API_KEY", "")
        self.system_prompt = """You are a software classifier agent. Analyze the provided binary metadata and search results to determine its canonical identity, category, and license model.

Input Data:
- Filename: {filename}
- PE Product Name: {pe_product_name}
- PE Company Name: {pe_company_name}
- Parent Folder: {parent_folder}
- Search Results: {search_results}

Constraints:
1. Use the provided taxonomy categories as a base for classification.
2. If search results are available, prioritize them over internal metadata.
3. Determine the canonical vendor and product name based on authoritative sources.
4. Infer the license model (Open Source, Proprietary, Freeware, etc.) if possible.
5. Provide a concise summary and reasoning for your classification.

Output Format: JSON matching LLMClassificationResult schema."""

    def _build_search_query(self, metadata: RawBinaryMetadata) -> str:
        """Construct a search query combining filename, PE data, and folder hints."""
        parts = []
        
        # Filename
        if metadata.file_extension.lower() in ['.exe', '.msi', '.dll']:
            parts.append(f"{metadata.pe_original_filename or 'executable'} {metadata.file_extension}")
        else:
            parts.append(metadata.file_extension)

        # PE Data
        if metadata.pe_product_name:
            parts.append(f"product:{metadata.pe_product_name}")
        if metadata.pe_company_name:
            parts.append(f"company:{metadata.pe_company_name}")
        
        # Folder Hints (sanitized for search)
        folder_parts = re.sub(r'[^a-zA-Z0-9\s\-_]', '', str(metadata.parent_folder_chain))
        if folder_parts:
            parts.append(folder_parts)

        return " ".join(parts)

    def _perform_web_search(self, query: str) -> Optional[str]:
        """Perform a lightweight web search using DuckDuckGo API."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; SoftwareClassifier/1.0)'
            }
            
            # Try to use configured URL, otherwise fallback to standard DDG
            if self.search_url.startswith("http"):
                response = requests.get(self.search_url, params={"q": query}, headers=headers, timeout=10)
            else:
                response = requests.get("https://api.duckduckgo.com/", params={"q": query}, headers=headers, timeout=10)

            if response.status_code == 200:
                # Parse HTML to extract snippets or structured data
                content = response.text
                # Simple heuristic: look for 'title' tags or JSON-LD if available
                # For this implementation, we return the raw text as a fallback search summary
                # In a production environment, use BeautifulSoup or similar to parse specific fields
                return content[:2000]  # Limit size to avoid token overflow
            else:
                return None
        except Exception:
            # Graceful offline fallback
            return "No external search results available. Relying on internal metadata."

    def _call_llm(self, prompt: str) -> Optional[str]:
        """Call an LLM endpoint for classification."""
        if not self.llm_endpoint or not self.llm_api_key:
            return None
        
        try:
            payload = {
                "model": "llama-3.1-8b-instruct", # Default fallback, adjust based on config
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,
                "max_tokens": 1024
            }

            response = requests.post(self.llm_endpoint, json=payload, headers={"Authorization": f"Bearer {self.llm_api_key}"}, timeout=30)
            
            if response.status_code == 200:
                return response.json().get("choices", [{}])[0].get("message", {}).get("content")
            else:
                return None
        except Exception:
            return None

    def classify_binary(self, metadata: RawBinaryMetadata) -> LLMClassificationResult:
        """
        Classify a binary using web search and LLM inference.
        
        1. Build search query from metadata.
        2. Perform web search (DuckDuckGo).
        3. Call LLM with combined data.
        4. Parse result into LLMClassificationResult schema.
        """
        
        # Step 1: Construct Search Query
        search_query = self._build_search_query(metadata)

        # Step 2: Perform Web Search
        search_results_text = "No external data found."
        if metadata.pe_product_name or metadata.pe_company_name:
            search_results_text = self._perform_web_search(search_query)

        # Step 3: Prepare LLM Prompt
        prompt = self.system_prompt.format(
            filename=metadata.file_extension,
            pe_product_name=metadata.pe_product_name or "Unknown",
            pe_company_name=metadata.pe_company_name or "Unknown",
            parent_folder=metadata.parent_folder_chain or "Root",
            search_results=search_results_text
        )

        # Step 4: Call LLM
        llm_response = self._call_llm(prompt)

        # Step 5: Parse and Validate Result
        if not llm_response:
            # Fallback to default taxonomy if LLM fails
            return self._generate_fallback_result(metadata)

        try:
            result_data = json.loads(llm_response)
            
            # Extract fields, handling potential schema mismatches in response
            canonical_vendor = result_data.get("canonical_vendor", "Unknown")
            canonical_product = result_data.get("canonical_product", "Unknown")
            detected_version = result_data.get("detected_version", metadata.detected_version)
            architecture = ArchitectureEnum(metadata.architecture.value if metadata.architecture else "Unknown")
            
            # Determine category based on product name or search results
            primary_category = self._determine_primary_category(canonical_product, canonical_vendor)
            
            subcategory = None
            license_model = None
            
            # Infer subcategory and license from context
            if "IDE" in canonical_product.upper() or "Compiler" in canonical_product.upper():
                subcategory = "Integrated Development Environment"
            elif "Driver" in canonical_product.upper():
                subcategory = "Device Driver"
            
            summary = result_data.get("summary", f"Software identified as {canonical_product} by {canonical_vendor}.")
            reasoning = result_data.get("reasoning", "Classification based on PE metadata and web search.")
            confidence_score = float(result_data.get("confidence_score", 0.75))

            return LLMClassificationResult(
                canonical_vendor=canonical_vendor,
                canonical_product=canonical_product,
                detected_version=detected_version,
                architecture=architecture,
                primary_category=primary_category,
                subcategory=subcategory,
                license_model=license_model,
                summary=summary,
                confidence_score=confidence_score,
                reasoning=reasoning
            )
        except json.JSONDecodeError:
            return self._generate_fallback_result(metadata)

    def _determine_primary_category(self, product_name: str, vendor: str) -> str:
        """Map product/vendor to a taxonomy category prefix."""
        # Check against default taxonomies for quick mapping
        for tax in self.taxonomy_service.get_taxonomy_tree():
            if tax["category_prefix"] == "01_Development_Tools":
                if any(keyword in product_name.upper() for keyword in ["IDE", "COMPILER", "BUILD", "DEBUG", "SCRIPT"]):
                    return tax["category_prefix"]
            elif tax["category_prefix"] == "02_Productivity_and_Office":
                if any(keyword in product_name.upper() for keyword in ["WORD", "EXCEL", "POWERPOINT", "PROJECT", "OFFICE"]):
                    return tax["category_prefix"]
            elif tax["category_prefix"] == "03_System_Utilities":
                if any(keyword in product_name.upper() for keyword in ["DISK", "SYSTEM", "MONITOR", "CLEANUP", "UTIL"]):
                    return tax["category_prefix"]
            elif tax["category_prefix"] == "04_Drivers_and_Hardware":
                if any(keyword in product_name.upper() for keyword in ["DRIVER", "HARDWARE", "DEVICE", "GPU", "NETWORK"]):
                    return tax["category_prefix"]
            elif tax["category_prefix"] == "05_Media_and_Design":
                if any(keyword in product_name.upper() for keyword in ["PHOTO", "VIDEO", "DESIGN", "GRAPHIC", "MEDIA"]):
                    return tax["category_prefix"]
            elif tax["category_prefix"] == "06_Security_and_Network":
                if any(keyword in product_name.upper() for keyword in ["FIREWALL", "ANTIVIRUS", "SECURITY", "NETWORK", "PROXY"]):
                    return tax["category_prefix"]
            elif tax["category_prefix"] == "07_Scientific_and_CAD":
                if any(keyword in product_name.upper() for keyword in ["SIMULATION", "CALCULATOR", "CAD", "ENGINEERING"]):
                    return tax["category_prefix"]
            elif tax["category_prefix"] == "99_Unclassified_Orphan_Binaries":
                return tax["category_prefix"]
        
        # Default to unclassified if no match found
        return "99_Unclassified_Orphan_Binaries"

    def _generate_fallback_result(self, metadata: RawBinaryMetadata) -> LLMClassificationResult:
        """Generate a fallback result when LLM or search fails."""
        primary_category = "99_Unclassified_Orphan_Binaries"
        
        # Infer subcategory and license from context
        subcategory = None
        license_model = None
        
        if metadata.file_extension.lower() in ['.exe', '.msi']:
            subcategory = "Executable Binary"
        elif metadata.file_extension.lower() == '.dll':
            subcategory = "Dynamic Link Library"
        
        summary = f"Binary identified as {metadata.pe_original_filename or 'unknown'} ({metadata.file_extension})."
        reasoning = "Classification based on internal metadata due to lack of external data."
        confidence_score = 0.5

        return LLMClassificationResult(
            canonical_vendor="Unknown",
            canonical_product=metadata.pe_original_filename or "Unknown",
            detected_version=metadata.detected_version,
            architecture=ArchitectureEnum(metadata.architecture.value if metadata.architecture else "Unknown"),
            primary_category=primary_category,
            subcategory=subcategory,
            license_model=license_model,
            summary=summary,
            confidence_score=confidence_score,
            reasoning=reasoning
        )
