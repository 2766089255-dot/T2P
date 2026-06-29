import json
import os
from pathlib import Path


def standardize_calculus_dataset(input_path: str, output_path: str):
    """
    Data cleaning script for T2P project:
    1. Unify Topic tags to 15 standard core modules.
    2. Move the original segmentation labels to the sub_topic field.
    3. Ensure data consistency and optimize the Roadmap generation for UserSession.
    """

    # 1. Define a standard mapping dictionary (for the actual dirty labels in your dataset)
    topic_mapping = {
        # Derivative class merging
        "Derivatives": "Derivatives and Differentiation",
        "Chain Rule": "Derivatives and Differentiation",
        "Partial Derivatives": "Multivariable Calculus",
        "L'Hôpital's Rule": "Derivatives and Differentiation",
        "Related Rates": "Applications of Derivatives",
        "Optimization": "Applications of Derivatives",

        # Merge points categories
        "Fundamental Theorem of Calculus": "Integration and FTOC",
        "Riemann Sums": "Integration and FTOC",
        "Definite Integrals": "Integration and FTOC",
        "Integration by Parts": "Techniques of Integration",
        "Volume of Revolution": "Applications of Integration",

        # Series and Multivariate Categories
        "Infinite Series": "Sequences and Series",
        "Taylor Series": "Sequences and Series",
        "Lagrange Multipliers": "Multivariable Calculus",
        "Green's Theorem": "Vector Calculus",
        "Polar Coordinates": "Parametric and Polar Curves",

        # Conceptual category
        "Intermediate Value Theorem": "Limits and Continuity",
        "Separable ODEs": "Differential Equations"
    }

    # Load raw data
    if not os.path.exists(input_path):
        print(f"Error: File not found {input_path}")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    problems = data.get("problems", [])
    modified_count = 0

    print(f"Processing the No.{len(problems)} Title ..")

    # 2. Traverse and clean
    for prob in problems:
        old_topic = prob.get("topic")

        if old_topic in topic_mapping:
            new_topic = topic_mapping[old_topic]

            # If the original topic does not have sub_topic, save the old topic to preserve details
            if not prob.get("sub_topic") or prob["sub_topic"] == old_topic:
                prob["sub_topic"] = old_topic

            # Update to standard topic
            prob["topic"] = new_topic
            modified_count += 1

    # 3. Save the cleaned data
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    print(f"Cleaning completed!")
    print(f"Modification record:{modified_count} The tags have been standardized。")
    print(f"The new dataset has been saved to: {output_path}")


if __name__ == "__main__":
    # Get the root directory path of the current project
    base_dir = Path(__file__).resolve().parent
    input_file = base_dir / "data" / "golden_dataset_v2.json"
    output_file = base_dir / "data" / "golden_dataset_v2_standardized.json"

    standardize_calculus_dataset(str(input_file), str(output_file))