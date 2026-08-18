import os
import glob

TS_TEMPLATE = """/**
 * @file {filepath}
 * @description Core module for A.U.R.O.R.A. System
 *
 * Implements primary logic and architectural constraints.
 *
 * Architectural constraints and responsibilities apply here.
 * Testability and dependency separation are enforced.
 */
"""

PY_TEMPLATE = '"""\n@file {filepath}\n@description Core module for A.U.R.O.R.A. System\n\nImplements primary logic and architectural constraints.\n\nArchitectural constraints and responsibilities apply here.\nTestability and dependency separation are enforced.\n"""\n'

def process_file(filepath, template):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Check if header already exists
    if "@file" in content[:300]:
        return
        
    rel_path = os.path.relpath(filepath, start=os.getcwd()).replace('\\', '/')
    header = template.format(filepath=rel_path)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(header + "\n" + content)
        
def main():
    # Process Frontend (TS/TSX)
    for root, _, files in os.walk('frontend/src'):
        for file in files:
            if file.endswith(('.ts', '.tsx')):
                process_file(os.path.join(root, file), TS_TEMPLATE)
                
    # Process Backend (PY)
    for root, _, files in os.walk('backend/app'):
        for file in files:
            if file.endswith('.py') and not file.startswith('__'):
                process_file(os.path.join(root, file), PY_TEMPLATE)
                
    # Also main.py
    if os.path.exists('backend/main.py'):
        process_file('backend/main.py', PY_TEMPLATE)

if __name__ == "__main__":
    main()
