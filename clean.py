#!/usr/bin/env python3
"""
Script to delete all __pycache__ folders in the project.
"""

import os
import shutil
from pathlib import Path


def find_and_delete_pycache(root_path: Path) -> int:
    """
    Find and delete all __pycache__ folders recursively.
    
    Args:
        root_path: Root directory to start searching from
        
    Returns:
        Number of __pycache__ folders deleted
    """
    deleted_count = 0
    
    # Use Path.rglob() for more reliable recursive search
    for pycache_dir in root_path.rglob("__pycache__"):
        if pycache_dir.is_dir():
            try:
                shutil.rmtree(pycache_dir)
                print(f"✅ Deleted: {pycache_dir}")
                deleted_count += 1
            except Exception as e:
                print(f"❌ Failed to delete {pycache_dir}: {e}")
    
    return deleted_count


def main():
    """Main function to clean __pycache__ folders."""
    print("🧹 Cleaning __pycache__ folders in project...\n")
    
    # Get current project root
    project_root = Path(__file__).parent
    print(f"📁 Project root: {project_root.absolute()}")
    
    # Find and delete __pycache__ folders
    deleted_count = find_and_delete_pycache(project_root)
    
    print(f"\n🎉 Cleanup complete!")
    print(f"📊 Total __pycache__ folders deleted: {deleted_count}")
    
    if deleted_count == 0:
        print("✨ No __pycache__ folders found - project is already clean!")


if __name__ == "__main__":
    main()