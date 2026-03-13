"""
File Operations Tools for ABC AI Agent
Provides file read, write, edit, and directory listing capabilities
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class FileTools:
    """File operation tools for the agent"""
    
    def __init__(self, allowed_base_dir: str):
        """
        Initialize file tools with security restrictions
        
        Args:
            allowed_base_dir: Base directory the agent can access
        """
        self.allowed_base_dir = Path(allowed_base_dir).resolve()
        logger.info(f"FileTools initialized with base: {self.allowed_base_dir}")
    
    def _validate_path(self, path: str) -> Tuple[bool, Path, str]:
        """
        Validate and resolve a file path
        
        Returns:
            (is_valid, resolved_path, error_message)
        """
        try:
            # Expand user and resolve to absolute path
            resolved = Path(path).expanduser().resolve()
            
            # Check if path is within allowed directory
            try:
                resolved.relative_to(self.allowed_base_dir)
            except ValueError:
                return False, resolved, f"Path {path} is outside allowed directory {self.allowed_base_dir}"
            
            return True, resolved, ""
            
        except Exception as e:
            return False, Path(path), f"Invalid path: {str(e)}"
    
    def read_file(self, file_path: str, start_line: int = 1, end_line: Optional[int] = None) -> Dict:
        """
        Read file contents with line numbers
        
        Args:
            file_path: Path to file
            start_line: Starting line number (1-indexed)
            end_line: Ending line number (optional)
            
        Returns:
            Dict with content, line numbers, and metadata
        """
        is_valid, resolved_path, error = self._validate_path(file_path)
        if not is_valid:
            return {"success": False, "error": error}
        
        if not resolved_path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}
        
        if not resolved_path.is_file():
            return {"success": False, "error": f"Path is not a file: {file_path}"}
        
        try:
            with open(resolved_path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
            
            total_lines = len(lines)
            
            # Adjust line numbers (convert to 0-indexed)
            start_idx = max(0, start_line - 1)
            end_idx = min(total_lines, end_line) if end_line else total_lines
            
            # Get requested lines with line numbers
            selected_lines = lines[start_idx:end_idx]
            numbered_content = ""
            for i, line in enumerate(selected_lines, start=start_line):
                numbered_content += f"{i:4d} | {line}"
            
            return {
                "success": True,
                "content": numbered_content,
                "total_lines": total_lines,
                "displayed_lines": len(selected_lines),
                "file_path": str(resolved_path),
                "file_name": resolved_path.name
            }
            
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return {"success": False, "error": f"Failed to read file: {str(e)}"}
    
    def write_file(self, file_path: str, content: str, append: bool = False) -> Dict:
        """
        Write content to a file
        
        Args:
            file_path: Path to file
            content: Content to write
            append: If True, append instead of overwrite
            
        Returns:
            Dict with result status
        """
        is_valid, resolved_path, error = self._validate_path(file_path)
        if not is_valid:
            return {"success": False, "error": error}
        
        try:
            # Create parent directories if needed
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            
            mode = 'a' if append else 'w'
            with open(resolved_path, mode, encoding='utf-8') as f:
                f.write(content)
            
            action = "appended to" if append else "written"
            return {
                "success": True,
                "message": f"Successfully {action} {resolved_path.name}",
                "file_path": str(resolved_path),
                "bytes_written": len(content.encode('utf-8'))
            }
            
        except Exception as e:
            logger.error(f"Error writing file {file_path}: {e}")
            return {"success": False, "error": f"Failed to write file: {str(e)}"}
    
    def edit_file(self, file_path: str, old_text: str, new_text: str) -> Dict:
        """
        Replace text in a file (first occurrence)
        
        Args:
            file_path: Path to file
            old_text: Text to find
            new_text: Text to replace with
            
        Returns:
            Dict with result status
        """
        is_valid, resolved_path, error = self._validate_path(file_path)
        if not is_valid:
            return {"success": False, "error": error}
        
        if not resolved_path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}
        
        try:
            with open(resolved_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if old_text not in content:
                return {"success": False, "error": f"Text not found in file: {old_text[:50]}..."}
            
            # Replace first occurrence
            new_content = content.replace(old_text, new_text, 1)
            
            with open(resolved_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            return {
                "success": True,
                "message": f"Successfully edited {resolved_path.name}",
                "file_path": str(resolved_path),
                "replacements": 1
            }
            
        except Exception as e:
            logger.error(f"Error editing file {file_path}: {e}")
            return {"success": False, "error": f"Failed to edit file: {str(e)}"}
    
    def list_directory(self, dir_path: str = ".", show_hidden: bool = False) -> Dict:
        """
        List files and directories
        
        Args:
            dir_path: Directory path
            show_hidden: Whether to show hidden files
            
        Returns:
            Dict with file listings
        """
        is_valid, resolved_path, error = self._validate_path(dir_path)
        if not is_valid:
            return {"success": False, "error": error}
        
        if not resolved_path.exists():
            return {"success": False, "error": f"Directory not found: {dir_path}"}
        
        if not resolved_path.is_dir():
            return {"success": False, "error": f"Path is not a directory: {dir_path}"}
        
        try:
            items = []
            
            for item in sorted(resolved_path.iterdir()):
                # Skip hidden files unless requested
                if not show_hidden and item.name.startswith('.'):
                    continue
                
                item_type = "📁" if item.is_dir() else "📄"
                size = ""
                if item.is_file():
                    size_bytes = item.stat().st_size
                    if size_bytes < 1024:
                        size = f"{size_bytes}B"
                    elif size_bytes < 1024 * 1024:
                        size = f"{size_bytes // 1024}KB"
                    else:
                        size = f"{size_bytes // (1024 * 1024)}MB"
                    size = f" ({size})"
                
                items.append(f"{item_type} {item.name}{size}")
            
            return {
                "success": True,
                "items": items,
                "total": len(items),
                "directory": str(resolved_path)
            }
            
        except Exception as e:
            logger.error(f"Error listing directory {dir_path}: {e}")
            return {"success": False, "error": f"Failed to list directory: {str(e)}"}


# For testing
if __name__ == "__main__":
    import tempfile
    
    # Create temp directory for testing
    test_dir = tempfile.mkdtemp()
    tools = FileTools(test_dir)
    
    # Test write
    print("Testing write_file...")
    result = tools.write_file(f"{test_dir}/test.txt", "Hello World\nLine 2\nLine 3")
    print(result)
    
    # Test read
    print("\nTesting read_file...")
    result = tools.read_file(f"{test_dir}/test.txt")
    print(result['content'])
    
    # Test edit
    print("\nTesting edit_file...")
    result = tools.edit_file(f"{test_dir}/test.txt", "Line 2", "Line 2 - EDITED")
    print(result)
    
    # Test list
    print("\nTesting list_directory...")
    result = tools.list_directory(test_dir)
    print("\n".join(result['items']))
    
    # Cleanup
    import shutil
    shutil.rmtree(test_dir)
    print("\n✓ All tests passed!")
