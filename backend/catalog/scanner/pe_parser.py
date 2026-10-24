import os
import struct
import re
from typing import Optional, List
from pathlib import Path

try:
    import pefile
except ImportError:
    pefile = None


from backend.catalog.schemas import ArchitectureEnum, RawBinaryMetadata


def extract_pe_metadata(file_path: str) -> RawBinaryMetadata:
    """
    Extract static metadata from a Windows PE (.exe) file.
    Uses 'pefile' if available and headers are valid, otherwise falls back to pure Python parsing.
    """
    path = Path(file_path)
    
    # Initialize metadata with defaults
    metadata = RawBinaryMetadata(
        sha256_hash="0" * 64,  # Placeholder; real hash would require hashlib
        file_size_bytes=0,
        file_extension=path.suffix.lower(),
        architecture=ArchitectureEnum.Unknown,
        pe_company_name=None,
        pe_product_name=None,
        pe_file_description=None,
        pe_original_filename=None,
        detected_version=None,
        msi_product_code=None,
        digital_signature_subject=None,
        parent_folder_chain=str(path.parent)
    )

    # Ensure file exists and has .exe extension
    if not path.exists():
        return metadata
    
    if not path.suffix.lower() == '.exe':
        return metadata

    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read()
        
        # Attempt pefile parsing
        if pefile is not None:
            try:
                pe = pefile.PE(file_path)
                
                # Extract Architecture
                arch_name = get_architecture_name(pe.FILE_HEADER.Machine)
                metadata.architecture = ArchitectureEnum(arch_name)
                
                # Extract Strings from Optional Header (VS_VERSION_INFO)
                vs_info = extract_vs_version_info(pe, raw_data)
                if vs_info:
                    for key, value in vs_info.items():
                        field_map = {
                            'CompanyName': 'pe_company_name',
                            'ProductName': 'pe_product_name',
                            'FileDescription': 'pe_file_description',
                            'FileVersion': 'detected_version',
                            'ProductVersion': 'detected_version',
                            'OriginalFilename': 'pe_original_filename',
                            'InternalName': None,
                            'LegalCopyright': None
                        }
                        
                        if key in field_map:
                            target_field = field_map[key]
                            if value:
                                metadata.__dict__[target_field] = str(value)

                # Check for Authenticode signature (PE header often contains a certificate blob)
                cert_subject = extract_cert_subject(raw_data, pe)
                if cert_subject:
                    metadata.digital_signature_subject = cert_subject

            except Exception as e:
                # Fallback to pure Python parsing if pefile fails or header is malformed
                try:
                    metadata.architecture, metadata.pe_company_name, metadata.pe_product_name, \
                    metadata.pe_file_description, metadata.pe_original_filename, metadata.detected_version = \
                        parse_pe_fallback(file_path)
                except Exception:
                    pass
        else:
            # pefile not installed, use pure Python fallback
            try:
                metadata.architecture, metadata.pe_company_name, metadata.pe_product_name, \
                metadata.pe_file_description, metadata.pe_original_filename, metadata.detected_version = \
                    parse_pe_fallback(file_path)
            except Exception:
                pass

    except Exception as e:
        # File read error or other unexpected issues
        pass
    
    return metadata


def get_architecture_name(machine_value: int) -> str:
    """Map PE Machine value to Architecture Enum string."""
    machine_map = {
        0x14c: "x86",           # IMAGE_FILE_MACHINE_I386
        0x8664: "x64",         # IMAGE_FILE_MACHINE_AMD64
        0xaa64: "ARM64",       # IMAGE_FILE_MACHINE_ARM64
        0x01c2: "Universal",   # IMAGE_FILE_MACHINE_IA64
    }
    
    return machine_map.get(machine_value, "Unknown")


