import json
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# Set plotting style
sns.set_theme(style="whitegrid")
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False


def perform_visual_analysis(json_path):
    # 1. Load data
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    problems = data.get('problems', [])
    df = pd.DataFrame(problems)

    # Preprocessing: Ensure 'type' field exists (fallback to 'question_type')
    if 'type' not in df.columns and 'question_type' in df.columns:
        df['type'] = df['question_type']

    # Create canvas
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    # --- Plot 1: Difficulty Distribution ---
    sns.countplot(x='difficulty', data=df, ax=axes[0], palette='viridis', hue='difficulty', legend=False)
    axes[0].set_title(f'Problem Difficulty Distribution (Total: {len(df)})', fontsize=14)
    axes[0].set_xlabel('Difficulty Level (1-5)')
    axes[0].set_ylabel('Count')

    # --- Plot 2: Topic vs Type Heatmap ---
    # Construct pivot table: Rows are topics, columns are types
    pivot_df = df.groupby(['topic', 'type']).size().unstack(fill_value=0)

    sns.heatmap(pivot_df, annot=True, fmt='d', cmap='YlGnBu', ax=axes[1])
    axes[1].set_title('Topic vs Question Type Distribution', fontsize=14)
    axes[1].set_xlabel('Question Type')
    axes[1].set_ylabel('Topic')

    plt.tight_layout()

    # Save results
    output_path = Path(json_path).parent / "dataset_analysis.png"
    plt.savefig(output_path, dpi=300)
    print(f"Analysis complete! Visualization saved to: {output_path}")
    plt.show()


if __name__ == "__main__":
    # Ensure this path points to your latest v3 file
    DATASET_PATH = "data/golden_dataset_v3.json"
    perform_visual_analysis(DATASET_PATH)