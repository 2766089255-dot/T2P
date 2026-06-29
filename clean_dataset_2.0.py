import json
import re
import os


def unify_latex_to_standard_b(text):
    if not isinstance(text, str):
        return text

    # --- 1. Preprocessing: Fix common JSON escape traps ---
    # Unify multiple backslashes to prevent stacking caused by multi-layer data passing
    text = text.replace('\\\\', '\\')

    # --- 2. Convert Block Math ---
    # Convert \[ ... \] to \n\n$$\n...\n$$\n\n
    # Use re.DOTALL to ensure multiline matching for complex piecewise functions
    text = re.sub(r'\\\[([\s\S]*?)\\\]', r'\n\n$$\1$$\n\n', text)

    # --- 3. Convert Inline Math ---
    # Convert \( ... \) to $ ... $
    text = re.sub(r'\\\(([\s\S]*?)\\\)', r'$\1$', text)

    # --- 4. Edge Case Repair: Handle [ ... ] where backslashes were lost ---
    # Upgrade to $$ if [ ] contains LaTeX specific commands (e.g., \begin, \frac)
    text = re.sub(r'\[\s*([\s\S]*?(\\(?:begin|frac|lim|int|sum|sqrt|lambda|alpha|beta))[\s\S]*?)\s*\]',
                  r'\n\n$$\1$$\n\n', text)

    # --- 5. Formatting Automation: "Breathing Space" between text and formulas ---
    # Add space before $ (excluding start of line, newline, or existing space)
    text = re.sub(r'([^\s\$\n])(\$)', r'\1 \2', text)
    # Add space after $ (excluding end of line, newline, or common punctuation)
    text = re.sub(r'(\$)([^\s\$\n\.,!\?\?，。！？：；])', r'\1 \2', text)

    # --- 6. Core Logic Reinforcement: Piecewise functions and alignment ---
    if "\\begin{cases}" in text:
        # Ensure LaTeX newline \\ is correctly preserved inside cases
        # Many renderers fail on single \ in JSON; ensuring semantic clarity
        text = text.replace("\\\\", "\\\\\n")
        # Optimize spacing for alignment symbol &
        text = re.sub(r'\s*&\s*', ' & ', text)

    # --- 7. Clean redundant empty lines ---
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def upgrade_dataset_to_v4(input_path):
    if not os.path.exists(input_path):
        print(f"Input file not found: {input_path}")
        return

    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"JSON Parsing Error: {e}")
        return

    print(f"Processing dataset: {data.get('dataset_info', {}).get('name', 'Unknown')}")

    repair_count = 0

    # Define recursive cleaning to ensure nested fields (like scaffolding) are processed
    def recursive_clean(obj):
        nonlocal repair_count
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ['problem_statement', 'hint', 'explanation'] and isinstance(v, str):
                    cleaned = unify_latex_to_standard_b(v)
                    if cleaned != v:
                        obj[k] = cleaned
                        repair_count += 1
                else:
                    recursive_clean(v)
        elif isinstance(obj, list):
            for item in obj:
                recursive_clean(item)

    # Execute global cleaning
    recursive_clean(data.get('problems', []))

    # Update metadata versioning
    if 'dataset_info' in data:
        data['dataset_info']['version'] = "4.0-Standard-B"
        data['dataset_info']['description'] = "LaTeX normalization completed ($/$$); optimized spacing for web rendering."

    output_path = input_path.replace('.json', '_v4_standard_B.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        # ensure_ascii=False is kept to prevent turning characters into unicode escapes
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Cleaning complete! Fixed {repair_count} formatting issues.")
    print(f"New file saved to: {output_path}")


if __name__ == "__main__":
    # Please verify your file path
    path = r'D:\PycharmBase\T2P\data\golden_dataset_v3.json'
    upgrade_dataset_to_v4(path)