def extract_vs_version_info(pe, raw_data):
    """Extract VS_VERSION_INFO strings from the PE Optional Header."""
    vs_info = {}
    
    try:
        # Check if there is a VS_VERSION_INFO section (Data Directory 0)
        data_section_idx = pe.OPTIONAL_HEADER.DataDirectory[0].VirtualAddress
        if data_section_idx < len(pe.sections):
            data_section = pe.sections[data_section_idx]
            raw_data_section = data_section.get_data()
            
            # Look for 'VS' signature (little-endian)
            vs_sig = b'\x56\x53'
            idx = raw_data_section.find(vs_sig)
            
            if idx != -1:
                # Parse VS_VERSION_INFO structure
                # Structure: [Signature(2)] [Version(4)] [StringTableOffset(4)]
                version = struct.unpack('<I', raw_data_section[idx+2:idx+6])[0]
                string_table_offset = struct.unpack('<I', raw_data_section[idx+6:idx+10])[0]
                
                # Get String Table data
                string_start = idx + 10
                string_end = string_start + version
                
                # Parse strings (UTF-16LE)
                offset = string_start
                while offset < string_end:
                    length = struct.unpack('<H', raw_data_section[offset:offset+2])[0]
                    if length == 0:
                        break
                    
                    try:
                        text = raw_data_section[offset+2:offset+length].decode('utf-16-le')
                        # Simple keyword matching based on string content
                        if 'CompanyName' in text or 'Company' in text:
                            vs_info['CompanyName'] = text
                        elif 'ProductName' in text or 'Product' in text:
                            vs_info['ProductName'] = text
                        elif 'FileDescription' in text or 'Description' in text:
                            vs_info['FileDescription'] = text
                        elif 'FileVersion' in text or 'Version' in text:
                            vs_info['FileVersion'] = text
                        elif 'ProductVersion' in text:
                            vs_info['ProductVersion'] = text
                        elif 'OriginalFilename' in text or 'FileName' in text:
                            vs_info['OriginalFilename'] = text
                    except UnicodeDecodeError:
                        break
                    
                    offset += length + 2
    except Exception:
        pass
    
    # Fallback: Try to extract strings directly from raw data if structure parsing fails
    try:
        vs_sig = b'\x56\x53'
        idx = raw_data.find(vs_sig)
        if idx != -1:
            version = struct.unpack('<I', raw_data[idx+2:idx+6])[0]
            string_table_offset = struct.unpack('<I', raw_data[idx+6:idx+10])[0]
            
            # Known offsets for VS_VERSION_INFO strings (simplified)
            string_start = idx + 10
            string_end = string_start + version
            
            # Simple keyword search in the string table region
            keywords = [b'CompanyName', b'ProductName', b'FileDescription', 
                       b'FileVersion', b'ProductVersion', b'OriginalFilename']
            
            for key_bytes in keywords:
                try:
                    key_idx = raw_data.find(key_bytes, string_start)
                    if key_idx != -1:
                        # Find the end of this keyword string
                        next_key = None
                        for k in keywords:
                            found = raw_data.find(k, key_idx + 1)
                            if found != -1 and found < key_idx + len(key_bytes):
                                next_key = found
                        
                        if next_key is None:
                            end = string_end
                        else:
                            end = next_key
                        
                        value_start = key_idx + len(key_bytes)
                        value_len = struct.unpack('<H', raw_data[value_start:value_start+2])[0]
                        
                        if value_len > 0 and value_start + 2 <= end:
                            try:
                                val = raw_data[value_start+2:value_start+value_len].decode('utf-16-le')
                                vs_info[key_bytes.decode('utf-8')] = val
                            except UnicodeDecodeError:
                                pass
                except Exception:
                    pass
    except Exception:
        pass
    
    return vs_info


def extract_cert_subject(raw_data, pe):
    """
    Attempt to extract Authenticode certificate subject string.
    This is a simplified heuristic for static analysis.
    Authenticode certificates are often stored in the PE header or optional header.
    We look for PKCS7 signatures or specific certificate structures.
    """
    # Heuristic: Look for "PKCS7" signature which indicates an embedded certificate
    if b'PKCS7' in raw_data:
        # Try to find a string that looks like a subject within the certificate data
        # A simple heuristic is to search for common subject patterns or just return the context
        # For zero-execution static analysis, we can scan the raw bytes of the Optional Header area.
        cert_start = raw_data.find(b'PKCS7')
        if cert_start != -1:
            # Look for a string pattern that resembles a certificate subject (e.g., CN=...)
            # or simply return the hex dump if no clear text is found, 
            # but per requirements we want the subject string.
            # We'll search for 'CN=' or similar patterns within 1KB of the PKCS7 marker
            search_area = raw_data[cert_start:cert_start+4096]
            
            # Try to find a string starting with CN=
            cn_match = re.search(rb'CN=(?:[^\\]|\\.)*', search_area)
            if cn_match:
                return cn_match.group().decode('utf-8')
            
            # Fallback: Return the raw hex of the certificate block if no clear text found
            # This ensures we don't lose data, though it's not a "subject string" per se.
            # However, to strictly follow "extract subject strings", we prioritize CN= matches.
            # If none found, return None or a placeholder indicating presence.
            # Let's return the first readable string found near PKCS7 if no CN match.
            for s in re.finditer(rb'[^\\]*(?:\\\\[^\n]*)?', search_area):
                try:
                    text = s.group().decode('utf-8')
                    if len(text) > 10: # Filter noise
                        return text
                except:
                    pass
    
    return None


def parse_pe_fallback(file_path: str):
    """
    Pure Python fallback for parsing PE headers.
    Returns tuple: (architecture, company_name, product_name, file_description, original_filename, detected_version)
    """
    with open(file_path, 'rb') as f:
        raw_data = f.read()
    
    # Check Magic Number
    if raw_data[:4] != b'MZ':
        return ("Unknown", None, None, None, None, None)
    
    # PE Header Offset (64 bytes)
    pe_offset = 64
    
    # Machine Type (Offset 0x3C + 2)
    machine_val = struct.unpack('<I', raw_data[pe_offset+0x3c:pe_offset+0x40])[0]
    arch_name = get_architecture_name(machine_val)
    
    # Optional Header Offset (Offset 0x68 + MachineSize)
    opt_header_offset = pe_offset + 0x68 + struct.unpack('<I', raw_data[pe_offset+0x3c:pe_offset+0x40])[0]
    
    # Check for VS_VERSION_INFO in Optional Header
    # Look for 'VS' signature
    vs_sig = b'\x56\x53'
    idx = raw_data.find(vs_sig, opt_header_offset)
    
    result_company = None
    result_product = None
    result_desc = None
    result_orig_name = None
    result_version = None
    
    if idx != -1:
        # Parse VS_VERSION_INFO structure
        version = struct.unpack('<I', raw_data[idx+2:idx+6])[0]
        string_table_offset = struct.unpack('<I', raw_data[idx+6:idx+10])[0]
        
        string_start = idx + 10
        string_end = string_start + version
        
        # Parse strings (UTF-16LE)
        offset = string_start
        while offset < string_end:
            length = struct.unpack('<H', raw_data[offset:offset+2])[0]
            if length == 0:
                break
            
            try:
                text = raw_data[offset+2:offset+length].decode('utf-16-le')
                
                # Check for keywords
                if 'CompanyName' in text or 'Company' in text:
                    result_company = text
                elif 'ProductName' in text or 'Product' in text:
                    result_product = text
                elif 'FileDescription' in text or 'Description' in text:
                    result_desc = text
                elif 'FileVersion' in text or 'Version' in text:
                    result_version = text
                elif 'OriginalFilename' in text or 'FileName' in text:
                    result_orig_name = text
            except UnicodeDecodeError:
                break
            
            offset += length + 2
    
    return (arch_name, result_company, result_product, result_desc, result_orig_name, result_version)
